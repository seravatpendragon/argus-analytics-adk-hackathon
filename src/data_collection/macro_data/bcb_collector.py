# src/data_collection/macro_data/bcb_collector.py
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
        batch_upsert_indicator_values, get_latest_effective_date
    )
    from bcb import sgs # Biblioteca para acessar o SGS do BCB
except ImportError as e:
    # O logger pode não estar configurado se settings falhar
    print(f"Erro em bcb_collector.py ao importar: {e}")
    sys.exit(1)
except ModuleNotFoundError:
    print("Erro: A biblioteca 'python-bcb' não está instalada. Por favor, instale com 'pip install python-bcb'")
    sys.exit(1)

CONFIG_FILE_PATH = os.path.join(settings.BASE_DIR, "config", "bcb_indicators_config.json")

def load_bcb_config():
    """Carrega a configuração dos indicadores do BCB do arquivo JSON."""
    try:
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        settings.logger.error(f"Arquivo de configuração não encontrado: {CONFIG_FILE_PATH}")
        return []
    except json.JSONDecodeError:
        settings.logger.error(f"Erro ao decodificar JSON em: {CONFIG_FILE_PATH}")
        return []

def save_raw_data_bcb(data_series_or_df, config_params, sgs_code_str, start_date_str):
    """Salva os dados brutos em CSV."""
    if data_series_or_df is None or data_series_or_df.empty:
        settings.logger.info(f"Dados para salvar (BCB SGS {sgs_code_str} a partir de {start_date_str}) estão vazios. Nenhum arquivo bruto será salvo.")
        return

    folder_path = os.path.join(settings.RAW_DATA_DIR, config_params.get("raw_data_subfolder", "bcb_data_default"))
    os.makedirs(folder_path, exist_ok=True)
    
    file_part = config_params.get("file_part", f"sgs_{sgs_code_str}")
    # Para dados incrementais, o nome pode refletir o período, mas para simplicidade, usamos data da coleta.
    # Se for histórico completo, pode indicar isso.
    filename_suffix = start_date_str.replace("-","") if start_date_str else "fullhistory"
    filename = f"{file_part}_{filename_suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    filepath = os.path.join(folder_path, filename)
    
    try:
        if isinstance(data_series_or_df, (pd.DataFrame, pd.Series)):
            data_series_or_df.to_csv(filepath, header=True) # Inclui header para clareza do CSV
        settings.logger.info(f"Dados brutos do BCB salvos em: {filepath}")
    except Exception as e:
        settings.logger.error(f"Erro ao salvar dados brutos do BCB em {filepath}: {e}")


def collect_bcb_data():
    """Coleta dados de séries temporais do SGS do Banco Central do Brasil."""
    configs = load_bcb_config()
    if not configs:
        settings.logger.warning("Nenhuma configuração de indicador do BCB carregada.")
        return

    session = get_db_session()

    try:
        for config_entry_index, config in enumerate(configs):
            if not config.get("enabled", False):
                settings.logger.info(f"Indicador BCB {config.get('indicator_config_id')} desabilitado, pulando.")
                continue

            indicator_config_id = config.get('indicator_config_id', f"bcb_unknown_config_{config_entry_index}")
            db_indicator_name = config.get('db_indicator_name')
            params = config.get("params", {})
            sgs_code = params.get("sgs_code")

            if not db_indicator_name or sgs_code is None:
                settings.logger.warning(f"Configuração inválida para {indicator_config_id}: db_indicator_name ou sgs_code ausentes. Pulando.")
                continue

            settings.logger.info(f"Processando: {indicator_config_id} - {db_indicator_name} (SGS: {sgs_code})")

            indicator_id_val = get_or_create_indicator_id(
                session,
                db_indicator_name,
                config.get("db_indicator_type", "macro_national"),
                config.get("db_indicator_frequency", "D"),
                config.get("db_indicator_unit", "value"),
                None
            )
            if not indicator_id_val:
                settings.logger.error(f"Não foi possível obter/criar ID para o indicador '{db_indicator_name}'. Pulando coleta para SGS {sgs_code}.")
                continue

            last_recorded_date = get_latest_effective_date(session, indicator_id_val)
            start_date_for_download_str = params.get("initial_history_start_date", "1970-01-01")
            is_incremental_fetch = False
            if last_recorded_date:
                start_date_for_download_obj = last_recorded_date + timedelta(days=1)
                start_date_for_download_str = start_date_for_download_obj.strftime('%Y-%m-%d')
                is_incremental_fetch = True
                settings.logger.info(f"Última data para '{db_indicator_name}' no BD: {last_recorded_date}. Buscando a partir de {start_date_for_download_str}.")
            else:
                settings.logger.info(f"Nenhum dado anterior para '{db_indicator_name}' no BD. Buscando histórico completo desde {start_date_for_download_str}.")

            end_date_for_download_str = date.today().strftime('%Y-%m-%d')
            settings.logger.debug(f"Período de busca para SGS {sgs_code}: Início='{start_date_for_download_str}', Fim='{end_date_for_download_str}'")

            if pd.to_datetime(start_date_for_download_str).date() > date.today() and is_incremental_fetch:
                settings.logger.info(f"Data de início {start_date_for_download_str} é futura para '{db_indicator_name}'. Nenhum dado novo para buscar.")
                continue

            fetched_data_series = None
            try:
                settings.logger.debug(f"Buscando BCB SGS {sgs_code} de {start_date_for_download_str} até {end_date_for_download_str}...")
                fetched_data_series = sgs.get(sgs_code, start=start_date_for_download_str, end=end_date_for_download_str)
                time.sleep(settings.API_DELAYS["BCB"])

                if isinstance(fetched_data_series, pd.Series) and not fetched_data_series.empty:
                    fetched_data = fetched_data_series.to_frame(name=str(sgs_code))
                elif isinstance(fetched_data_series, pd.DataFrame) and not fetched_data_series.empty:
                    fetched_data = fetched_data_series
                else:
                    settings.logger.info(f"Nenhum dado novo retornado pela API do BCB para SGS {sgs_code} no período.")
                    fetched_data = None

                if fetched_data is not None and not fetched_data.empty:
                    save_raw_data_bcb(fetched_data, params, str(sgs_code), start_date_for_download_str)

            except Exception as e:
                settings.logger.error(f"Erro ao buscar dados do BCB SGS {sgs_code} para '{db_indicator_name}': {e}")
                continue

            if fetched_data is not None and not fetched_data.empty:
                data_dict = []
                column_name_from_sgs = str(sgs_code)
                if column_name_from_sgs not in fetched_data.columns:
                    if fetched_data_series.name == sgs_code:
                        series_to_process = fetched_data_series.dropna()
                    else:
                        settings.logger.warning(
                            f"Coluna inesperada ou nome da série para SGS {sgs_code} no DataFrame/Series retornado. "
                            f"Esperado: '{column_name_from_sgs}' ou nome da série igual ao código. Encontrado: "
                            f"{fetched_data.columns if isinstance(fetched_data, pd.DataFrame) else fetched_data_series.name if isinstance(fetched_data_series, pd.Series) else 'N/A'}"
                        )
                        continue
                else:
                    series_to_process = fetched_data[column_name_from_sgs].dropna()

                if not isinstance(series_to_process.index, pd.DatetimeIndex):
                    settings.logger.error(f"Índice para SGS {sgs_code} não é DatetimeIndex! Tipo: {type(series_to_process.index)}. Pulando indicador.")
                    continue

                for index_date, value in series_to_process.items():
                    if not isinstance(index_date, pd.Timestamp):
                        settings.logger.warning(f"Item de índice inesperado: {index_date} (tipo: {type(index_date)}) para SGS {sgs_code}. Pulando esta entrada.")
                        continue
                    if pd.isna(value):
                        settings.logger.debug(f"Valor NaN encontrado para SGS {sgs_code} em {index_date.date()}. Pulando.")
                        continue

                    data_dict.append({
                        "indicator_id": indicator_id_val,
                        "company_id":None,
                        "segment_id": None,
                        "effective_date": index_date.date(),
                        "value_numeric": float(value),
                        "value_text": None,
                        "collection_timestamp": datetime.now()
                    })

                if data_dict:
                    batch_upsert_indicator_values(session, data_dict)
                    settings.logger.info(f"{len(data_dict)} registros enviados para EconomicIndicatorValues. Inseridos: {len(data_dict)}")
                else:
                    settings.logger.info(f"Nenhum dado válido para inserir para {db_indicator_name} após processamento.")
            else:
                settings.logger.info(f"Nenhum dado bruto para processar para {db_indicator_name} (SGS: {sgs_code}).")

        settings.logger.info("Coleta de dados do BCB (SGS) concluída.")

    except Exception as e_outer:
        settings.logger.error(f"Erro geral no processo de coleta do BCB: {e_outer}", exc_info=True)
        if session:
            session.rollback()
    finally:
        if session:
            session.close()

