# src/data_collection/macro_data/fred_collector.py
# -*- coding: utf-8 -*-

import pandas as pd
import json
import os
import time
import requests # Para fazer chamadas HTTP à API
from datetime import datetime, date, timedelta

# Adiciona o diretório raiz do projeto ao sys.path
import sys
project_root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if project_root_path not in sys.path:
    sys.path.append(project_root_path)

try:
    from config import settings
    from src.database.db_utils import (
        get_db_session, get_or_create_indicator_id,
        batch_upsert_indicator_values, get_latest_effective_date
    )
except ImportError as e:
    print(f"Erro CRÍTICO em fred_collector.py ao importar módulos: {e}")
    sys.exit(1)

CONFIG_FILE_PATH = os.path.join(settings.BASE_DIR, "config", "fred_indicators_config.json")
FRED_API_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

def load_fred_config():
    """Carrega a configuração dos indicadores do FRED do arquivo JSON."""
    try:
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
            settings.logger.info(f"Configuração FRED carregada de {CONFIG_FILE_PATH} com {len(config_data)} entradas.")
            return config_data
    except FileNotFoundError:
        settings.logger.error(f"Arquivo de configuração FRED não encontrado: {CONFIG_FILE_PATH}")
        return []
    except json.JSONDecodeError:
        settings.logger.error(f"Erro ao decodificar JSON do FRED em: {CONFIG_FILE_PATH}")
        return []

def save_raw_data_fred(data_json: dict, config_params: dict, series_id: str, period_str: str):
    """Salva os dados brutos JSON retornados pela API do FRED."""
    if not data_json:
        settings.logger.info(f"Dados JSON para salvar (FRED {series_id}, período: {period_str}) estão vazios. Nenhum arquivo bruto será salvo.")
        return

    file_part = config_params.get("file_part", f"fred_{series_id}")
    filename_period_part = period_str.replace("-","") if isinstance(period_str, str) and len(period_str) > 7 else "completo"
    filename = f"{file_part}_{filename_period_part}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    raw_data_subfolder = config_params.get("raw_data_subfolder", os.path.join("fred_data", file_part)) # Alterado para pegar do params
    folder_path = os.path.join(settings.RAW_DATA_DIR, raw_data_subfolder)
    
    os.makedirs(folder_path, exist_ok=True)
    filepath = os.path.join(folder_path, filename)
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data_json, f, indent=4, ensure_ascii=False)
        settings.logger.info(f"Dados brutos do FRED (JSON) salvos em: {filepath}")
    except Exception as e:
        settings.logger.error(f"Erro ao salvar dados brutos do FRED em {filepath}: {e}")

def try_convert_to_float(value_str):
    """Tenta converter uma string para float. Retorna None se falhar ou se o valor for '.' (FRED missing)."""
    if value_str == ".": # Representação de valor ausente no FRED
        return None
    try:
        return float(value_str)
    except (ValueError, TypeError):
        return None

def collect_fred_data():
    """Coleta dados de séries temporais da API do FRED."""
    if not settings.FRED_API_KEY:
        settings.logger.error("Chave da API do FRED (FRED_API_KEY) não configurada em settings.py. Finalizando coletor FRED.")
        return
        
    configs = load_fred_config()
    if not configs:
        settings.logger.warning("Nenhuma configuração de indicador do FRED carregada. Finalizando coletor FRED.")
        return

    session = get_db_session()
    
    try:
        for config_entry_index, config in enumerate(configs):
            if not config.get("enabled", False):
                settings.logger.info(f"Indicador FRED (config ID: {config.get('indicator_config_id', 'N/A')}) desabilitado, pulando.")
                continue

            indicator_config_id = config.get('indicator_config_id')
            db_indicator_name = config.get("db_indicator_name")
            params_config = config.get("params", {}) # Parâmetros específicos da série FRED
            series_id_fred = params_config.get("series_id")
            
            db_indicator_type = config.get("db_indicator_type", "macro_international")
            db_indicator_frequency = config.get("db_indicator_frequency", "D")
            db_indicator_unit = config.get("db_indicator_unit", "value")

            if not indicator_config_id or not db_indicator_name or not series_id_fred:
                settings.logger.warning(f"Configuração inválida para entrada {config_entry_index} (ID: {indicator_config_id}): db_indicator_name ou series_id ausentes. JSON: {config}. Pulando.")
                continue
            
            settings.logger.info(f"Processando: {indicator_config_id} - '{db_indicator_name}' (FRED Series ID: {series_id_fred})")

            indicator_id_val = get_or_create_indicator_id(
                session, db_indicator_name, db_indicator_type,
                db_indicator_frequency, db_indicator_unit
            )
            if not indicator_id_val:
                settings.logger.error(f"Não foi possível obter/criar ID para o indicador '{db_indicator_name}'. Pulando coleta para FRED {series_id_fred}.")
                continue

            last_recorded_date = get_latest_effective_date(session, indicator_id_val)

            start_date_for_download_obj = pd.to_datetime(params_config.get("initial_history_start_date", "1900-01-01")).date()
            is_incremental_fetch = False
            if last_recorded_date:
                start_date_for_download_obj = last_recorded_date + timedelta(days=1)
                is_incremental_fetch = True
                settings.logger.info(f"Última data para '{db_indicator_name}' no BD: {last_recorded_date}. Buscando a partir de {start_date_for_download_obj.strftime('%Y-%m-%d')}.")
            else:
                settings.logger.info(f"Nenhum dado anterior para '{db_indicator_name}' no BD. Buscando histórico completo desde {start_date_for_download_obj.strftime('%Y-%m-%d')}.")
            
            # FRED API usa formato YYYY-MM-DD
            observation_start_str = start_date_for_download_obj.strftime('%Y-%m-%d')
            observation_end_str = date.today().strftime('%Y-%m-%d')


            if start_date_for_download_obj > date.today() and is_incremental_fetch:
                settings.logger.info(f"Data de início {start_date_for_download_obj.strftime('%Y-%m-%d')} é futura para '{db_indicator_name}'. Nenhum dado novo para buscar.")
                continue
            
            api_params = {
                "series_id": series_id_fred,
                "api_key": settings.FRED_API_KEY,
                "file_type": "json",
                "observation_start": observation_start_str,
                "observation_end": observation_end_str,
                # "frequency": params_config.get("api_frequency_code"), # Opcional, se a série permitir e você quiser forçar
                # "units": "lin" # Nível (padrão), ou "chg", "pch", etc.
            }
            
            response_data = None
            try:
                settings.logger.debug(f"Buscando FRED {series_id_fred} de {observation_start_str} até {observation_end_str}...")
                response = requests.get(FRED_API_BASE_URL, params=api_params, timeout=settings.DEFAULT_REQUEST_TIMEOUT)
                response.raise_for_status() # Levanta HTTPError para respostas ruins (4XX ou 5XX)
                response_data = response.json()
                time.sleep(settings.API_DELAYS["FRED"])

                if response_data:
                    save_raw_data_fred(response_data, params_config, series_id_fred, observation_start_str)
                else: # Pode não ser um erro, mas a API pode retornar um JSON vazio ou com estrutura de erro
                    settings.logger.info(f"Nenhum dado JSON retornado pela API do FRED para {series_id_fred} no período.")
            
            except requests.exceptions.HTTPError as http_err:
                settings.logger.error(f"Erro HTTP ao buscar dados do FRED {series_id_fred}: {http_err}. Resposta: {response.text if response else 'N/A'}")
                continue
            except requests.exceptions.RequestException as req_err:
                settings.logger.error(f"Erro de requisição ao buscar dados do FRED {series_id_fred}: {req_err}")
                continue
            except json.JSONDecodeError as json_err:
                settings.logger.error(f"Erro ao decodificar JSON da resposta do FRED para {series_id_fred}: {json_err}. Resposta: {response.text if response else 'N/A'}")
                continue


            if response_data and "observations" in response_data and response_data["observations"]:
                data_to_insert = []
                for obs in response_data["observations"]:
                    obs_date_str = obs.get("date")
                    obs_value_str = obs.get("value")

                    if not obs_date_str or obs_value_str is None: # obs_value_str pode ser "."
                        settings.logger.debug(f"Observação inválida ou valor ausente para {series_id_fred} em {obs_date_str}. Pulando.")
                        continue
                    
                    try:
                        effective_date_val = datetime.strptime(obs_date_str, '%Y-%m-%d').date()
                        value_num = try_convert_to_float(obs_value_str)

                        if value_num is None: # Se o valor foi "." ou não conversível
                            settings.logger.debug(f"Valor '{obs_value_str}' para {series_id_fred} em {effective_date_val} não é numérico ou é ausente. Pulando.")
                            continue

                        data_to_insert.append({
                            "indicator_id": indicator_id_val,
                            "company_id": None, 
                            "segment_id": None, 
                            "effective_date": effective_date_val,
                            "value_numeric": value_num,
                            "value_text": None,
                            "collection_timestamp": datetime.now()
                        })
                    except ValueError as ve:
                        settings.logger.warning(f"Erro ao processar observação do FRED para {series_id_fred}: Data='{obs_date_str}', Valor='{obs_value_str}'. Erro: {ve}")
                        continue
                
                if data_to_insert:
                    settings.logger.debug(f"FRED - Dados preparados para UPSERT para {db_indicator_name} (Série: {series_id_fred}), {len(data_to_insert)} itens.")
                    if data_to_insert:
                         log_entry = {k: data_to_insert[0].get(k) for k in ['indicator_id', 'effective_date', 'value_numeric']}
                         settings.logger.debug(f"  Exemplo do primeiro item para UPSERT: {log_entry}")
                    batch_upsert_indicator_values(session, data_to_insert)
                else:
                    settings.logger.info(f"Nenhum dado válido para inserir para {db_indicator_name} (Série: {series_id_fred}) após processamento das observações.")
            else:
                 settings.logger.info(f"Nenhuma observação encontrada na resposta do FRED para {series_id_fred} no período ou resposta vazia.")
        
        settings.logger.info("Coleta de dados do FRED concluída.")

    except Exception as e_outer:
        settings.logger.error(f"Erro geral no processo de coleta do FRED: {e_outer}", exc_info=True)
    finally:
        if session:
            session.close()
            settings.logger.info("Sessão do FRED Collector fechada.")

