import fundamentus
from typing import List, Dict, Any
from config import settings

logger = settings.logger

class FundamentusCollector:
    def get_fundamentus_data(self, tickers: List[str]) -> List[Dict[str, Any]]:
        """
        Busca TODOS os dados do pyfundamentus, separando a data do balanço dos
        demais indicadores para garantir a datação correta.
        """
        logger.info(f"Iniciando PyFundamentusCollector (v7 - Lógica Simplificada)")
        
        all_tickers_data = []
        for full_ticker in tickers:
            try:
                normalized_ticker = full_ticker.split('.')[0]
                pipeline = fundamentus.Pipeline(normalized_ticker)
                response = pipeline.get_all_information()

                balanco_date_str = None
                indicators_list = []

                # Coleta todos os itens de uma vez
                all_items = [
                    item
                    for category in response.transformed_information.values() if isinstance(category, dict)
                    for item in category.values() if hasattr(item, 'title') and item.title
                ]

                # Itera uma vez, separando o que é metadado (data) do que é dado (indicadores)
                for item in all_items:
                    title = item.title.strip()
                    if title.lower() == 'último balanço':
                        balanco_date_str = item.value
                    else:
                        indicators_list.append({
                            'indicator': title,
                            'value': item.value
                        })
                
                if balanco_date_str:
                    logger.info(f"Data do balanço extraída para {full_ticker}: {balanco_date_str}")
                else:
                    logger.warning(f"Não foi possível encontrar a 'Último balanço' para {full_ticker}.")

                all_tickers_data.append({
                    "ticker": full_ticker,
                    "balanco_date_str": balanco_date_str,
                    "indicators": indicators_list
                })
            except Exception as e:
                logger.warning(f"Não foi possível buscar dados do pyfundamentus para '{full_ticker}'. Erro: {e}")
                continue

        return all_tickers_data
