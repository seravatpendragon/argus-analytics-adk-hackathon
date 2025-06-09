import json
from pathlib import Path
from datetime import datetime, date, timedelta
from config import settings
from src.data_collection.macro_data.eia_collector import EIACollector
from src.database.db_utils import (
    get_db_session, get_or_create_indicator_id, get_or_create_data_source, 
    batch_upsert_indicator_values, get_latest_effective_date
)

logger = settings.logger

def collect_and_store_eia_indicators() -> str:
    """
    Ferramenta que lê o manifesto da EIA, executa a coleta incremental e persiste os dados.
    """
    logger.info("Iniciando a ferramenta de coleta de indicadores da EIA (Incremental).")
    
    if not settings.EIA_API_KEY:
        return "Erro crítico: EIA_API_KEY não configurada em settings.py."

    try:
        PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
    except NameError:
        PROJECT_ROOT = Path.cwd()
        
    manifest_path = PROJECT_ROOT / "config" / "eia_indicators_config.json"
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    except FileNotFoundError:
        return f"Erro crítico: Manifesto de coleta da EIA não encontrado em {manifest_path}"

    session = get_db_session()
    try:
        collector = EIACollector(api_key=settings.EIA_API_KEY)
        eia_source_id = get_or_create_data_source(session, "EIA")
        all_data_to_upsert = []
        
        for task in manifest:
            if not task.get("enabled", False): continue

            params = task.get("params", {})
            series_id = params.get("facet_series_id")
            db_indicator_name = task.get("db_indicator_name")
            
            if not all([series_id, db_indicator_name]): continue

            indicator_id = get_or_create_indicator_id(
                session=session, indicator_name=db_indicator_name,
                indicator_type=task.get('db_indicator_type', 'Macroeconomia'),
                unit=task.get('db_indicator_unit', 'N/A'),
                frequency=task.get('db_indicator_frequency', 'N/A'),
                econ_data_source_id=eia_source_id
            )
            if not indicator_id: continue

            last_date = get_latest_effective_date(session, indicator_id)
            start_date_obj = (last_date + timedelta(days=1)) if last_date else datetime.strptime(params.get("initial_history_start_date", "1980-01-01"), '%Y-%m-%d').date()
            
            if start_date_obj > date.today():
                logger.info(f"Dados para '{db_indicator_name}' já estão atualizados. Pulando.")
                continue
                
            df = collector.get_series(
                route=params["api_route"],
                series_id=series_id,
                frequency=params["frequency_param_api"],
                start=start_date_obj.strftime('%Y-%m-%d'),
                end=date.today().strftime('%Y-%m-%d')
            )
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
        
        return f"Sucesso! {rows_affected} novos registros de indicadores da EIA inseridos/atualizados."

    except Exception as e:
        logger.critical(f"Erro crítico na ferramenta EIA, revertendo transação: {e}", exc_info=True)
        session.rollback()
        return f"Erro crítico na execução da ferramenta EIA, transação revertida: {e}"
    finally:
        session.close()