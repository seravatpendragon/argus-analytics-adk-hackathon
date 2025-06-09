import json
import os
from config import settings
from pathlib import Path
from src.data_collection.macro_data.ibge_collector import IBGECollector
from src.database.db_utils import (
    get_db_session, get_or_create_indicator_id,
    get_or_create_data_source, batch_upsert_indicator_values
)

logger = settings.logger

def collect_and_store_ibge_indicators() -> str:
    """
    Ferramenta que lê o manifesto de coleta do IBGE, passa cada tarefa
    para o coletor e persiste os resultados no banco de dados.
    """
    logger.info("Iniciando a ferramenta de coleta de indicadores do IBGE (vManifesto).")
    
    # Adicionado o path detection aqui por robustez
    try:
        PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
    except NameError:
        PROJECT_ROOT = Path(os.getcwd())
        
    manifest_path = PROJECT_ROOT / "config" / "ibge_indicators_config.json"
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    except FileNotFoundError:
        return f"Erro crítico: Manifesto de coleta do IBGE não encontrado em {manifest_path}"

    session = get_db_session()
    try:
        collector = IBGECollector()
        ibge_source_id = get_or_create_data_source(session, "IBGE-SIDRA")
        all_data_to_upsert = []
        
        for task in manifest:
            if not task.get("enabled", False): continue
            
            # O coletor agora recebe a tarefa inteira
            df = collector.get_series(task)
            if df.empty: continue

            indicator_id = get_or_create_indicator_id(
                session=session, indicator_name=task['db_indicator_name'],
                indicator_type=task.get('db_indicator_type', 'Macroeconomia'),
                unit=task.get('db_indicator_unit', 'N/A'),
                frequency=task.get('db_indicator_frequency', 'Mensal'),
                econ_data_source_id=ibge_source_id
            )
            if not indicator_id: continue

            for _, row in df.iterrows():
                all_data_to_upsert.append({
                    "indicator_id": indicator_id, "company_id": None,
                    "effective_date": row['date'].date(),
                    "value_numeric": float(row['value']),
                    "value_text": None, "segment_id": None
                })

        if not all_data_to_upsert:
            return "Coleta concluída, mas nenhum registro válido foi preparado para inserção."
        
        rows_affected = batch_upsert_indicator_values(session, all_data_to_upsert)
        session.commit()
        
        return f"Sucesso! Transação concluída. {rows_affected} registros de indicadores do IBGE inseridos/atualizados."

    except Exception as e:
        logger.critical(f"Erro crítico na ferramenta IBGE, revertendo a transação: {e}", exc_info=True)
        session.rollback()
        return f"Erro crítico na execução da ferramenta IBGE, transação revertida: {e}"
    finally:
        session.close()