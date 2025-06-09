import pandas as pd
import requests
from datetime import datetime
from config import settings
import time

logger = settings.logger

class EIACollector:
    """
    O "Engenheiro Especialista" para a API v2 de dados da U.S. Energy Information Administration (EIA).
    """
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("API Key para a EIA não fornecida.")
        self.api_key = api_key
        self.base_url = "https://api.eia.gov/v2"

    def get_series(self, route: str, series_id: str, frequency: str, start: str, end: str) -> pd.DataFrame:
        """
        Busca uma série de dados completa da EIA, lidando com a paginação.
        """
        url = f"{self.base_url}{route}/data/"
        logger.info(f"EIACollector: Buscando série '{series_id}' de {start} até {end}.")
        
        all_observations = []
        offset = 0
        page_length = 5000

        while True:
            params = {
                "api_key": self.api_key,
                "data[0]": "value",
                "facets[series][0]": series_id,
                "frequency": frequency,
                "start": start,
                "end": end,
                "sort[0][column]": "period",
                "sort[0][direction]": "asc",
                "offset": offset,
                "length": page_length
            }
            
            try:
                response = requests.get(url, params=params, timeout=settings.DEFAULT_REQUEST_TIMEOUT)
                response.raise_for_status()
                page_data = response.json()

                if not page_data or "response" not in page_data or not page_data["response"].get("data"):
                    logger.info(f"Nenhuma observação adicional encontrada para '{series_id}' no offset {offset}.")
                    break
                
                observations = page_data["response"]["data"]
                all_observations.extend(observations)

                total_available = int(page_data["response"].get("total", 0))
                if not observations or (offset + len(observations) >= total_available):
                    break
                
                offset += page_length
                time.sleep(settings.API_DELAYS.get("EIA", 1))

            except requests.exceptions.HTTPError as http_err:
                logger.error(f"Erro HTTP ao buscar dados da EIA '{series_id}': {http_err}")
                break
            except Exception as e:
                logger.error(f"Erro ao processar a série '{series_id}' da EIA: {e}")
                break

        if not all_observations:
            return pd.DataFrame()

        df = pd.DataFrame(all_observations)
        df = df[['period', 'value']]
        df['date'] = pd.to_datetime(df['period'])
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        df.dropna(inplace=True)

        logger.info(f"EIACollector: {len(df)} registros encontrados para a série '{series_id}'.")
        return df[['date', 'value']]