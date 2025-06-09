import pandas as pd
import requests
from datetime import datetime
from config import settings
import re

logger = settings.logger

class IBGECollector:
    """
    Coletor robusto para a API do SIDRA/IBGE, que constrói a URL complexa
    e interpreta a resposta dinamicamente para encontrar as colunas de data e valor.
    """
    def __init__(self):
        # A URL agora é apenas a base, o resto é construído dinamicamente.
        self.base_url = "https://apisidra.ibge.gov.br/values"

    def get_series(self, task: dict) -> pd.DataFrame:
        params = task.get("params", {})
        table_code = params.get("table_code")
        variable_list = params.get("variable_arg_list", [])
        
        if not all([table_code, variable_list]):
            logger.error(f"Task IBGE mal configurada: {task.get('indicator_config_id')}")
            return pd.DataFrame()

        # --- INÍCIO DA LÓGICA DE CONSTRUÇÃO DE URL CORRETA ---
        
        # 1. Período (last N)
        years = params.get("initial_history_years", 5)
        frequency = task.get("db_indicator_frequency", "M")
        num_periods = 0
        if frequency == "M":
            num_periods = years * 12
        elif frequency == "Q":
            num_periods = years * 4
        else: # Anual ou desconhecido
            num_periods = years
        period_arg = f"last%20{num_periods}"

        # 2. Montagem da URL baseada nos caminhos
        url_parts = [
            f"/t/{table_code}",
            f"/n{params.get('geo_level_arg', '1')}/{params.get('geo_codes_arg', 'all')}",
            f"/v/{'+'.join(variable_list)}",
            f"/p/{period_arg}"
        ]

        # 3. Classificações (parâmetros /c...)
        classifications = params.get("classifications_arg") or {}
        for class_code, item_code in classifications.items():
            url_parts.append(f"/c{class_code}/{item_code}")
        
        url = self.base_url + "".join(url_parts)
        # --- FIM DA LÓGICA DE CONSTRUÇÃO DE URL ---
        
        logger.info(f"IBGECollector: Buscando dados para '{task['indicator_config_id']}'")
        logger.debug(f"URL montada: {url}")
        
        try:
            # A API do SIDRA espera o formato 'application/json; charset=utf-8'
            headers = {'Accept': 'application/json; charset=utf-8'}
            response = requests.get(url, headers=headers, timeout=90)
            response.raise_for_status()
            data = response.json()

            if not data or len(data) <= 1:
                logger.warning(f"Nenhum dado retornado para a tarefa {task['indicator_config_id']}.")
                return pd.DataFrame()

            header_map = {key: value for key, value in data[0].items()}
            df_data = data[1:]
            
            # Lógica de parsing dinâmico das colunas
            period_key = None
            for key, value in header_map.items():
                if re.search(r'mês|ano|trimestre', str(value), re.IGNORECASE):
                    period_key = key
                    break
            
            value_key = 'V'

            if not period_key:
                logger.error(f"Não foi possível encontrar a coluna de período na resposta da API para a tarefa {task['indicator_config_id']}.")
                return pd.DataFrame()
                
            df = pd.DataFrame(df_data)
            df = df[[period_key, value_key]]
            df.rename(columns={period_key: 'period_code', value_key: 'value'}, inplace=True)
            
            df['value'] = pd.to_numeric(df['value'], errors='coerce')
            df['date'] = pd.to_datetime(df['period_code'], format='%Y%m', errors='coerce')
            
            df.dropna(subset=['date', 'value'], inplace=True)

            logger.info(f"IBGECollector: {len(df)} registros encontrados para '{task['indicator_config_id']}'.")
            return df[['date', 'value']]

        except Exception as e:
            logger.error(f"Erro ao processar dados do IBGE para a tarefa {task['indicator_config_id']}: {e}", exc_info=True)
            return pd.DataFrame()