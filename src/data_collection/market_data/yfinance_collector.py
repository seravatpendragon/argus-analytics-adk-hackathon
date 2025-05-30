# src/data_collection/market_data/yfinance_collector.py
# -*- coding: utf-8 -*-

import pandas as pd
import json
import os
import time
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
        batch_upsert_indicator_values, get_company_id_for_ticker,
        get_latest_effective_date
    )
    # Importar o modelo EconomicIndicatorValue se precisar fazer a query de verificação explícita aqui
    # from src.database.create_db_tables import EconomicIndicatorValue 
    import yfinance as yf
except ImportError as e:
    print(f"Erro CRÍTICO em yfinance_collector.py ao importar módulos: {e}")
    sys.exit(1)
except ModuleNotFoundError:
    print("Erro: A biblioteca 'yfinance' não está instalada. Por favor, instale com 'pip install yfinance'")
    sys.exit(1)

CONFIG_FILE_PATH = os.path.join(settings.BASE_DIR, "config", "yfinance_indicators_config.json")

def load_yfinance_config():
    """Carrega a configuração dos indicadores yfinance do arquivo JSON."""
    try:
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
            settings.logger.info(f"Configuração yfinance carregada de {CONFIG_FILE_PATH} com {len(config_data)} entradas.")
            return config_data
    except FileNotFoundError:
        settings.logger.error(f"Arquivo de configuração não encontrado: {CONFIG_FILE_PATH}")
        return []
    except json.JSONDecodeError:
        settings.logger.error(f"Erro ao decodificar JSON em: {CONFIG_FILE_PATH}")
        return []

def save_raw_data_yfinance(data_to_save, config_params: dict, data_type_suffix:str =""):
    """Salva os dados brutos em CSV ou JSON."""
    if data_to_save is None:
        settings.logger.info(f"Dados para salvar ({config_params.get('ticker_symbol', 'N/A')}_{data_type_suffix}) são None. Nenhum arquivo bruto será salvo.")
        return
    
    is_empty = False
    if isinstance(data_to_save, pd.DataFrame): is_empty = data_to_save.empty
    elif isinstance(data_to_save, pd.Series): is_empty = data_to_save.empty
    elif isinstance(data_to_save, dict): is_empty = not bool(data_to_save)
    
    if is_empty:
        settings.logger.info(f"Dados para salvar ({config_params.get('ticker_symbol', 'N/A')}_{data_type_suffix}) estão vazios. Nenhum arquivo bruto será salvo.")
        return

    folder_path = os.path.join(settings.RAW_DATA_DIR, config_params.get("raw_data_subfolder", "yfinance_default"))
    os.makedirs(folder_path, exist_ok=True)
    
    filename_base = config_params.get("ticker_symbol", "data").replace("^", "") # Remove ^ de tickers como ^BVSP
    if data_type_suffix: filename_base += f"_{data_type_suffix}"
    
    filename_ext = ".json" if isinstance(data_to_save, dict) else ".csv"
    # Adiciona timestamp ao nome do arquivo para evitar sobrescrita e ter histórico de coletas
    filename = f"{filename_base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{filename_ext}"
    filepath = os.path.join(folder_path, filename)
    
    try:
        if isinstance(data_to_save, (pd.DataFrame, pd.Series)):
            data_to_save.to_csv(filepath, header=True, index_label="date")
        elif isinstance(data_to_save, dict):
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=4, ensure_ascii=False)
        settings.logger.info(f"Dados brutos do yfinance salvos em: {filepath}")
    except Exception as e:
        settings.logger.error(f"Erro ao salvar dados brutos do yfinance em {filepath}: {e}")


def collect_yfinance_data():
    """Coleta dados do Yahoo Finance conforme configuração e salva no banco."""
    configs = load_yfinance_config()
    if not configs:
        settings.logger.warning("Nenhuma configuração de indicador yfinance carregada. Finalizando coletor yfinance.")
        return

    session = get_db_session()
    # Caches em memória para a execução atual do script
    yf_ticker_info_cache = {}
    yf_ticker_history_cache = {}
    yf_ticker_dividends_cache = {}
    yf_ticker_splits_cache = {}

    try:
        for config_entry_index, config in enumerate(configs):
            if not config.get("enabled", False):
                settings.logger.info(f"Indicador yfinance (config ID: {config.get('indicator_config_id', 'N/A')}) desabilitado, pulando.")
                continue

            indicator_config_id = config.get('indicator_config_id', f"yf_unknown_config_{config_entry_index}")
            db_indicator_name = config.get('db_indicator_name')
            params = config.get("params", {})
            ticker_symbol = params.get("ticker_symbol")
            yfinance_data_type = config.get("yfinance_data_type")

            if not db_indicator_name or not ticker_symbol or not yfinance_data_type:
                settings.logger.warning(f"Configuração inválida para {indicator_config_id}: db_indicator_name, ticker_symbol ou yfinance_data_type ausentes. Pulando.")
                continue
            
            settings.logger.info(f"Processando: {indicator_config_id} - '{db_indicator_name}' (Ticker: {ticker_symbol})")

            company_id = None
            data_category = config.get("data_category", "")
            db_indicator_type = config.get("db_indicator_type", "unknown_type")

            if data_category.startswith("company_"):
                company_id = get_company_id_for_ticker(session, ticker_symbol)
                if not company_id and db_indicator_type.startswith("company_"):
                    settings.logger.error(f"Pulando {db_indicator_name} para {ticker_symbol} pois company_id é crucial e não foi encontrado.")
                    continue
                elif not company_id:
                     settings.logger.warning(f"Não foi possível obter company_id para {ticker_symbol} (indicador {db_indicator_name}). Dados não serão associados a uma empresa específica, o que pode ser um erro para este tipo de indicador.")


            data_to_insert_for_batch = []
            
            indicator_id_val = get_or_create_indicator_id(
                session, db_indicator_name, db_indicator_type,
                config.get("db_indicator_frequency", "D"), 
                config.get("db_indicator_unit", "value")
            )
            if not indicator_id_val:
                settings.logger.error(f"Não foi possível obter/criar ID para o indicador '{db_indicator_name}'. Pulando coleta para este config.")
                continue

            if yfinance_data_type == "HISTORY":
                column_from_config = params.get("value_column_yfinance")
                if not column_from_config:
                    settings.logger.warning(f"value_column_yfinance não definido para {indicator_config_id} (HISTORY), pulando.")
                    continue
                
                series_company_id_for_history = company_id if db_indicator_type.startswith("company_") else None
                last_recorded_date = get_latest_effective_date(session, indicator_id_val, company_id_to_check=series_company_id_for_history)
                
                start_date_for_download_obj = pd.to_datetime(params.get("initial_history_start_date", "1970-01-01")).date()
                is_incremental_fetch = False
                if last_recorded_date:
                    start_date_for_download_obj = last_recorded_date + timedelta(days=1)
                    is_incremental_fetch = True
                    settings.logger.info(f"Última data para '{db_indicator_name}' (EntidadeID: {series_company_id_for_history}) no BD: {last_recorded_date}. Buscando a partir de {start_date_for_download_obj.strftime('%Y-%m-%d')}.")
                else:
                    settings.logger.info(f"Nenhum dado anterior para '{db_indicator_name}' (EntidadeID: {series_company_id_for_history}) no BD. Buscando histórico completo desde {start_date_for_download_obj.strftime('%Y-%m-%d')}.")

                end_date_for_download_obj = date.today() + timedelta(days=1) # Inclui o dia atual

                if start_date_for_download_obj >= end_date_for_download_obj and is_incremental_fetch:
                    settings.logger.info(f"Data de início {start_date_for_download_obj.strftime('%Y-%m-%d')} é igual ou posterior à data final para {ticker_symbol}. Nenhum dado novo para buscar para '{db_indicator_name}'.")
                else:
                    cache_key = f"{ticker_symbol}_{start_date_for_download_obj.strftime('%Y%m%d')}_{end_date_for_download_obj.strftime('%Y%m%d')}"
                    if cache_key not in yf_ticker_history_cache:
                        try:
                            settings.logger.info(f"Baixando dados históricos para {ticker_symbol} de {start_date_for_download_obj.strftime('%Y-%m-%d')} até {end_date_for_download_obj.strftime('%Y-%m-%d')}...")
                            downloaded_df = yf.download(ticker_symbol, start=start_date_for_download_obj, end=end_date_for_download_obj, progress=False, auto_adjust=True)
                            yf_ticker_history_cache[cache_key] = downloaded_df
                            time.sleep(settings.API_DELAYS["YFINANCE"])
                            save_raw_data_yfinance(downloaded_df, params, f"history_from_{start_date_for_download_obj.strftime('%Y%m%d')}")
                        except Exception as e:
                            settings.logger.error(f"Erro ao baixar dados históricos para {ticker_symbol}: {e}")
                            yf_ticker_history_cache[cache_key] = pd.DataFrame()
                    
                    data_df = yf_ticker_history_cache.get(cache_key)

                    if data_df is not None and not data_df.empty:
                        series_to_process = None
                        # Lógica para acessar a coluna correta (simples ou MultiIndex)
                        if isinstance(data_df.columns, pd.MultiIndex):
                            if (column_from_config, ticker_symbol) in data_df.columns:
                                series_to_process = data_df[(column_from_config, ticker_symbol)].dropna()
                            # Adicionar mais fallbacks para MultiIndex se necessário, ou logar colunas disponíveis
                            else:
                                settings.logger.warning(f"Coluna MultiIndex ('{column_from_config}', '{ticker_symbol}') não encontrada para {ticker_symbol}. Colunas: {list(data_df.columns)}. Pulando '{db_indicator_name}'.")
                        elif column_from_config in data_df.columns:
                            series_to_process = data_df[column_from_config].dropna()
                        else:
                            settings.logger.warning(f"Coluna '{column_from_config}' não encontrada para {ticker_symbol} (Índice Simples). Colunas: {list(data_df.columns)}. Pulando '{db_indicator_name}'.")

                        if series_to_process is not None and not series_to_process.empty:
                            if not isinstance(series_to_process.index, pd.DatetimeIndex):
                                settings.logger.error(f"Índice para {ticker_symbol}, coluna '{column_from_config}', não é DatetimeIndex! Tipo: {type(series_to_process.index)}. Pulando.")
                            else:
                                for index_date_ts, row_value in series_to_process.items():
                                    if not isinstance(index_date_ts, pd.Timestamp):
                                        settings.logger.warning(f"Item de índice inesperado: {index_date_ts} (tipo: {type(index_date_ts)}) para {ticker_symbol}, coluna {column_from_config}. Pulando.")
                                        continue
                                    if pd.isna(row_value): continue

                                    data_to_insert_for_batch.append({
                                        "indicator_id": indicator_id_val, 
                                        "company_id": series_company_id_for_history,
                                        "segment_id": None,
                                        "effective_date": index_date_ts.date(), 
                                        "value_numeric": float(row_value),
                                        "value_text": None, 
                                        "collection_timestamp": datetime.now()
                                    })
                        else:
                             settings.logger.info(f"Nenhuma série de dados para processar para {ticker_symbol}, coluna {column_from_config} (indicador '{db_indicator_name}').")
                    else:
                        settings.logger.info(f"Nenhum dado novo retornado por yfinance para {ticker_symbol} no período para '{db_indicator_name}'.")


            elif yfinance_data_type == "INFO":
                field_to_extract = params.get("value_field_yfinance_info")
                if not field_to_extract:
                    settings.logger.warning(f"value_field_yfinance_info não definido para {indicator_config_id} (INFO), pulando.")
                    continue

                if ticker_symbol not in yf_ticker_info_cache:
                    try:
                        settings.logger.info(f"Buscando .info() para {ticker_symbol}...")
                        yf_ticker_info_cache[ticker_symbol] = yf.Ticker(ticker_symbol).info
                        time.sleep(settings.API_DELAYS["YFINANCE"])
                        save_raw_data_yfinance(yf_ticker_info_cache[ticker_symbol], params, "info")
                    except Exception as e:
                        settings.logger.error(f"Erro ao buscar .info() para {ticker_symbol}: {e}")
                        yf_ticker_info_cache[ticker_symbol] = {}
                
                info_data = yf_ticker_info_cache[ticker_symbol]

                if info_data and field_to_extract in info_data and info_data[field_to_extract] is not None:
                    value_num = None
                    try:
                        value_num = float(info_data[field_to_extract])
                    except (ValueError, TypeError):
                        settings.logger.warning(f"Não foi possível converter o valor '{info_data[field_to_extract]}' do campo {field_to_extract} para float para {ticker_symbol}. Pulando.")
                        continue
                    
                    data_to_insert_for_batch.append({
                        "indicator_id": indicator_id_val, 
                        "company_id": company_id,
                        "segment_id": None, 
                        "effective_date": date.today(), 
                        "value_numeric": value_num, 
                        "value_text": None, 
                        "collection_timestamp": datetime.now()
                    })
                else:
                    settings.logger.warning(f"Campo {field_to_extract} não encontrado, nulo ou info_data vazio em .info() para {ticker_symbol} ({db_indicator_name}).")
            
            elif yfinance_data_type in ["DIVIDENDS", "SPLITS"]:
                series_data = None
                cache_to_use = yf_ticker_dividends_cache if yfinance_data_type == "DIVIDENDS" else yf_ticker_splits_cache
                data_type_suffix_raw = "dividends" if yfinance_data_type == "DIVIDENDS" else "splits"

                if ticker_symbol not in cache_to_use:
                    try:
                        settings.logger.info(f"Buscando {data_type_suffix_raw} para {ticker_symbol}...")
                        if yfinance_data_type == "DIVIDENDS":
                            cache_to_use[ticker_symbol] = yf.Ticker(ticker_symbol).dividends
                        else: # SPLITS
                            cache_to_use[ticker_symbol] = yf.Ticker(ticker_symbol).splits
                        time.sleep(settings.API_DELAYS["YFINANCE"])
                        save_raw_data_yfinance(cache_to_use[ticker_symbol], params, data_type_suffix_raw)
                    except Exception as e:
                        settings.logger.error(f"Erro ao buscar {data_type_suffix_raw} para {ticker_symbol}: {e}")
                        cache_to_use[ticker_symbol] = pd.Series(dtype=float) # Retorna Série vazia em caso de erro
                series_data = cache_to_use[ticker_symbol]

                if series_data is not None and not series_data.empty:
                    for index_date_ts, value in series_data.items():
                        if not isinstance(index_date_ts, pd.Timestamp) or pd.isna(value): continue
                        effective_date_val = index_date_ts.date()
                        
                        data_to_insert_for_batch.append({
                            "indicator_id": indicator_id_val, 
                            "company_id": company_id,
                            "segment_id": None,
                            "effective_date": effective_date_val, 
                            "value_numeric": float(value),
                            "value_text": f"Split ratio: {value}" if yfinance_data_type == "SPLITS" else None,
                            "collection_timestamp": datetime.now()
                        })
                else:
                    settings.logger.info(f"Nenhuma série de dados para {yfinance_data_type} de {ticker_symbol} ({db_indicator_name}).")

            # Enviar para o batch_upsert APÓS processar cada config individualmente
            if data_to_insert_for_batch:
                # Log de DEBUG DETALHADO (se habilitado e necessário para este config_id)
                if indicator_config_id in ["YF_PETR4_MARKETCAP", "YF_PETR4_DIVIDENDS"]: # Exemplo
                    settings.logger.info(f"DEBUG DETALHADO para {db_indicator_name} ({indicator_config_id}):")
                    for i, item_dict in enumerate(data_to_insert_for_batch[:3]): # Primeiros 3 itens
                        log_entry = {k: item_dict.get(k) for k in ['indicator_id', 'effective_date', 'company_id', 'segment_id', 'value_numeric']}
                        settings.logger.info(f"  Item {i} para UPSERT: {log_entry}")
                        settings.logger.info(f"    Tipos: indicator_id({type(item_dict.get('indicator_id'))}), "
                                             f"effective_date({type(item_dict.get('effective_date'))}), "
                                             f"company_id({type(item_dict.get('company_id'))}), "
                                             f"segment_id({type(item_dict.get('segment_id'))})")

                batch_upsert_indicator_values(session, data_to_insert_for_batch)
            else:
                settings.logger.info(f"Nenhum dado novo ou para atualizar preparado para o indicador {db_indicator_name} ({indicator_config_id}) após todas as verificações.")
        
        session.commit() # Commit final da sessão após processar todos os indicadores no loop
        settings.logger.info("Coleta de dados yfinance concluída.")

    except Exception as e_outer:
        settings.logger.error(f"Erro geral no processo de coleta yfinance: {e_outer}", exc_info=True)
        if session: # Garante que a sessão não esteja None
            session.rollback()
    finally:
        if session: # Garante que a sessão não esteja None
            session.close()
            settings.logger.info("Sessão do yfinance Collector fechada.")

if __name__ == '__main__':
    settings.logger.info("Iniciando execução direta do yfinance_collector.py para teste...")
    # Garanta que a PETR4.SA exista na tabela Companies com o ID correto antes de rodar.
    # Você pode adicionar uma lógica de verificação/criação aqui ou usar o asset_loader.py separadamente.
    collect_yfinance_data()
    settings.logger.info("Execução direta do yfinance_collector.py finalizada.")