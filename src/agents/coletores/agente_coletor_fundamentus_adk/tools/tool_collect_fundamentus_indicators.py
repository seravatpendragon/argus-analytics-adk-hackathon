# src/agents/coletores/agente_coletor_pyfundamentus_adk/tools/tool_collect_pyfundamentus_indicators.py

from datetime import datetime
from decimal import Decimal
from dateutil.parser import parse as parse_date
from config import settings
from src.data_collection.market_data.fundamentus_collector import FundamentusCollector
from src.database.db_utils import (
    get_db_session,
    get_all_tickers,
    get_or_create_indicator_id,
    get_or_create_data_source,
    get_company_id_for_ticker,
    batch_upsert_indicator_values
)

logger = settings.logger

def collect_and_store_fundamentus_indicators() -> str:
    """
    Ferramenta final e robusta para orquestrar a coleta de dados do Fundamentus.
    Implementa o padrão Unit of Work para garantir a integridade dos dados.
    """
    logger.info("Iniciando a ferramenta de coleta do PyFundamentus (vFinal).")
    
    # --- Início da Unidade de Trabalho ---
    session = get_db_session()
    try:
        # 1. Buscar os tickers que serão processados
        tickers = get_all_tickers(session)
        if not tickers:
            return "Nenhum ticker encontrado no banco de dados para coleta."

        # 2. Chamar o "Especialista" para coletar os dados brutos
        collector = FundamentusCollector()
        collected_data_per_ticker = collector.get_fundamentus_data(tickers)
        if not collected_data_per_ticker:
            return "Coleta concluída, mas nenhum dado novo foi retornado pelo coletor."

        # 3. Preparar os dados para o banco de dados
        data_to_upsert = []
        
        # Otimização: buscar IDs uma vez antes do loop
        fundamentus_source_id = get_or_create_data_source(session, "Fundamentus")
        ticker_to_company_id = {ticker: get_company_id_for_ticker(session, ticker) for ticker in tickers}

        logger.info(f"Processando dados para {len(collected_data_per_ticker)} tickers...")
        for ticker_data in collected_data_per_ticker:
            ticker = ticker_data['ticker']
            
            # Converte a data do balanço uma vez por ticker
            try:
                effective_date = parse_date(ticker_data['balanco_date_str'], dayfirst=True).date()
            except (TypeError, ValueError):
                logger.warning(f"Data do balanço inválida para {ticker}. Usando data de hoje como fallback.")
                effective_date = datetime.now().date()

            # Itera sobre os indicadores daquele ticker
            for item in ticker_data['indicators']:
                try:
                    indicator_name = item['indicator']
                    company_id = ticker_to_company_id.get(ticker)
                    
                    if not company_id:
                        logger.warning(f"ID da empresa não encontrado para o ticker '{ticker}'. Pulando indicador '{indicator_name}'.")
                        continue

                    indicator_id = get_or_create_indicator_id(
                        session=session,
                        indicator_name=indicator_name,
                        indicator_type='Fundamentalista',
                        frequency='Trimestral', # Baseado na origem (Balanço)
                        unit='Varia',
                        econ_data_source_id=fundamentus_source_id
                    )

                    if not indicator_id:
                        logger.error(f"Não foi possível obter o ID para o indicador '{indicator_name}'. Registro não será criado.")
                        continue
                    
                    # Lógica de conversão de valor
                    raw_value = item['value']
                    numeric_value = None
                    text_value = str(raw_value)

                    try:
                        numeric_value = float(raw_value)
                        text_value = None  # Se for um número, o texto fica nulo
                    except (ValueError, TypeError):
                        pass # Mantém o valor como texto se não for numérico

                    # Montagem final do registro
                    value_record = {
                        "indicator_id": indicator_id,
                        "company_id": company_id,
                        "effective_date": effective_date,
                        "value_numeric": numeric_value,
                        "value_text": text_value,
                        "segment_id": None
                    }
                    data_to_upsert.append(value_record)

                except KeyError as e:
                    logger.error(f"Item de dados mal formatado do coletor. Chave ausente: {e}. Item: {item}")
                    continue
        
        if not data_to_upsert:
            return "Dados coletados, mas nenhum registro válido foi preparado para inserção."

        # 4. Executar a inserção em lote (sem commit)
        rows_affected = batch_upsert_indicator_values(session, data_to_upsert)
        
        # 5. COMMIT FINAL: Salva todas as mudanças da transação de uma vez.
        session.commit()
        
        msg = f"Sucesso! Transação concluída. {rows_affected} indicadores do PyFundamentus foram inseridos/atualizados."
        logger.info(msg)
        return msg

    except Exception as e:
        logger.critical(f"!!!!!! EXCEÇÃO CAPTURADA !!!!!! Ocorreu um erro, revertendo a transação (rollback). Detalhes: {e}", exc_info=True)
        session.rollback()
        return f"Erro crítico na execução da ferramenta, transação revertida: {e}"
    finally:
        session.close()