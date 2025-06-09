import pandas as pd
import requests
from datetime import datetime
from config import settings

logger = settings.logger

class FREDCollector:
    """
    O "Engenheiro Especialista" para a API de dados do Federal Reserve (FRED).
    """
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("API Key para a FRED não fornecida.")
        self.api_key = api_key
        self.base_url = "https://api.stlouisfed.org/fred/series/observations"

    def get_series(self, series_id: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Busca uma série de dados do FRED para um determinado período.
        """
        logger.info(f"FREDCollector: Buscando série '{series_id}' de {start_date} até {end_date}.")
        
        api_params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": start_date,
            "observation_end": end_date,
        }
        
        try:
            response = requests.get(self.base_url, params=api_params, timeout=settings.DEFAULT_REQUEST_TIMEOUT)
            response.raise_for_status()
            response_data = response.json()

            if not response_data or not response_data.get("observations"):
                logger.info(f"Nenhuma observação encontrada na resposta do FRED para '{series_id}'.")
                return pd.DataFrame()

            df = pd.DataFrame(response_data["observations"])
            df = df[['date', 'value']] # Seleciona e ordena as colunas
            df['date'] = pd.to_datetime(df['date'])
            # FRED usa '.' para valores nulos
            df['value'] = pd.to_numeric(df['value'], errors='coerce')
            df.dropna(inplace=True)

            logger.info(f"FREDCollector: {len(df)} registros encontrados para a série '{series_id}'.")
            return df

        except requests.exceptions.HTTPError as http_err:
            logger.error(f"Erro HTTP ao buscar dados do FRED '{series_id}': {http_err}")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Erro ao processar a série '{series_id}' do FRED: {e}")
            return pd.DataFrame()