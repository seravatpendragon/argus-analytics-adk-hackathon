import json
import os
from pathlib import Path
import fundamentus
import pandas as pd
from typing import List, Dict, Any
from config import settings

logger = settings.logger

# Bloco para encontrar a raiz do projeto e acessar a pasta /config
try:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
except NameError:
    PROJECT_ROOT = Path(os.getcwd())

class FundamentusCollector:
    """
    Coletor especialista para a biblioteca pyfundamentus.
    Responsabilidades:
    1. Ler a configuração de indicadores de um JSON.
    2. Chamar a API do pyfundamentus.
    3. Extrair a data do balanço e os indicadores aprovados.
    4. Retornar os dados de forma estruturada.
    """
    def __init__(self):
        self.approved_indicators = self._load_approved_indicators()

    def _load_approved_indicators(self):
        config_path = PROJECT_ROOT / "config" / "fundamentus_indicators_config.json"
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            # Transforma o JSON em uma lista plana de nomes de indicadores
            approved_list = [indicator for category in config.values() for indicator in category]
            # Adiciona o 'Último balanço' para garantir que sempre seja coletado
            if 'Último balanço' not in approved_list:
                approved_list.append('Último balanço')
            logger.debug(f"Indicadores aprovados para coleta via Fundamentus: {approved_list}")
            return approved_list
        except FileNotFoundError:
            logger.error(f"Arquivo de configuração não encontrado em: {config_path}")
            return []

    def get_fundamentus_data(self, tickers: List[str]) -> list:
        logger.info(f"Iniciando PyFundamentusCollector (v5 - Final com datação)")
        config_path = PROJECT_ROOT / "config" / "fundamentus_indicators_config.json"
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        approved_indicators = {indicator for category in config.values() for indicator in category}

        all_tickers_data = []
        for full_ticker in tickers:
            try:
                normalized_ticker = full_ticker.split('.')[0]
                pipeline = fundamentus.Pipeline(normalized_ticker)
                response = pipeline.get_all_information()

                combined_data = {
                    item.title.strip(): item.value
                    for category in response.transformed_information.values() if isinstance(category, dict)
                    for item in category.values() if hasattr(item, 'title')
                }

                # Extrai e remove o 'Último balanço' para usá-lo como a data efetiva
                balanco_date_str = combined_data.pop('Último balanço', None)
                
                ticker_indicators = []
                for indicator_name, indicator_value in combined_data.items():
                    if indicator_name in approved_indicators:
                        ticker_indicators.append({
                            'indicator': indicator_name,
                            'value': indicator_value
                        })

                all_tickers_data.append({
                    "ticker": full_ticker,
                    "balanco_date_str": balanco_date_str,
                    "indicators": ticker_indicators
                })
            except Exception as e:
                logger.warning(f"Não foi possível buscar dados do pyfundamentus para '{full_ticker}'. Erro: {e}")
                continue

        return all_tickers_data