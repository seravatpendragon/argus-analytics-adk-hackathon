from datetime import datetime
from decimal import Decimal
from dateutil.parser import parse as parse_date
from config import settings
from src.data_collection.market_data.fundamentus_collector import FundamentusCollector
from src.database.db_utils import (
    get_db_session, get_all_tickers, get_or_create_indicator_id,
    get_or_create_data_source, get_company_id_for_ticker, batch_upsert_indicator_values
)

logger = settings.logger

def collect_and_store_fundamentus_indicators() -> str:
    """
    Ferramenta final e robusta para orquestrar a coleta de dados do Fundamentus.
    """
    logger.info("Iniciando a ferramenta de coleta do PyFundamentus (vFinal-Corrigida).")
    session = get_db_session()
    try:
        tickers = get_all_tickers(session)
        if not tickers: return "Nenhum ticker encontrado no banco de dados para coleta."

        collector = FundamentusCollector()
        collected_data_by_ticker = collector.get_fundamentus_data(tickers)
        if not collected_data_by_ticker: return "Coleta concluída, mas nenhum dado novo foi retornado."

        data_to_upsert = []
        fundamentus_source_id = get_or_create_data_source(session, "Fundamentus")
        
        # Mapeia tickers para company_id uma vez para otimização
        ticker_to_company_id = {ticker: get_company_id_for_ticker(session, ticker) for ticker in tickers}

        # Loop externo: um item para cada ticker coletado
        for ticker_data in collected_data_by_ticker:
            
            ticker = ticker_data['ticker']
            company_id = ticker_to_company_id.get(ticker)
            if not company_id:
                logger.warning(f"ID da empresa não encontrado para o ticker '{ticker}'. Pulando.")
                continue

            try:
                effective_date = parse_date(ticker_data['balanco_date_str'], dayfirst=True).date()
            except (TypeError, ValueError):
                logger.warning(f"Data do balanço inválida para {ticker}. Usando data de hoje.")
                effective_date = datetime.now().date()
            
            # Loop interno: processa cada indicador para o ticker atual
            for item in ticker_data['indicators']:
                indicator_name = item['indicator']
                
                indicator_id = get_or_create_indicator_id(
                    session=session, indicator_name=indicator_name, indicator_type='Fundamentalista',
                    frequency='Trimestral', unit='Varia', econ_data_source_id=fundamentus_source_id
                )
                if not indicator_id:
                    logger.error(f"Não foi possível obter ID para o indicador '{indicator_name}' do ticker '{ticker}'.")
                    continue

                raw_value = item['value']
                numeric_value, text_value = None, str(raw_value)
                try:
                    numeric_value = float(raw_value)
                    text_value = None
                except (ValueError, TypeError):
                    pass

                data_to_upsert.append({
                    "indicator_id": indicator_id, "company_id": company_id,
                    "effective_date": effective_date, "value_numeric": numeric_value,
                    "value_text": text_value, "segment_id": None
                })
        
        if not data_to_upsert: return "Dados coletados, mas nenhum registro válido foi preparado para inserção."

        rows_affected = batch_upsert_indicator_values(session, data_to_upsert)
        session.commit()
        
        return f"Sucesso! Transação concluída. {rows_affected} indicadores do PyFundamentus inseridos/atualizados."

    except Exception as e:
        logger.critical(f"Erro crítico, revertendo a transação: {e}", exc_info=True)
        session.rollback()
        return f"Erro crítico na execução, transação revertida: {e}"
    finally:
        session.close()