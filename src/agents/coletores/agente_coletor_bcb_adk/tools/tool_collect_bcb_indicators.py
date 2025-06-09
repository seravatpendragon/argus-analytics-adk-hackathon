import json
import os
from pathlib import Path

import pandas as pd
from config import settings
from src.data_collection.macro_data.bcb_collector import BCBCollector
from src.database.db_utils import (
    get_db_session, get_or_create_indicator_id,
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
            # Acessa o dicionário 'params' primeiro para obter os valores
            task_params = task.get("params", {})
            sgs_code = task_params.get("sgs_code")
            start_date = task_params.get("initial_history_start_date", "01/01/2010")
            
            if not sgs_code:
                logger.warning(f"Task no manifesto BCB sem 'sgs_code' em 'params': {task}")
                continue
    
            # Busca os dados da série histórica
            df = collector.get_series(sgs_code, start_date)
            if df.empty:
                logger.warning(f"Nenhum dado retornado para a série {sgs_code}, pulando.")
                continue

            indicator_id = get_or_create_indicator_id(
                session=session, indicator_name=task['db_indicator_name'],
                indicator_type=task.get('db_indicator_type', 'Macroeconomia'),
                unit=task.get('db_indicator_unit', 'N/A'),
                frequency=task.get('db_indicator_frequency', 'Diário'),
                econ_data_source_id=bcb_source_id
            )
            if not indicator_id: continue

            for _, row in df.iterrows():
                if pd.isna(row['value']): continue
                all_data_to_upsert.append({
                    "indicator_id": indicator_id,
                    "company_id": None,
                    "effective_date": row['date'].date(),
                    "value_numeric": float(row['value']),
                    "value_text": None,
                    "segment_id": None
                })

        if not all_data_to_upsert:
            return "Coleta concluída, mas nenhum registro válido foi preparado para inserção."
        
        rows_affected = batch_upsert_indicator_values(session, all_data_to_upsert)
        session.commit()
        
        return f"Sucesso! Transação concluída. {rows_affected} registros de indicadores do BCB inseridos/atualizados."

    except Exception as e:
        logger.critical(f"Erro crítico na ferramenta BCB, revertendo a transação: {e}", exc_info=True)
        session.rollback()
        return f"Erro crítico na execução da ferramenta BCB, transação revertida: {e}"
    finally:
        session.close()