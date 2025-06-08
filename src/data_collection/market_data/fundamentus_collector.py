import fundamentus
import pandas as pd
from typing import List, Dict, Any
from src.database.db_utils import get_db_connection, get_assets_by_source
from src.utils.logging_config import setup_logging

logger = setup_logging(__name__)

class FundamentusCollector:
    """
    O "Engenheiro Especialista" para dados do pyfundamentus.

    Esta classe é responsável pela lógica de baixo nível:
    1. Chamar a biblioteca pyfundamentus.
    2. Receber a lista de tickers a serem buscados.
    3. Formatar os dados brutos no padrão esperado pela tabela EconomicIndicatorValues.
    """
    def __init__(self):
        logger.info("FundamentusCollector instanciado.")

    def get_fundamentus_data(self, tickers: List[str]) -> List[Dict[str, Any]]:
        """
        Busca dados fundamentalistas para uma lista de tickers.
        """
        logger.info(f"Buscando dados fundamentalistas para {len(tickers)} tickers.")
        all_indicators = []
        
        for ticker in tickers:
            try:
                # O pyfundamentus retorna um dicionário de dicionários
                # {'papel': 'VALE3', 'cotacao': '61.7', ...}
                raw_data = fundamentus.get_papel(ticker)
                
                # Transforma o dicionário em um DataFrame para facilitar a manipulação
                df = pd.DataFrame.from_dict(raw_data, orient='index', columns=['value'])
                df.reset_index(inplace=True)
                df.rename(columns={'index': 'indicator'}, inplace=True)
                
                df['ticker'] = ticker
                df['source'] = 'Fundamentus'
                df['collected_at'] = pd.to_datetime('today').strftime('%Y-%m-%d')
                
                # Remove o próprio ticker da lista de indicadores para evitar redundância
                df = df[df['indicator'] != 'papel']
                
                # Converte para o formato de dicionário esperado
                indicators = df.to_dict('records')
                all_indicators.extend(indicators)
                logger.debug(f"Dados para {ticker} processados com sucesso.")
                
            except Exception as e:
                logger.error(f"Erro ao buscar dados para o ticker {ticker}: {e}")
                continue # Pula para o próximo ticker em caso de erro

        logger.info(f"Total de {len(all_indicators)} indicadores coletados da Fundamentus.")
        return all_indicators