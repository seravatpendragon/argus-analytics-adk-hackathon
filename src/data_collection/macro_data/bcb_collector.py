import pandas as pd
from datetime import datetime
from bcb import sgs
from config import settings

logger = settings.logger

class BCBCollector:
    """
    O "Engenheiro Especialista" para a API do SGS do BCB, usando
    a biblioteca 'python-bcb' e tratando corretamente os nomes das colunas.
    """
    def get_series(self, sgs_code: int, start_date_str: str) -> pd.DataFrame:
        logger.info(f"BCBCollector (python-bcb v2): Buscando série {sgs_code} a partir de {start_date_str}.")
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            
            # A biblioteca usa o nome da chave do dicionário como nome da coluna.
            # Vamos usar o próprio código da série como a chave.
            sgs_code_str = str(sgs_code)
            df = sgs.get({sgs_code_str: sgs_code}, start=start_date)
            
            if df.empty:
                logger.warning(f"Nenhum dado retornado para a série {sgs_code}.")
                return pd.DataFrame()

            # --- CORREÇÃO DO KEYERROR ---
            # Renomeia o índice (Date -> date) e a coluna de valor (ex: '432' -> 'value')
            df.reset_index(inplace=True)
            df.rename(columns={'Date': 'date', sgs_code_str: 'value'}, inplace=True)
            
            logger.info(f"BCBCollector: {len(df)} registros encontrados para a série {sgs_code}.")
            return df

        except Exception as e:
            logger.error(f"Erro ao usar a biblioteca python-bcb para a série {sgs_code}: {e}")
            return pd.DataFrame()