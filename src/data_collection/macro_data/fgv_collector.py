# src/data_collection/macro_data/fgv_collector.py
# -*- coding: utf-8 -*-

import pandas as pd
import json
import os
from datetime import datetime, date

# Adiciona o diretório raiz do projeto ao sys.path
import sys
project_root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if project_root_path not in sys.path:
    sys.path.append(project_root_path)

try:
    from config import settings
    from src.database.db_utils import (
        get_db_session, get_or_create_indicator_id,
        batch_upsert_indicator_values
        # get_latest_effective_date não é estritamente necessário aqui,
        # pois processaremos o CSV inteiro e o UPSERT cuidará das atualizações/novas inserções.
    )
except ImportError as e:
    print(f"Erro CRÍTICO em fgv_collector.py ao importar módulos: {e}")
    sys.exit(1)

CONFIG_FILE_PATH = os.path.join(settings.BASE_DIR, "config", "fgv_indicators_config.json")
# O CSV está em data/config_input/ conforme sua informação
BASE_CSV_FOLDER_PATH = os.path.join(settings.DATA_DIR, "config_input") 

def load_manual_csv_config():
    """Carrega a configuração dos indicadores de CSV manual."""
    try:
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
            settings.logger.info(f"Configuração de CSVs manuais carregada de {CONFIG_FILE_PATH} com {len(config_data)} entradas.")
            return config_data
    except FileNotFoundError:
        settings.logger.error(f"Arquivo de configuração não encontrado: {CONFIG_FILE_PATH}")
        return []
    except json.JSONDecodeError:
        settings.logger.error(f"Erro ao decodificar JSON em: {CONFIG_FILE_PATH}")
        return []

def copy_raw_csv(original_csv_path: str, config_params: dict, indicator_name: str):
    """Copia o CSV de input para a pasta data/raw para versionamento/auditoria."""
    if not os.path.exists(original_csv_path):
        settings.logger.warning(f"Arquivo CSV original não encontrado em {original_csv_path} para {indicator_name}")
        return

    file_part = config_params.get("file_part", indicator_name.replace(" ", "_"))
    raw_data_subfolder = config_params.get("raw_data_subfolder", "manual_csv_processed") # Subpasta em data/raw
    
    dest_folder_path = os.path.join(settings.RAW_DATA_DIR, raw_data_subfolder)
    os.makedirs(dest_folder_path, exist_ok=True)
    
    dest_filename = f"{file_part}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    dest_filepath = os.path.join(dest_folder_path, dest_filename)
    
    try:
        pd.read_csv(original_csv_path).to_csv(dest_filepath, index=False) # Simplesmente copia o conteúdo
        settings.logger.info(f"Cópia do CSV manual salva em: {dest_filepath}")
    except Exception as e:
        settings.logger.error(f"Erro ao copiar CSV manual para {dest_filepath}: {e}")


def collect_fgv_data():
    """Coleta dados de CSVs manuais da FGV/CNI."""
    configs = load_manual_csv_config()
    if not configs:
        settings.logger.warning("Nenhuma configuração de indicador de CSV manual carregada. Finalizando coletor.")
        return

    session = get_db_session()
    
    # Cache para DataFrames lidos, para evitar ler o mesmo CSV múltiplas vezes se vários indicadores vierem dele
    loaded_csv_data = {}

    try:
        for config_entry_index, config in enumerate(configs):
            if not config.get("enabled", False):
                settings.logger.info(f"Indicador CSV (config ID: {config.get('indicator_config_id', 'N/A')}) desabilitado, pulando.")
                continue

            indicator_config_id = config.get('indicator_config_id')
            db_indicator_name = config.get("db_indicator_name")
            params = config.get("params", {})
            
            csv_filename = params.get("csv_filename")
            date_col_csv = params.get("date_column_name_in_csv")
            value_col_csv = params.get("value_column_name_in_csv")
            csv_date_format = params.get("csv_date_format") # Pode ser None

            if not all([indicator_config_id, db_indicator_name, csv_filename, date_col_csv, value_col_csv]):
                settings.logger.warning(f"Configuração inválida para {indicator_config_id}: campos CSV essenciais ausentes. Pulando.")
                continue
            
            settings.logger.info(f"Processando: {indicator_config_id} - '{db_indicator_name}' do arquivo '{csv_filename}'")

            indicator_id_val = get_or_create_indicator_id(
                session,
                db_indicator_name,
                config.get("db_indicator_type", "macro_national"),
                config.get("db_indicator_frequency", "M"),
                config.get("db_indicator_unit", "index_points"),
                None # econ_data_source_id - pode ser um ID para "FGV CSV" ou "CNI CSV"
            )
            if not indicator_id_val:
                settings.logger.error(f"Não foi possível obter/criar ID para o indicador '{db_indicator_name}'. Pulando CSV.")
                continue

            full_csv_path = os.path.join(BASE_CSV_FOLDER_PATH, csv_filename)

            df_csv = None
            if csv_filename in loaded_csv_data:
                df_csv = loaded_csv_data[csv_filename]
                settings.logger.debug(f"Usando CSV '{csv_filename}' do cache em memória.")
            elif os.path.exists(full_csv_path):
                try:
                    # Tenta ler com UTF-8 primeiro (que é o ideal)
                    df_csv = pd.read_csv(full_csv_path, encoding='utf-8')
                    settings.logger.debug(f"CSV '{full_csv_path}' lido com sucesso usando UTF-8.")
                except UnicodeDecodeError:
                    settings.logger.warning(f"Falha ao ler CSV '{full_csv_path}' com UTF-8. Tentando com 'latin1'...")
                    try:
                        df_csv = pd.read_csv(full_csv_path, encoding='latin1')
                        settings.logger.info(f"CSV '{full_csv_path}' lido com sucesso usando 'latin1'.")
                    except Exception as e_latin1:
                        settings.logger.error(f"Erro ao ler CSV '{full_csv_path}' com 'latin1' também: {e_latin1}")
                        continue # Pula para o próximo indicador na configuração
                except Exception as e_other:
                    settings.logger.error(f"Erro inesperado ao ler arquivo CSV '{full_csv_path}': {e_other}")
                    continue
                loaded_csv_data[csv_filename] = df_csv 
                copy_raw_csv(full_csv_path, params, db_indicator_name)
            else:
                settings.logger.warning(f"Arquivo CSV '{full_csv_path}' não encontrado. Pulando indicador '{db_indicator_name}'.")
                continue

            if df_csv is None or df_csv.empty:
                settings.logger.warning(f"DataFrame vazio para CSV '{csv_filename}'. Pulando indicador '{db_indicator_name}'.")
                continue
            
            if date_col_csv not in df_csv.columns or value_col_csv not in df_csv.columns:
                settings.logger.error(f"Colunas '{date_col_csv}' ou '{value_col_csv}' não encontradas no CSV '{csv_filename}'. Colunas disponíveis: {df_csv.columns.tolist()}. Pulando '{db_indicator_name}'.")
                continue

            data_to_insert = []
            try:
                # Tenta converter a coluna de data
                if csv_date_format:
                    df_csv[date_col_csv] = pd.to_datetime(df_csv[date_col_csv], format=csv_date_format)
                else:
                    df_csv[date_col_csv] = pd.to_datetime(df_csv[date_col_csv])
                
                # Tenta converter a coluna de valor, tratando erros
                # Em alguns locais, números podem vir com vírgula como separador decimal
                if df_csv[value_col_csv].dtype == 'object':
                    df_csv[value_col_csv] = df_csv[value_col_csv].str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
                df_csv[value_col_csv] = pd.to_numeric(df_csv[value_col_csv], errors='coerce')


                for index, row in df_csv.iterrows():
                    effective_date_val = row[date_col_csv]
                    value_num = row[value_col_csv]

                    if pd.isna(effective_date_val) or pd.isna(value_num):
                        settings.logger.debug(f"Data ou valor nulo encontrado no CSV para {db_indicator_name} na linha {index+1}. Pulando.")
                        continue
                    
                    # Garante que effective_date_val seja um objeto date do Python
                    if isinstance(effective_date_val, pd.Timestamp):
                        effective_date_val = effective_date_val.date()
                    elif not isinstance(effective_date_val, date):
                        settings.logger.warning(f"Formato de data inesperado para {db_indicator_name} na linha {index+1}: {effective_date_val}. Pulando.")
                        continue


                    data_to_insert.append({
                        "indicator_id": indicator_id_val,
                        "company_id": None, "segment_id": None, 
                        "effective_date": effective_date_val,
                        "value_numeric": float(value_num),
                        "value_text": None,
                        "collection_timestamp": datetime.now()
                    })
            except Exception as e_process:
                settings.logger.error(f"Erro ao processar linhas do CSV para {db_indicator_name}: {e_process}", exc_info=True)
                continue # Pula para o próximo indicador na configuração
                
            if data_to_insert:
                settings.logger.debug(f"CSV Manual - Dados preparados para UPSERT para {db_indicator_name}, {len(data_to_insert)} itens.")
                batch_upsert_indicator_values(session, data_to_insert)
            else:
                settings.logger.info(f"Nenhum dado válido para inserir para {db_indicator_name} após processamento do CSV.")
        
        settings.logger.info("Coleta de dados de CSVs manuais (FGV/CNI) concluída.")

    except Exception as e_outer:
        settings.logger.error(f"Erro geral no processo de coleta de CSVs manuais: {e_outer}", exc_info=True)
    finally:
        if session:
            session.close()
            settings.logger.info("Sessão do CSV Manual Collector fechada.")
