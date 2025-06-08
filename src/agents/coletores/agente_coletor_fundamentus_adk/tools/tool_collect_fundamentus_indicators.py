from datetime import datetime
from decimal import Decimal
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
        collected_data = collector.get_fundamentus_data(tickers)
        if not collected_data:
            return "Coleta concluída, mas nenhum dado novo foi retornado pelo coletor."

        # 3. Preparar os dados para o banco de dados
        data_to_upsert = []
        today_date = datetime.now().date()

        # Otimização: buscar IDs uma vez antes do loop
        fundamentus_source_id = get_or_create_data_source(session, "Fundamentus")
        ticker_to_company_id = {ticker: get_company_id_for_ticker(session, ticker) for ticker in tickers}

        logger.info(f"Processando {len(collected_data)} indicadores coletados...")
        for item in collected_data:
            try:
                indicator_name = item['indicator']
                ticker = item['ticker']
                
                company_id = ticker_to_company_id.get(ticker)
                if not company_id:
                    logger.warning(f"ID da empresa não encontrado para o ticker '{ticker}'. Pulando indicador '{indicator_name}'.")
                    continue

                indicator_id = get_or_create_indicator_id(
                    session=session,
                    indicator_name=indicator_name,
                    indicator_type='Fundamentalista',
                    frequency='Diário',
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
                except (ValueError, TypeError):
                    logger.debug(f"Valor '{text_value}' para o indicador '{indicator_name}' não é numérico.")

                # Montagem final do registro
                value_record = {
                    "indicator_id": indicator_id,
                    "company_id": company_id,
                    "segment_id": None,
                    "effective_date": today_date,
                    "value_numeric": numeric_value,
                    "value_text": text_value
                }
                data_to_upsert.append(value_record)

            except KeyError as e:
                logger.error(f"Item de dados mal formatado do coletor. Chave ausente: {e}. Item: {item}")
                continue

        if not data_to_upsert:
            return "Dados coletados, mas nenhum registro válido foi preparado para inserção."

        # 4. Executar a inserção em lote (sem commit)
        logger.info(f"Preparados {len(data_to_upsert)} registros para o banco. Executando batch upsert...")
        rows_affected = batch_upsert_indicator_values(session, data_to_upsert)
        
        # 5. COMMIT FINAL: Salva todas as mudanças da transação de uma vez.
        logger.info(f"Batch upsert reportou {rows_affected} linhas. Realizando o COMMIT da transação...")
        session.commit()
        logger.info("<<<<< COMMIT REALIZADO COM SUCESSO! >>>>>")
        
        msg = f"Sucesso! Transação concluída. {rows_affected} indicadores do PyFundamentus foram inseridos/atualizados."
        return msg

    except Exception as e:
        logger.critical(f"!!!!!! EXCEÇÃO CAPTURADA !!!!!! Ocorreu um erro, revertendo a transação (rollback). Detalhes: {e}", exc_info=True)
        session.rollback()
        return f"Erro crítico na execução da ferramenta, transação revertida: {e}"
    finally:
        logger.info("Fechando a sessão do banco de dados.")
        session.close()