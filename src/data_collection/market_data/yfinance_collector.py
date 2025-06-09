import yfinance as yf
from config import settings

logger = settings.logger

class YFinanceCollector:
    """
    O "Engenheiro Especialista" para a biblioteca yfinance.
    Sua única função é buscar os dados brutos de um tipo específico
    (HISTORY, INFO, ACTIONS) para uma lista de tickers.
    """
    def fetch_data(self, tickers: list, data_type: str, params: dict = None):
        logger.info(f"YFinanceCollector: Buscando dados do tipo '{data_type}' para {len(tickers)} tickers.")
        params = params or {}
        
        if not tickers:
            logger.warning("YFinanceCollector: Nenhuma lista de tickers fornecida.")
            return None

        data_by_ticker = {}
        for ticker_symbol in tickers:
            try:
                ticker_obj = yf.Ticker(ticker_symbol)
                
                if data_type == "HISTORY":
                    data = ticker_obj.history(period=params.get("period", "1y"))
                elif data_type == "INFO":
                    data = ticker_obj.info
                elif data_type == "ACTIONS":
                    data = ticker_obj.actions
                else:
                    logger.warning(f"Tipo de dado desconhecido para o YFinanceCollector: '{data_type}'")
                    continue
                
                if data is not None and not (hasattr(data, 'empty') and data.empty):
                    data_by_ticker[ticker_symbol] = data
                else:
                    logger.debug(f"Nenhum dado do tipo '{data_type}' retornado para o ticker {ticker_symbol}.")

            except Exception as e:
                logger.error(f"Erro ao buscar dados do yfinance para {ticker_symbol}: {e}")
                continue
                
        return data_by_ticker