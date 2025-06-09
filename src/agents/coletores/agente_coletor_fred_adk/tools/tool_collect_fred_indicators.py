import json
from pathlib import Path
from datetime import datetime, date, timedelta
from config import settings
from src.data_collection.macro_data.fred_collector import FREDCollector
from src.database.db_utils import (
    get_db_session, get_or_create_indicator_id, get_or_create_data_source, 
    batch_upsert_indicator_values, get_latest_effective_date
)

logger = settings.logger

def collect_and_store_fred_indicators() -> str:
    """
    Ferramenta que lê o manifesto do FRED, executa a coleta incremental e persiste os dados.
    """
    logger.info("Iniciando a ferramenta de coleta de indicadores do FRED (Incremental).")
    
    if not settings.FRED_API_KEY:
        return "Erro crítico: FRED_API_KEY não configurada em settings.py."

    try:
        PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
    except NameError:
        PROJECT_ROOT = Path.cwd()
        
    manifest_path = PROJECT_ROOT / "config" / "fred_indicators_config.json"
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    except FileNotFoundError:
        return f"Erro crítico: Manifesto de coleta do FRED não encontrado em {manifest_path}"

    session = get_db_session()
    try:
        collector = FREDCollector(api_key=settings.FRED_API_KEY)
        fred_source_id = get_or_create_data_source(session, "FRED")
        all_data_to_upsert = []
        
        for task in manifest:
            if not task.get("enabled", False): continue

            series_id = task["params"]["series_id"]
            db_indicator_name = task["db_indicator_name"]
            
            indicator_id = get_or_create_indicator_id(
                session=session, indicator_name=db_indicator_name,
                indicator_type=task.get('db_indicator_type', 'Macroeconomia'),
                unit=task.get('db_indicator_unit', 'N/A'),
                frequency=task.get('db_indicator_frequency', 'N/A'),
                econ_data_source_id=fred_source_id
            )
            if not indicator_id: continue

            # Lógica de Coleta Incremental
            last_date = get_latest_effective_date(session, indicator_id)
            start_date_obj = (last_date + timedelta(days=1)) if last_date else datetime.strptime(task["params"]["initial_history_start_date"], '%Y-%m-%d').date()
            
            logger.info(f"Coleta incremental para '{db_indicator_name}'. Última data: {last_date}. Buscando a partir de {start_date_obj}.")
            
            df = collector.get_series(series_id, start_date_obj.strftime('%Y-%m-%d'), date.today().strftime('%Y-%m-%d'))
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
        
        return f"Sucesso! {rows_affected} novos registros de indicadores do FRED inseridos/atualizados."

    except Exception as e:
        logger.critical(f"Erro crítico na ferramenta FRED, revertendo transação: {e}", exc_info=True)
        session.rollback()
        return f"Erro crítico na execução da ferramenta FRED, transação revertida: {e}"
    finally:
        session.close()