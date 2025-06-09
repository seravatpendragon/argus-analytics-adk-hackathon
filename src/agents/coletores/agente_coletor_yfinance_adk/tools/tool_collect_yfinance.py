import json
import os
from pathlib import Path
from datetime import datetime
import pandas as pd
from config import settings
from src.data_collection.market_data.yfinance_collector import YFinanceCollector
from src.database.db_utils import (
    get_db_session, get_all_tickers, get_or_create_indicator_id,
    get_or_create_data_source, get_company_id_for_ticker, batch_upsert_indicator_values
)

logger = settings.logger

# --- BLOCO DE DETECÇÃO DE CAMINHO (A CORREÇÃO) ---
try:
    # O caminho deste arquivo é: .../src/agents/coletores/agente_coletor_yfinance_adk/tools/
    # A raiz do projeto está 6 níveis acima.
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
except NameError:
    PROJECT_ROOT = Path(os.getcwd())
# --- FIM DO BLOCO ---


def collect_and_store_yfinance_indicators() -> str:
    """
    Ferramenta inteligente que lê um manifesto, busca tickers do banco
    e orquestra a coleta de dados de empresas E de indicadores macro.
    """
    logger.info("Iniciando a ferramenta de coleta do YFinance (Manifest-Driven - vFinal-Corrigida).")
    
    # Usa a variável PROJECT_ROOT que acabamos de definir
    manifest_path = PROJECT_ROOT / "config" / "yfinance_indicators_config.json"
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    except FileNotFoundError:
        return f"Erro crítico: Manifesto de coleta não encontrado em {manifest_path}"

    session = get_db_session()
    try:
        company_tickers = get_all_tickers(session)
        yfinance_source_id = get_or_create_data_source(session, "YFinance")
        ticker_to_company_id = {ticker: get_company_id_for_ticker(session, ticker) for ticker in company_tickers}
        
        all_data_to_upsert = []
        collector = YFinanceCollector()

        # --- Processar Templates para Empresas ---
        if company_tickers:
            logger.info(f"Iniciando coleta de dados para {len(company_tickers)} empresas...")
            for template in manifest.get("company_indicator_templates", []):
                data_type = template["yfinance_data_type"]
                params = template.get("params", {})
                
                raw_data_company = collector.fetch_data(company_tickers, data_type, params)
                if not raw_data_company: continue

                if data_type == "HISTORY":
                    for ticker, df in raw_data_company.items():
                        company_id = ticker_to_company_id.get(ticker)
                        if not company_id: continue
                        
                        for date, row in df.iterrows():
                            for col_name, col_config in template["value_columns"].items():
                                if col_name not in df.columns: continue
                                indicator_name = f"{ticker} {col_config['db_indicator_name_suffix']}"
                                indicator_id = get_or_create_indicator_id(session, indicator_name, col_config['db_indicator_type'], 'Diário', col_config.get('db_indicator_unit', 'N/A'), yfinance_source_id)
                                if not indicator_id: continue
                                value = row[col_name]
                                if pd.isna(value): continue
                                all_data_to_upsert.append({"indicator_id": indicator_id, "company_id": company_id, "effective_date": date.date(), "value_numeric": float(value), "value_text": None, "segment_id": None})
                
                elif data_type == "INFO":
                    today_date = datetime.now().date()
                    for ticker, info_dict in raw_data_company.items():
                        company_id = ticker_to_company_id.get(ticker)
                        if not company_id: continue
                        for field_name, field_config in template["info_fields"].items():
                            raw_value = info_dict.get(field_name)
                            if raw_value is None: continue
                            indicator_name = f"{ticker} {field_config['db_indicator_name_suffix']}"
                            indicator_id = get_or_create_indicator_id(session, indicator_name, field_config['db_indicator_type'], 'Diário', field_config.get('db_indicator_unit', 'N/A'), yfinance_source_id)
                            if not indicator_id: continue
                            numeric_value, text_value = None, str(raw_value)
                            try:
                                numeric_value = float(raw_value)
                                text_value = None
                            except (ValueError, TypeError): pass
                            all_data_to_upsert.append({"indicator_id": indicator_id, "company_id": company_id, "effective_date": today_date, "value_numeric": numeric_value, "value_text": text_value, "segment_id": None})

        # --- Processar Tarefas Macro ---
        logger.info("Iniciando coleta de dados para indicadores macro...")
        for task in manifest.get("macro_indicator_tasks", []):
            task_params = task.get("params", {})
            macro_ticker = task_params.get("ticker_symbol")
            if not macro_ticker: continue
            raw_data_macro = collector.fetch_data([macro_ticker], "HISTORY", task_params)
            if not raw_data_macro or macro_ticker not in raw_data_macro: continue
            df_macro = raw_data_macro[macro_ticker]
            value_col = task_params.get("value_column_yfinance", "Close")
            indicator_id = get_or_create_indicator_id(session, task['db_indicator_name'], 'Índice de Mercado', 'Diário', 'Pontos', yfinance_source_id)
            if not indicator_id: continue
            for date, row in df_macro.iterrows():
                value = row[value_col]
                if pd.isna(value): continue
                all_data_to_upsert.append({"indicator_id": indicator_id, "company_id": None, "effective_date": date.date(), "value_numeric": float(value), "value_text": None, "segment_id": None})

        # --- Persistir Dados ---
        if not all_data_to_upsert:
            return "Coleta concluída, mas nenhum registro válido foi preparado para inserção."
        rows_affected = batch_upsert_indicator_values(session, all_data_to_upsert)
        session.commit()
        return f"Sucesso! Transação concluída. {rows_affected} registros do YFinance inseridos/atualizados."

    except Exception as e:
        logger.critical(f"Erro crítico na ferramenta YFinance, revertendo a transação: {e}", exc_info=True)
        session.rollback()
        return f"Erro crítico na execução da ferramenta YFinance, transação revertida: {e}"
    finally:
        session.close()