# src/data_collection/macro_data/ibge_collector.py
# -*- coding: utf-8 -*-

import pandas as pd
import json
import os
import time
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
import calendar

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
    import sidrapy # Biblioteca para acessar a API SIDRA do IBGE
except ImportError as e:
    print(f"Erro em ibge_collector.py ao importar: {e}")
    if 'sidrapy' in str(e).lower():
        print("A biblioteca 'sidrapy' não parece estar instalada. Por favor, instale com 'pip install sidrapy'")
    if 'dateutil' in str(e).lower():
        print("A biblioteca 'python-dateutil' não parece estar instalada. Por favor, instale com 'pip install python-dateutil'")
    sys.exit(1)

CONFIG_FILE_PATH = os.path.join(settings.BASE_DIR, "config", "ibge_indicators_config.json")

def load_ibge_config():
    """Carrega a configuração dos indicadores do IBGE SIDRA do arquivo JSON."""
    try:
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        settings.logger.debug(f"Arquivo de configuração não encontrado: {CONFIG_FILE_PATH}")
        return []
    except json.JSONDecodeError:
        settings.logger.debug(f"Erro ao decodificar JSON em: {CONFIG_FILE_PATH}")
        return []

def save_raw_data_ibge(data_df, config_params, table_code_str, period_str_for_file):
    """Salva os dados brutos (pd.DataFrame) em CSV."""
    if data_df is None or data_df.empty:
        settings.logger.info(f"Dados para salvar (IBGE SIDRA Tabela {table_code_str}, período {period_str_for_file}) estão vazios. Nenhum arquivo bruto será salvo.")
        return

    folder_path = os.path.join(settings.RAW_DATA_DIR, config_params.get("raw_data_subfolder", "ibge_data"))
    os.makedirs(folder_path, exist_ok=True)
    
    file_part = config_params.get("file_part", f"sidra_{table_code_str}")
    
    safe_period_str = period_str_for_file.replace('-', '_to_').replace(' ', '_')
    filename = f"{file_part}_{safe_period_str}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    filepath = os.path.join(folder_path, filename)
    
    try:
        data_df.to_csv(filepath, index=False, encoding='utf-8-sig')
        settings.logger.info(f"Dados brutos do IBGE SIDRA salvos em: {filepath}")
    except Exception as e:
        settings.logger.debug(f"Erro ao salvar dados brutos do IBGE SIDRA em {filepath}: {e}")

def get_sidra_period_range_str_for_api(start_date_obj, end_date_obj, frequency_from_config):
    """
    Converte datas de início/fim em uma string de período (YYYYMM-YYYYMM ou YYYYQQ-YYYYQQ)
    para a API do SIDRA.
    """
    start_period_str = ""
    end_period_str = ""

    if frequency_from_config == 'M': # Mensal
        start_period_str = start_date_obj.strftime('%Y%m')
        end_period_str = end_date_obj.strftime('%Y%m')
    elif frequency_from_config == 'Q': # Trimestral
        start_quarter = (start_date_obj.month - 1) // 3 + 1
        end_quarter = (end_date_obj.month - 1) // 3 + 1
        start_period_str = f"{start_date_obj.year}{start_quarter:02d}"
        end_period_str = f"{end_date_obj.year}{end_quarter:02d}"
    else:
        raise ValueError(f"Frequência '{frequency_from_config}' não suportada para gerar período SIDRA.")
    
    return f"{start_period_str}-{end_period_str}"

def sidra_period_to_effective_date(period_code_str, frequency_from_config, period_column_name_from_df, row=None):
    """
    Converte o código do período retornado pelo SIDRA para um objeto date.
    Suporta trimestres móveis do IBGE.
    """
    try:
        period_code_str = str(period_code_str)
        year = int(period_code_str[:4])
        period_val = int(period_code_str[4:])
    except (ValueError, TypeError):
        raise ValueError(f"Formato de período inválido '{period_code_str}' da coluna '{period_column_name_from_df}'.")

    if frequency_from_config == 'M':
        # mês normal
        if 1 <= period_val <= 12:
            return date(year, period_val, 1)
        else:
            raise ValueError(f"Mês inválido '{period_val}' para frequência mensal.")
    elif frequency_from_config == 'Q':
        # Trimestre móvel: tenta extrair o mês inicial do texto, se possível
        if row is not None and 'D2N' in row:
            # Exemplo: "set-out-nov 2015"
            meses = row['D2N'].split()[0].split('-')
            mes_inicio_nome = meses[0][:3].lower()
            mes_map = {
                'jan': 1, 'fev': 2, 'mar': 3, 'abr': 4, 'mai': 5, 'jun': 6,
                'jul': 7, 'ago': 8, 'set': 9, 'out': 10, 'nov': 11, 'dez': 12
            }
            mes_inicio = mes_map.get(mes_inicio_nome)
            if mes_inicio:
                return date(year, mes_inicio, 1)
        # fallback: tenta converter como trimestre fixo
        quarter = period_val
        if 1 <= quarter <= 4:
            month = (quarter - 1) * 3 + 1
            return date(year, month, 1)
        raise ValueError(f"Não foi possível converter período '{period_code_str}' para data (trimestre móvel).")
    else:
        raise ValueError(f"Frequência '{frequency_from_config}' não suportada para converter período SIDRA para data.")

def collect_ibge_data():
    """Coleta dados de séries temporais da API SIDRA do IBGE."""
    configs = load_ibge_config()
    if not configs:
        settings.logger.warning("Nenhuma configuração de indicador do IBGE SIDRA carregada.")
        return

    session = get_db_session()
    
    try:
        for config_entry_index, config in enumerate(configs):
            if not config.get("enabled", False):
                settings.logger.info(f"Indicador IBGE {config.get('indicator_config_id', f'index_{config_entry_index}')} desabilitado, pulando.")
                continue

            indicator_config_id = config.get('indicator_config_id')
            db_indicator_name = config.get('db_indicator_name')
            db_indicator_frequency = config.get('db_indicator_frequency')
            config_params = config.get("params", {})
            table_code = config_params.get("table_code")
            initial_history_years = config_params.get("initial_history_years", 10)  # valor padrão 10 anos

            # Calcule a data inicial usando initial_history_years
            years_to_fetch = config_params.get("initial_history_years", 10)
            today = date.today()
            end_fetch_date_obj = today
            if db_indicator_frequency == 'D':
                start_fetch_date_obj = today - relativedelta(years=years_to_fetch)
            elif db_indicator_frequency == 'M':
                start_fetch_date_obj = (today - relativedelta(years=years_to_fetch)).replace(day=1)
            elif db_indicator_frequency == 'Q':
                start_fetch_date_obj = (today - relativedelta(years=years_to_fetch)).replace(day=1)
            else:
                start_fetch_date_obj = today - relativedelta(years=years_to_fetch)
            
            indicator_id_val = get_or_create_indicator_id(
                session,
                db_indicator_name,
                config.get("db_indicator_type", "macro_national"),
                db_indicator_frequency,
                config.get("db_indicator_unit", "value"),
                None
            )

            settings.logger.info(
                f"Baixando sempre os últimos {years_to_fetch} anos para '{db_indicator_name}' ({indicator_id_val}). De {start_fetch_date_obj} até {end_fetch_date_obj}."
            )

            if start_fetch_date_obj > end_fetch_date_obj:
                settings.logger.info(f"Data início {start_fetch_date_obj} > data fim {end_fetch_date_obj} para '{db_indicator_name}'. Nada a buscar.")
                continue
            
            original_period_range_str = get_sidra_period_range_str_for_api(start_fetch_date_obj, end_fetch_date_obj, db_indicator_frequency)

            # --- CORREÇÕES E TESTES INTEGRADOS ---
            geo_level_map = {"1": "1", "2": "2", "3": "3", "6": "6"}
            geo_level_config_val = config_params.get("geo_level_arg")
            
            territory_level_for_api = "1" 
            if geo_level_config_val and geo_level_config_val in geo_level_map:
                territory_level_for_api = geo_level_map[geo_level_config_val]
            elif geo_level_config_val:
                 settings.logger.warning(f"geo_level_arg '{geo_level_config_val}' não mapeado para {indicator_config_id}. Usando default '1'.")

            ibge_code_for_api = config_params.get("geo_codes_arg", "all")
            if territory_level_for_api == "1" and str(ibge_code_for_api).lower() == "all":
                ibge_code_for_api = "1"
                settings.logger.debug(f"Para territorial_level '1' (Brasil), usando ibge_territorial_code='1' para {indicator_config_id}.")

            variable_list_from_config = config_params.get("variable_arg_list")
            variable_param_for_api = None 
            if isinstance(variable_list_from_config, list) and len(variable_list_from_config) == 1:
                variable_param_for_api = variable_list_from_config[0]
                try: variable_param_for_api = int(variable_param_for_api)
                except ValueError: pass 
                settings.logger.debug(f"Usando var única '{variable_param_for_api}' (tipo: {type(variable_param_for_api)}) para API.")
            elif isinstance(variable_list_from_config, list) and len(variable_list_from_config) > 1:
                variable_param_for_api = [str(v) for v in variable_list_from_config]
                settings.logger.debug(f"Usando lista de vars {variable_param_for_api} para API.")
            elif variable_list_from_config: 
                variable_param_for_api = variable_list_from_config
                try: variable_param_for_api = int(variable_param_for_api)
                except ValueError: pass
                settings.logger.debug(f"Usando var direta '{variable_param_for_api}' do config para API.")
            else:
                settings.logger.debug(f"'variable_arg_list' ausente/inválido para {indicator_config_id}. Pulando.")
                continue
            
            
            api_call_params = {
                "table_code": str(table_code),
                "period": original_period_range_str, # Linha para RESTAURAR APÓS O TESTE
                "variable": variable_param_for_api,
                "header": "n", "format": "pandas",
                "territorial_level": territory_level_for_api,
                "ibge_territorial_code": ibge_code_for_api
            }
            if config_params.get("classifications_arg"):
                api_call_params["classifications"] = config_params.get("classifications_arg")
            # --- FIM DAS CORREÇÕES ---

            settings.logger.debug(f"Parâmetros API SIDRA para {indicator_config_id}: {json.dumps(api_call_params)}")
            
            raw_df = None
            try:
                raw_df = sidrapy.get_table(**api_call_params) 
                time.sleep(settings.API_DELAYS["IBGE"])
            except ValueError as ve:
                settings.logger.debug(f"Erro API SIDRA (Tabela {table_code}, {indicator_config_id}): {ve}", exc_info=False)
                continue
            except Exception as e:
                settings.logger.debug(f"Erro inesperado API SIDRA (Tabela {table_code}, {indicator_config_id}): {e}", exc_info=True)
                continue

            if raw_df is None or raw_df.empty:
                settings.logger.info(f"Nenhum dado retornado API SIDRA (Tabela {table_code}, {indicator_config_id}) com params: {json.dumps(api_call_params)}.")
                continue
            
            save_raw_data_ibge(raw_df, config_params, str(table_code), original_period_range_str)

            period_column_name_from_df = config_params.get("period_col_sidra", "D2C")
            value_column_name_from_df = config_params.get("value_col_sidra", "V")

            if period_column_name_from_df not in raw_df.columns or value_column_name_from_df not in raw_df.columns:
                settings.logger.debug(f"Colunas período ('{period_column_name_from_df}') ou valor ('{value_column_name_from_df}') não encontradas no DF do SIDRA (Tabela {table_code}). Cols: {raw_df.columns.tolist()}")
                continue
            
            data_dict = []
            
            def process_sidra_row(row, period_column_name, value_column_name, db_indicator_frequency, indicator_id_val):
                period_code_str = str(row[period_column_name])
                value_str = str(row[value_column_name])
                numeric_value = pd.to_numeric(value_str, errors='coerce')
                if pd.isna(numeric_value):
                    return None
                effective_dt = sidra_period_to_effective_date(period_code_str, db_indicator_frequency, period_column_name, row=row)
                return {
                    "indicator_id": indicator_id_val,
                    "company_id": None,  # Sentinel para macro
                    "segment_id": None,  # Sentinel para macro
                    "effective_date": effective_dt,
                    "value_numeric": float(numeric_value),
                    "value_text": None,
                    "collection_timestamp": datetime.now()
                }

            # No loop:
            data_list = []
            for _, row in raw_df.iterrows():
                try:
                    row_dict = process_sidra_row(row, period_column_name_from_df, value_column_name_from_df, db_indicator_frequency, indicator_id_val)
                    if row_dict:
                        data_list.append(row_dict)
                    else:
                        settings.logger.debug(f"Valor NaN ou inválido para linha: {row}")
                except Exception as e_row:
                    settings.logger.debug(f"Erro processando linha do SIDRA para Tabela {table_code}: {row}. Erro: {e_row}", exc_info=False)
                    continue

            # --- REMOVA TODO O BLOCO DE FILTRAGEM DE DUPLICATAS ABAIXO ---
            # (Remova norm_key, existing_keys, query de chaves existentes, etc.)

            # Faça apenas o upsert:
            if data_list:
                try:
                    inserted_count = batch_upsert_indicator_values(session, data_list)
                    settings.logger.info(f"{inserted_count} registros inseridos para {db_indicator_name} (Tabela: {table_code}).")
                except Exception as upsert_exc:
                    settings.logger.debug(
                        f"Erro inesperado no upsert para {db_indicator_name} (Tabela: {table_code}): {upsert_exc}",
                        exc_info=True
                    )
            else:
                settings.logger.info(f"Nenhum dado válido para inserir para {db_indicator_name} (Tabela: {table_code}) após processar {raw_df.shape[0]} linhas brutas.")

        session.commit()
        settings.logger.info("Todas as alterações pendentes da coleta IBGE foram comitadas.")
    except Exception as e_outer:
        settings.logger.debug(f"Erro geral catastrófico no processo de coleta do IBGE SIDRA: {e_outer}", exc_info=True)
        if session: session.rollback()
    finally:
        if session: session.close()
        settings.logger.info("Sessão do banco de dados (IBGE) fechada.")

    settings.logger.info("Coleta de dados do IBGE SIDRA concluída.")
