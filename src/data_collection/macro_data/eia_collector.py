# src/data_collection/macro_data/eia_collector.py
# -*- coding: utf-8 -*-

import pandas as pd
import json
import os
import time
import requests # Para fazer chamadas HTTP à API
from datetime import datetime, date, timedelta
import copy # Importar a biblioteca copy para deepcopy

# Adiciona o diretório raiz do projeto ao sys.path
import sys
project_root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if project_root_path not in sys.path:
    sys.path.append(project_root_path)

# Bloco try-except para importações de módulos do projeto
# Isso garante que o script possa ser executado mesmo que as importações falhem,
# o que é útil para testes isolados, mas idealmente as importações devem funcionar.
try:
    from config import settings # Assumindo que settings.py está em config/ e contém EIA_API_KEY, logger, etc.
    from src.database.db_utils import ( # Assumindo que db_utils.py está em src/database/
        get_db_session, get_or_create_indicator_id,
        batch_upsert_indicator_values, get_latest_effective_date
    )
except ImportError as e:
    # Para permitir que o script seja analisado mesmo que as importações locais falhem
    # em um ambiente diferente, mas emitir um aviso forte.
    print(f"ALERTA DE IMPORTAÇÃO em eia_collector.py: Não foi possível importar módulos do projeto: {e}")
    print("Este script pode não funcionar corretamente sem esses módulos.")
    # Definir placeholders para settings e db_utils se não puderem ser importados
    # Isso é apenas para que o resto do código não quebre imediatamente na definição.
    # Em uma execução real, a ausência desses módulos seria um problema.
    class MockSettings:
        EIA_API_KEY = None
        RAW_DATA_DIR = "./temp_raw_data" # Diretório temporário
        BASE_DIR = "."
        DEFAULT_REQUEST_TIMEOUT = 30
        API_DELAYS = {"EIA": 1}
        class MockLogger:
            def info(self, msg): print(f"INFO: {msg}")
            def warning(self, msg): print(f"WARNING: {msg}")
            def error(self, msg, exc_info=False): print(f"ERROR: {msg}")
            def debug(self, msg): print(f"DEBUG: {msg}")
        logger = MockLogger()

    settings = MockSettings()
    def get_db_session(): return None
    def get_or_create_indicator_id(session, name, type, freq, unit): return None
    def batch_upsert_indicator_values(session, values): pass
    def get_latest_effective_date(session, id): return None


CONFIG_FILE_PATH = os.path.join(settings.BASE_DIR, "config", "eia_indicators_config.json")
EIA_API_BASE_URL = "https://api.eia.gov/v2"

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
    except Exception as e:
        settings.logger.error(f"Erro inesperado ao carregar configuração EIA: {e}")
        return []

def save_raw_data_eia(data_json: dict, config_params: dict, series_id_facet: str, period_str: str):
    """Salva os dados brutos JSON retornados pela API da EIA, removendo/redigindo a api_key."""
    if not data_json or "response" not in data_json:
        settings.logger.info(f"Dados JSON para salvar (EIA {series_id_facet}, período: {period_str}) estão vazios ou malformados. Nenhum arquivo bruto será salvo.")
        return

    # --- MODIFICAÇÃO PARA REMOVER/REDIGIR API KEY ---
    data_to_save = copy.deepcopy(data_json) # Trabalhar com uma cópia

    if 'request' in data_to_save and \
       isinstance(data_to_save.get('request'), dict) and \
       'params' in data_to_save['request'] and \
       isinstance(data_to_save['request'].get('params'), dict) and \
       'api_key' in data_to_save['request']['params']:
        
        data_to_save['request']['params']['api_key'] = "REDACTED_FOR_SECURITY"
        settings.logger.debug(f"API key REDIGIDA no JSON bruto para {series_id_facet} antes de salvar.")
    # --- FIM DA MODIFICAÇÃO ---
        
    file_part = config_params.get("file_part", f"eia_{series_id_facet}")
    filename_period_part = period_str.replace("-","") if isinstance(period_str, str) and len(period_str) > 7 else "completo"
    filename = f"{file_part}_{filename_period_part}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    raw_data_subfolder = config_params.get("raw_data_subfolder", os.path.join("eia_data", file_part))
    folder_path = os.path.join(settings.RAW_DATA_DIR, raw_data_subfolder)
    
    os.makedirs(folder_path, exist_ok=True)
    filepath = os.path.join(folder_path, filename)
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, indent=4, ensure_ascii=False) # Salva o dicionário modificado
        settings.logger.info(f"Dados brutos da EIA (JSON com API Key redigida) salvos em: {filepath}")
    except Exception as e:
        settings.logger.error(f"Erro ao salvar dados brutos da EIA em {filepath}: {e}")

def try_convert_eia_value_to_float(value):
    """Tenta converter o valor da EIA para float. Retorna None se falhar ou se o valor for None."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        settings.logger.warning(f"Não foi possível converter valor '{value}' para float.")
        return None

def collect_eia_data():
    """Coleta dados de séries temporais da API da EIA."""
    if not settings.EIA_API_KEY:
        settings.logger.error("Chave da API da EIA (EIA_API_KEY) não configurada em settings.py ou via variável de ambiente. Finalizando coletor EIA.")
        return
            
    configs = load_eia_config()
    if not configs:
        settings.logger.warning("Nenhuma configuração de indicador da EIA carregada. Finalizando coletor EIA.")
        return

    session = get_db_session() # Assume que esta função retorna uma sessão SQLAlchemy ou similar, ou None
    if session is None and settings.RUNNING_ENV != "test": # Permite testes sem DB real
        settings.logger.error("Não foi possível obter sessão do banco de dados. Finalizando coletor EIA.")
        return
    
    try:
        for config_entry_index, config in enumerate(configs):
            if not config.get("enabled", False):
                settings.logger.info(f"Indicador EIA (config ID: {config.get('indicator_config_id', 'N/A')}) desabilitado, pulando.")
                continue

            indicator_config_id = config.get('indicator_config_id')
            db_indicator_name = config.get("db_indicator_name")
            params_config = config.get("params", {})
            api_route = params_config.get("api_route")
            facet_series_id = params_config.get("facet_series_id") # Este é o ID da série na EIA
            frequency_param_api = params_config.get("frequency_param_api")
            
            db_indicator_type = config.get("db_indicator_type", "macro_international_commodity")
            db_indicator_frequency = config.get("db_indicator_frequency", "D") # Frequência para o NOSSO BANCO
            db_indicator_unit = config.get("db_indicator_unit", "value")

            if not all([indicator_config_id, db_indicator_name, api_route, facet_series_id, frequency_param_api]):
                settings.logger.warning(f"Configuração inválida para entrada {config_entry_index} (ID: {indicator_config_id}): campos essenciais ausentes. JSON: {config}. Pulando.")
                continue
            
            settings.logger.info(f"Processando: {indicator_config_id} - '{db_indicator_name}' (EIA Series Facet: {facet_series_id})")

            indicator_id_val = None
            if session: # Somente interage com DB se a sessão existir
                indicator_id_val = get_or_create_indicator_id(
                    session, db_indicator_name, db_indicator_type,
                    db_indicator_frequency, db_indicator_unit
                )
                if not indicator_id_val:
                    settings.logger.error(f"Não foi possível obter/criar ID para o indicador '{db_indicator_name}'. Pulando coleta para EIA {facet_series_id}.")
                    continue

            last_recorded_date = None
            if session and indicator_id_val:
                last_recorded_date = get_latest_effective_date(session, indicator_id_val)

            start_date_for_download_obj = pd.to_datetime(params_config.get("initial_history_start_date", "1980-01-01")).date()
            is_incremental_fetch = False
            if last_recorded_date:
                start_date_for_download_obj = last_recorded_date + timedelta(days=1)
                is_incremental_fetch = True
                settings.logger.info(f"Última data para '{db_indicator_name}' no BD: {last_recorded_date}. Buscando a partir de {start_date_for_download_obj.strftime('%Y-%m-%d')}.")
            else:
                settings.logger.info(f"Nenhum dado anterior para '{db_indicator_name}' no BD. Buscando histórico completo desde {start_date_for_download_obj.strftime('%Y-%m-%d')}.")
            
            observation_start_str = start_date_for_download_obj.strftime('%Y-%m-%d')
            observation_end_str = date.today().strftime('%Y-%m-%d')

            if start_date_for_download_obj > date.today() and is_incremental_fetch:
                settings.logger.info(f"Data de início {start_date_for_download_obj.strftime('%Y-%m-%d')} é futura para '{db_indicator_name}'. Nenhum dado novo para buscar.")
                continue
            
            url = f"{EIA_API_BASE_URL}{api_route}data/"
            api_call_params = {
                "api_key": settings.EIA_API_KEY, # A chave é usada aqui para fazer a requisição
                "data[0]": "value", 
                f"facets[series][0]": facet_series_id,
                "frequency": frequency_param_api,
                "start": observation_start_str,
                "end": observation_end_str,
                "sort[0][column]": "period",
                "sort[0][direction]": "asc",
                "offset": 0,
                "length": params_config.get("page_length", 5000) # Permitir configurar page_length via JSON
            }
            
            response = None
            all_observations = []

            try:
                settings.logger.debug(f"Buscando EIA {facet_series_id} de {observation_start_str} até {observation_end_str}...")
                # Log sem a API Key
                params_to_log = {k:v for k,v in api_call_params.items() if k != 'api_key'}
                settings.logger.debug(f"URL EIA: {url} com params: {params_to_log}")

                while True:
                    response = requests.get(url, params=api_call_params, timeout=settings.DEFAULT_REQUEST_TIMEOUT)
                    response.raise_for_status() 
                    current_page_data = response.json() # Dicionário Python
                    
                    # Atraso após cada chamada de API
                    time.sleep(settings.API_DELAYS.get("EIA", 1)) # Usa delay de settings ou default 1s

                    if current_page_data and "response" in current_page_data and "data" in current_page_data["response"]:
                        observations_on_page = current_page_data["response"]["data"]
                        all_observations.extend(observations_on_page)
                        
                        if api_call_params["offset"] == 0 and observations_on_page:
                             # Passa o current_page_data original para save_raw_data_eia,
                             # que fará a cópia e a redação da chave.
                            save_raw_data_eia(current_page_data, params_config, facet_series_id, observation_start_str)

                        total_available_str = current_page_data["response"].get("total")
                        total_available = 0
                        if total_available_str is not None:
                            try:
                                total_available = int(total_available_str)
                            except ValueError:
                                settings.logger.error(f"Não foi possível converter 'total_available' ('{total_available_str}') para inteiro para a série {facet_series_id}.")
                                break 
                        else:
                            settings.logger.warning(f"Campo 'total' não encontrado na resposta da EIA para {facet_series_id}. Assumindo fim da paginação.")
                            break
                        
                        current_offset = api_call_params.get("offset", 0) # Deve ser api_call_params["offset"]
                        current_length_on_page = len(observations_on_page)
                        
                        if not observations_on_page or (current_offset + current_length_on_page >= total_available):
                            settings.logger.debug(f"Fim da paginação para {facet_series_id}: offset_atual={current_offset}, compr_pagina={current_length_on_page}, total_disponivel={total_available}")
                            break 
                        
                        api_call_params["offset"] = current_offset + api_call_params["length"] # Usa o length configurado
                        settings.logger.debug(f"Buscando próxima página da EIA para {facet_series_id}, offset: {api_call_params['offset']}")
                    else:
                        settings.logger.info(f"Estrutura de resposta inesperada ou sem dados da EIA para {facet_series_id} na página com offset {api_call_params.get('offset',0)}.")
                        break
                
                if not all_observations:
                    settings.logger.info(f"Nenhuma observação encontrada na resposta da EIA para {facet_series_id} no período.")

            except requests.exceptions.HTTPError as http_err:
                error_content = "N/A"
                if response is not None:
                    try: error_content = response.json()
                    except json.JSONDecodeError: error_content = response.text
                settings.logger.error(f"Erro HTTP ao buscar dados da EIA {facet_series_id}: {http_err}. Conteúdo: {error_content}")
                continue 
            except requests.exceptions.RequestException as req_err:
                settings.logger.error(f"Erro de requisição ao buscar dados da EIA {facet_series_id}: {req_err}")
                continue
            except json.JSONDecodeError as json_err:
                settings.logger.error(f"Erro ao decodificar JSON da EIA para {facet_series_id}: {json_err}. Resposta: {response.text if response else 'N/A'}")
                continue
            except Exception as e_api:
                settings.logger.error(f"Erro inesperado durante chamada à API EIA para {facet_series_id}: {e_api}", exc_info=True)
                continue

            if all_observations:
                data_to_insert = []
                for obs in all_observations:
                    obs_period_str = obs.get("period")
                    obs_value_data = obs.get("value")

                    if not obs_period_str or obs_value_data is None:
                        settings.logger.debug(f"Observação EIA inválida para {facet_series_id} período '{obs_period_str}'. Pulando.")
                        continue
                    
                    try:
                        effective_date_val = pd.to_datetime(obs_period_str).date()
                        value_num = try_convert_eia_value_to_float(obs_value_data)

                        if value_num is None:
                            settings.logger.debug(f"Valor '{obs_value_data}' para EIA {facet_series_id} em {effective_date_val} não é numérico. Pulando.")
                            continue

                        data_to_insert.append({
                            "indicator_id": indicator_id_val,
                            "company_id": None, "segment_id": None, # Ajuste se necessário para seu schema de DB
                            "effective_date": effective_date_val,
                            "value_numeric": value_num,
                            "value_text": None,
                            "collection_timestamp": datetime.now()
                        })
                    except Exception as ve_parse:
                        settings.logger.warning(f"Erro ao processar observação EIA para {facet_series_id}: Período='{obs_period_str}', Valor='{obs_value_data}'. Erro: {ve_parse}")
                        continue
                
                if data_to_insert:
                    settings.logger.debug(f"EIA - Dados preparados para UPSERT para {db_indicator_name}, {len(data_to_insert)} itens.")
                    if session: # Somente insere no DB se a sessão existir
                        batch_upsert_indicator_values(session, data_to_insert)
                else:
                    settings.logger.info(f"Nenhum dado válido para inserir para {db_indicator_name} (Série Facet: {facet_series_id}).")
            
            # Delay entre o processamento de diferentes SÉRIES da EIA (configurável em settings.py)
            if config_entry_index < len(configs) - 1: # Não dormir após o último
                delay_between_series = settings.API_DELAYS.get("EIA_SERIES", 2) # Novo delay para entre séries
                settings.logger.debug(f"Aguardando {delay_between_series}s antes da próxima série EIA...")
                time.sleep(delay_between_series)
                
        settings.logger.info("Coleta de dados da EIA concluída.")

    except Exception as e_outer:
        settings.logger.error(f"Erro geral no processo de coleta da EIA: {e_outer}", exc_info=True)
    finally:
        if session:
            session.close()
            settings.logger.info("Sessão do banco de dados do EIA Collector fechada.")

if __name__ == '__main__':
    # Para executar este script isoladamente para teste:
    # 1. Certifique-se de que settings.py está configurado corretamente (especialmente EIA_API_KEY e caminhos)
    # 2. Certifique-se de que eia_indicators_config.json existe e está correto.
    # 3. Se você tem um setup de DB separado, execute-o primeiro.
    # Este script assume que as funções de db_utils (get_db_session, etc.) estão disponíveis.

    # Adicionar um logger básico se settings.logger não estiver disponível para teste isolado
    if not hasattr(settings, 'logger'):
        import logging
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
        settings.logger = logging.getLogger(__name__)
        settings.logger.info("Logger básico configurado para teste isolado de eia_collector.py")
        settings.EIA_API_KEY = os.environ.get("EIA_API_KEY_TEST", "SUA_CHAVE_AQUI_PARA_TESTE_ISOLADO") # Para teste
        settings.RAW_DATA_DIR = "./temp_eia_raw_data"
        settings.BASE_DIR = "." # Ajuste se config estiver em outro lugar relativo a este script
        CONFIG_FILE_PATH = os.path.join(settings.BASE_DIR, "config", "eia_indicators_config.json") # Re-define com base no BASE_DIR de teste
        settings.DEFAULT_REQUEST_TIMEOUT = 30
        settings.API_DELAYS = {"EIA": 1, "EIA_SERIES": 2} # Delays para teste
        settings.RUNNING_ENV = "test" # Para pular interações com DB se get_db_session retornar None

        # Mock das funções de DB para teste isolado sem DB real
        # (apenas para que o script não quebre ao tentar chamá-las se não houver sessão)
        def mock_get_db_session(): return None
        def mock_get_or_create_indicator_id(s,n,t,f,u): return 1
        def mock_batch_upsert_indicator_values(s,v): settings.logger.info(f"MOCK DB: Tentativa de upsert de {len(v)} valores.")
        def mock_get_latest_effective_date(s, id): return None
        
        if settings.RUNNING_ENV == "test":
            get_db_session = mock_get_db_session
            get_or_create_indicator_id = mock_get_or_create_indicator_id
            batch_upsert_indicator_values = mock_batch_upsert_indicator_values
            get_latest_effective_date = mock_get_latest_effective_date

    print("--- Iniciando Coletor de Dados da EIA (Execução Isolada/Teste) ---")
    collect_eia_data()
    print("--- Coletor de Dados da EIA Concluído ---")