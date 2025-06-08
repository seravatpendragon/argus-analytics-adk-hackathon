from datetime import datetime
from config import settings
from src.data_collection.market_data.fundamentus_collector import FundamentusCollector
from src.database.db_utils import (
    get_db_session,
    get_all_tickers,
    get_or_create_indicator_id,
    batch_upsert_indicator_values,
    get_company_id_for_ticker
)

logger = settings.logger

def collect_and_store_fundamentus_indicators() -> str:
    """
    Orquestra a coleta de dados do Fundamentus e usa as funções de db_utils
    para garantir a criação de indicadores e a inserção em lote dos valores.
    """
    logger.info("Iniciando a ferramenta de coleta de indicadores do PyFundamentus (v2, com db_utils).")
    
    session = get_db_session()
    try:
        tickers = get_all_tickers()
        if not tickers:
            return "Nenhum ticker encontrado no banco de dados para coleta."

        collector = FundamentusCollector()
        collected_data = collector.get_fundamentus_data(tickers)
        if not collected_data:
            return "Coleta concluída, mas nenhum dado novo foi retornado pelo coletor."

        data_to_upsert = []
        today_date = datetime.now().date()

        # Mapeia tickers para company_id para evitar buscas repetidas no BD
        ticker_to_company_id = {ticker: get_company_id_for_ticker(session, ticker) for ticker in tickers}

        for item in collected_data:
            ticker = item['ticker']
            indicator_name = item['indicator']
            
            company_id = ticker_to_company_id.get(ticker)
            if not company_id:
                logger.warning(f"Não foi possível encontrar o company_id para o ticker '{ticker}'. Pulando indicador '{indicator_name}'.")
                continue

            # Garante que o indicador exista na tabela EconomicIndicators
            indicator_id = get_or_create_indicator_id(
                session=session,
                indicator_name=indicator_name,
                indicator_type='Fundamentalista', # Tipo padrão para dados do fundamentus
                frequency='Diário',
                unit='Varia' # Unidade varia dependendo do indicador
            )

            if not indicator_id:
                logger.error(f"Não foi possível criar ou obter o ID para o indicador '{indicator_name}'. Pulando.")
                continue

            # Monta o dicionário para a tabela EconomicIndicatorValues
            # O valor é salvo como texto, pois pode ser numérico ou textual (ex: '-%')
            value_record = {
                "indicator_id": indicator_id,
                "company_id": company_id,
                "segment_id": None, # Fundamentus não fornece dados por segmento
                "effective_date": today_date,
                "value_numeric": None, # Deixamos para um passo de processamento futuro converter
                "value_text": str(item['value'])
            }
            data_to_upsert.append(value_record)

        if not data_to_upsert:
            return "Dados coletados, mas nenhum registro válido foi preparado para inserção."

        # A função de batch agora só prepara a execução na sessão
        rows_affected = batch_upsert_indicator_values(session, data_to_upsert)
        
        # O COMMIT É FEITO AQUI, UMA ÚNICA VEZ!
        session.commit()
        
        msg = f"Sucesso! Transação concluída. {rows_affected} indicadores do PyFundamentus foram inseridos/atualizados."
        logger.info(msg)
        return msg

    except Exception as e:
        logger.error(f"Ocorreu um erro, revertendo a transação. Detalhes: {e}", exc_info=True)
        session.rollback() # Reverte tudo se qualquer passo falhar
        return f"Erro crítico na execução da ferramenta, transação revertida: {e}"
    finally:
        session.close()