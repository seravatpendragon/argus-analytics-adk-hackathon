from datetime import date
import json
import os
from pathlib import Path

import pandas as pd
from requests_cache import datetime, timedelta
from config import settings
from src.data_collection.macro_data.bcb_collector import BCBCollector
from src.database.db_utils import (
    get_db_session, get_latest_effective_date, get_or_create_indicator_id,
    get_or_create_data_source, batch_upsert_indicator_values
)

logger = settings.logger

# --- BLOCO DE DETECÇÃO DE CAMINHO (A CORREÇÃO) ---
try:
    # A raiz do projeto está 6 níveis acima deste arquivo
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
except NameError:
    PROJECT_ROOT = Path(os.getcwd())
# --- FIM DO BLOCO ---


def collect_and_store_bcb_indicators() -> str:
    """
    Ferramenta que lê o manifesto de coleta do BCB, busca as séries históricas
    e as persiste no banco de dados.
    """
    logger.info("Iniciando a ferramenta de coleta de indicadores do BCB (vCorrigida).")
    
    # Usa a variável PROJECT_ROOT para encontrar o manifesto
    manifest_path = PROJECT_ROOT / "config" / "bcb_indicators_config.json"
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    except FileNotFoundError:
        return f"Erro crítico: Manifesto de coleta do BCB não encontrado em {manifest_path}"

    session = get_db_session()
    try:
        collector = BCBCollector()
        bcb_source_id = get_or_create_data_source(session, "BCB-SGS")
        all_data_to_upsert = []
        
        for task in manifest:
            if not task.get("enabled", False): continue

            db_indicator_name = task['db_indicator_name']
            sgs_code = task["params"]["sgs_code"]

            indicator_id = get_or_create_indicator_id(
                session=session, indicator_name=db_indicator_name,
                indicator_type=task.get('db_indicator_type', 'Macroeconomia'),
                unit=task.get('db_indicator_unit', 'N/A'),
                frequency=task.get('db_indicator_frequency', 'Diário'),
                econ_data_source_id=bcb_source_id
            )
            if not indicator_id: continue

            # --- LÓGICA DE COLETA INCREMENTAL ---
            last_date = get_latest_effective_date(session, indicator_id)
            start_date_obj = (last_date + timedelta(days=1)) if last_date else datetime.strptime(task["params"]["initial_history_start_date"], '%Y-%m-%d').date()
            
            if start_date_obj > date.today():
                logger.info(f"Dados para '{db_indicator_name}' já estão atualizados. Pulando.")
                continue
                
            logger.info(f"Coleta incremental para '{db_indicator_name}'. Última data: {last_date}. Buscando a partir de {start_date_obj}.")
            # --- FIM DA LÓGICA ---
            
            df = collector.get_series(sgs_code, start_date_obj.strftime('%Y-%m-%d'))
            if df.empty: continue

            for _, row in df.iterrows():
                all_data_to_upsert.append({
                    "indicator_id": indicator_id, "company_id": None,
                    "effective_date": row['date'].date(),
                    "value_numeric": float(row['value']),
                    "value_text": None, "segment_id": None
                })
        
        if not all_data_to_upsert:
            return "Coleta concluída, nenhum dado novo para ser inserido."
        
        rows_affected = batch_upsert_indicator_values(session, all_data_to_upsert)
        session.commit()
        
        return f"Sucesso! {rows_affected} novos registros de indicadores do BCB inseridos/atualizados."

    except Exception as e:
        logger.critical(f"Erro crítico na ferramenta BCB, revertendo transação: {e}", exc_info=True)
        session.rollback()
        return f"Erro crítico na execução da ferramenta BCB, transação revertida: {e}"
    finally:
        session.close()