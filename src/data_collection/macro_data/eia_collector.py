# src/data_collection/macro_data/eia_collector.py
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
    print(f"Erro CRÍTICO em eia_collector.py ao importar módulos: {e}")
    sys.exit(1)

CONFIG_FILE_PATH = os.path.join(settings.BASE_DIR, "config", "eia_indicators_config.json")
EIA_API_BASE_URL = "https://api.eia.gov/v2" # API v2

def load_eia_config():
    """Carrega a configuração dos indicadores da EIA do arquivo JSON."""
    try:
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
            settings.logger.info(f"Configuração EIA carregada de {CONFIG_FILE_PATH} com {len(config_data)} entradas.")
            return config_data
    except FileNotFoundError:
        settings.logger.error(f"Arquivo de configuração EIA não encontrado: {CONFIG_FILE_PATH}")
        return []
    except json.JSONDecodeError:
        settings.logger.error(f"Erro ao decodificar JSON da EIA em: {CONFIG_FILE_PATH}")
        return []

def save_raw_data_eia(data_json: dict, config_params: dict, series_id_facet: str, period_str: str):
    """Salva os dados brutos JSON retornados pela API da EIA."""
    if not data_json or "response" not in data_json or not data_json["response"].get("data"):
        settings.logger.info(f"Dados JSON para salvar (EIA {series_id_facet}, período: {period_str}) estão vazios ou malformados. Nenhum arquivo bruto será salvo.")
        return

    file_part = config_params.get("file_part", f"eia_{series_id_facet}")
    filename_period_part = period_str.replace("-","") if isinstance(period_str, str) and len(period_str) > 7 else "completo"
    filename = f"{file_part}_{filename_period_part}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    raw_data_subfolder = config_params.get("raw_data_subfolder", os.path.join("eia_data", file_part))
    folder_path = os.path.join(settings.RAW_DATA_DIR, raw_data_subfolder)
    
    os.makedirs(folder_path, exist_ok=True)
    filepath = os.path.join(folder_path, filename)
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data_json, f, indent=4, ensure_ascii=False)
        settings.logger.info(f"Dados brutos da EIA (JSON) salvos em: {filepath}")
    except Exception as e:
        settings.logger.error(f"Erro ao salvar dados brutos da EIA em {filepath}: {e}")

def try_convert_eia_value_to_float(value):
    """Tenta converter o valor da EIA para float. Retorna None se falhar ou se o valor for None."""
    if value is None: # EIA pode retornar None para valores ausentes em JSON
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

def collect_eia_data():
    """Coleta dados de séries temporais da API da EIA."""
    if not settings.EIA_API_KEY:
        settings.logger.error("Chave da API da EIA (EIA_API_KEY) não configurada em settings.py. Finalizando coletor EIA.")
        return
        
    configs = load_eia_config()
    if not configs:
        settings.logger.warning("Nenhuma configuração de indicador da EIA carregada. Finalizando coletor EIA.")
        return

    session = get_db_session()
    
    try:
        for config_entry_index, config in enumerate(configs):
            if not config.get("enabled", False):
                settings.logger.info(f"Indicador EIA (config ID: {config.get('indicator_config_id', 'N/A')}) desabilitado, pulando.")
                continue

            indicator_config_id = config.get('indicator_config_id')
            db_indicator_name = config.get("db_indicator_name")
            params_config = config.get("params", {})
            api_route = params_config.get("api_route")
            facet_series_id = params_config.get("facet_series_id")
            frequency_param_api = params_config.get("frequency_param_api") # ex: "daily", "weekly", "monthly"
            
            db_indicator_type = config.get("db_indicator_type", "macro_international_commodity")
            db_indicator_frequency = config.get("db_indicator_frequency", "D")
            db_indicator_unit = config.get("db_indicator_unit", "value")

            if not all([indicator_config_id, db_indicator_name, api_route, facet_series_id, frequency_param_api]):
                settings.logger.warning(f"Configuração inválida para entrada {config_entry_index} (ID: {indicator_config_id}): campos essenciais ausentes. JSON: {config}. Pulando.")
                continue
            
            settings.logger.info(f"Processando: {indicator_config_id} - '{db_indicator_name}' (EIA Series Facet: {facet_series_id})")

            indicator_id_val = get_or_create_indicator_id(
                session, db_indicator_name, db_indicator_type,
                db_indicator_frequency, db_indicator_unit
            )
            if not indicator_id_val:
                settings.logger.error(f"Não foi possível obter/criar ID para o indicador '{db_indicator_name}'. Pulando coleta para EIA {facet_series_id}.")
                continue

            last_recorded_date = get_latest_effective_date(session, indicator_id_val)

            start_date_for_download_obj = pd.to_datetime(params_config.get("initial_history_start_date", "1980-01-01")).date()
            is_incremental_fetch = False
            if last_recorded_date:
                start_date_for_download_obj = last_recorded_date + timedelta(days=1)
                is_incremental_fetch = True
                settings.logger.info(f"Última data para '{db_indicator_name}' no BD: {last_recorded_date}. Buscando a partir de {start_date_for_download_obj.strftime('%Y-%m-%d')}.")
            else:
                settings.logger.info(f"Nenhum dado anterior para '{db_indicator_name}' no BD. Buscando histórico completo desde {start_date_for_download_obj.strftime('%Y-%m-%d')}.")
            
            # EIA API v2 usa formato YYYY-MM-DD para start/end
            observation_start_str = start_date_for_download_obj.strftime('%Y-%m-%d')
            observation_end_str = date.today().strftime('%Y-%m-%d') # Buscar até o dia atual

            if start_date_for_download_obj > date.today() and is_incremental_fetch:
                settings.logger.info(f"Data de início {start_date_for_download_obj.strftime('%Y-%m-%d')} é futura para '{db_indicator_name}'. Nenhum dado novo para buscar.")
                continue
            
            # Montar a URL da API v2 da EIA
            # Ex: https://api.eia.gov/v2/petroleum/pri/spt/data/?api_key=KEY&data[]=value&facets[seriesId][]=RBRTE&frequency=daily&start=2023-01-01&end=2023-01-31
            # O parâmetro 'data[]' especifica qual campo dos dados queremos, 'value' é o comum.
            # Para algumas séries, pode ser necessário ajustar os facets.
            
            url = f"{EIA_API_BASE_URL}{api_route}data/"
            api_call_params = {
                "api_key": settings.EIA_API_KEY,
                "data[0]": "value", 
                f"facets[series][0]": facet_series_id, # <<--- GARANTA QUE ESTÁ USANDO "series" AQUI
                "frequency": frequency_param_api,
                "start": observation_start_str,
                "end": observation_end_str,
                "sort[0][column]": "period",
                "sort[0][direction]": "asc",
                "offset": 0,
                "length": 5000 
            }
            
            response = None
            all_observations = []

            try:
                settings.logger.debug(f"Buscando EIA {facet_series_id} de {observation_start_str} até {observation_end_str}...")
                settings.logger.debug(f"URL EIA (sem api_key): {url} com params (sem api_key): {{k:v for k,v in api_call_params.items() if k != 'api_key'}}")

                # Loop para paginação se houver mais de 5000 resultados (comum para históricos longos)
                while True:
                    response = requests.get(url, params=api_call_params, timeout=settings.DEFAULT_REQUEST_TIMEOUT)
                    response.raise_for_status() 
                    current_page_data = response.json()
                    time.sleep(settings.API_DELAYS["EIA"])

                    if current_page_data and "response" in current_page_data and "data" in current_page_data["response"]:
                        observations_on_page = current_page_data["response"]["data"]
                        all_observations.extend(observations_on_page)
                        
                        # Log da primeira página para referência de salvamento de arquivo bruto
                        if api_call_params["offset"] == 0 and observations_on_page:
                             save_raw_data_eia(current_page_data, params_config, facet_series_id, observation_start_str)

                        #total_available = current_page_data["response"].get("total", 0)

                        # --- INÍCIO DA CORREÇÃO ---
                        total_available_str = current_page_data["response"].get("total") # Pega como pode vir (str ou int)
                        total_available = 0 # Default
                        if total_available_str is not None:
                            try:
                                total_available = int(total_available_str)
                            except ValueError:
                                settings.logger.error(f"Não foi possível converter 'total_available' ('{total_available_str}') para inteiro para a série {facet_series_id}.")
                                # Decide o que fazer: pode sair do loop ou tentar continuar sem paginação precisa.
                                # Sair do loop é mais seguro para evitar loops infinitos se a paginação falhar.
                                break 
                        else: # Se 'total' não estiver presente, assuma que não há mais páginas ou erro
                            settings.logger.warning(f"Campo 'total' não encontrado na resposta da EIA para {facet_series_id} na página com offset {api_call_params.get('offset', 0)}. Assumindo fim da paginação.")
                            break
                        current_offset = api_call_params.get("offset", 0)
                        current_length = len(observations_on_page)
                        
                        if not observations_on_page or (current_offset + current_length >= total_available):
                            settings.logger.debug(f"Fim da paginação para {facet_series_id}: offset_atual={current_offset}, compr_pagina={current_length}, total_disponivel={total_available}")
                            break 
                        
                        api_call_params["offset"] = current_offset + current_length
                        settings.logger.debug(f"Buscando próxima página da EIA para {facet_series_id}, offset: {api_call_params['offset']}")
                    else:
                        settings.logger.info(f"Estrutura de resposta inesperada ou sem dados da EIA para {facet_series_id} na página com offset {api_call_params['offset']}.")
                        break # Sai do loop se a resposta não for como esperado
                
                if not all_observations:
                     settings.logger.info(f"Nenhuma observação encontrada na resposta da EIA para {facet_series_id} no período.")


            except requests.exceptions.HTTPError as http_err:
                # Agora 'response' estará definida aqui se o erro ocorreu após requests.get()
                error_content = "N/A"
                if response is not None:
                    try:
                        error_content = response.json() # Tenta pegar JSON se for um erro estruturado da API
                    except json.JSONDecodeError:
                        error_content = response.text # Pega texto se não for JSON
                settings.logger.error(f"Erro HTTP ao buscar dados da EIA {facet_series_id}: {http_err}. Conteúdo da Resposta: {error_content}")
                continue # Ou return, dependendo da sua lógica de loop
            except requests.exceptions.RequestException as req_err:
                settings.logger.error(f"Erro de requisição ao buscar dados da EIA {facet_series_id}: {req_err}")
                continue
            except json.JSONDecodeError as json_err:
                settings.logger.error(f"Erro ao decodificar JSON da resposta da EIA para {facet_series_id}: {json_err}. Resposta: {response.text if 'response' in locals() and response else 'N/A'}")
                continue
            except Exception as e_api:
                 settings.logger.error(f"Erro inesperado durante chamada à API da EIA para {facet_series_id}: {e_api}", exc_info=True)
                 continue


            if all_observations:
                data_to_insert = []
                for obs in all_observations:
                    # O campo de data na API v2 é "period"
                    # O formato da data/período pode variar (YYYY-MM-DD, YYYY-MM, YYYY, YYYYMMDDTHHMMSSZ)
                    # Precisamos normalizar para datetime.date
                    obs_period_str = obs.get("period")
                    obs_value_data = obs.get("value") # O campo de valor na API v2 é "value"

                    if not obs_period_str or obs_value_data is None:
                        settings.logger.debug(f"Observação EIA inválida ou valor ausente para {facet_series_id} período '{obs_period_str}'. Pulando.")
                        continue
                    
                    try:
                        # Tenta converter o 'period' para datetime.date
                        # A API da EIA v2 especifica dateFormat na resposta, mas pd.to_datetime é robusto
                        effective_date_val = pd.to_datetime(obs_period_str).date()
                        value_num = try_convert_eia_value_to_float(obs_value_data)

                        if value_num is None:
                            settings.logger.debug(f"Valor '{obs_value_data}' para EIA {facet_series_id} em {effective_date_val} não é numérico ou é ausente. Pulando.")
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
                    except Exception as ve_parse: # Erro mais genérico no parsing do período
                        settings.logger.warning(f"Erro ao processar observação da EIA para {facet_series_id}: Período='{obs_period_str}', Valor='{obs_value_data}'. Erro: {ve_parse}")
                        continue
                
                if data_to_insert:
                    settings.logger.debug(f"EIA - Dados preparados para UPSERT para {db_indicator_name} (Série Facet: {facet_series_id}), {len(data_to_insert)} itens.")
                    if data_to_insert:
                         log_entry = {k: data_to_insert[0].get(k) for k in ['indicator_id', 'effective_date', 'value_numeric']}
                         settings.logger.debug(f"  Exemplo do primeiro item para UPSERT: {log_entry}")
                    batch_upsert_indicator_values(session, data_to_insert)
                else:
                    settings.logger.info(f"Nenhum dado válido para inserir para {db_indicator_name} (Série Facet: {facet_series_id}) após processamento das observações.")
            # else: (all_observations estava vazia)
            #    settings.logger.info(f"Nenhuma observação bruta para processar para {db_indicator_name} (Série Facet: {facet_series_id}).")
        
        settings.logger.info("Coleta de dados da EIA concluída.")

    except Exception as e_outer:
        settings.logger.error(f"Erro geral no processo de coleta da EIA: {e_outer}", exc_info=True)
    finally:
        if session:
            session.close()
            settings.logger.info("Sessão do EIA Collector fechada.")

