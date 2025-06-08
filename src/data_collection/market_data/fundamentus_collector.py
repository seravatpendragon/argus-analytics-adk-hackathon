# Em /src/data_collection/market_data/pyfundamentus_collector.py

import json
import os
from pathlib import Path
import fundamentus
import pandas as pd
from typing import List, Dict, Any
from config import settings
from decimal import Decimal

logger = settings.logger

# --- INÍCIO DA CORREÇÃO: Configuração de Caminhos ---
# Este bloco encontra a raiz do projeto para que possamos localizar a pasta /config
try:
    # O caminho deste arquivo é: .../src/data_collection/market_data/
    # .parent (1) -> market_data
    # .parent (2) -> data_collection
    # .parent (3) -> src
    # .parent (4) -> Raiz do Projeto
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
except NameError:
    # Fallback caso o script seja executado de uma forma onde __file__ não é definido
    PROJECT_ROOT = Path(os.getcwd())
# --- FIM DA CORREÇÃO ---

class FundamentusCollector:
    def get_fundamentus_data(self, tickers: List[str]) -> List[Dict[str, Any]]:
        """
        Busca dados do pyfundamentus, filtrando e formatando com base no
        arquivo de configuração fundamentus_indicators_config.json.
        """
        logger.info(f"Iniciando PyFundamentusCollector (v4, com JSON e parsing de valor)")

        # Carrega a lista de indicadores aprovados do JSON usando o caminho correto
        config_path = PROJECT_ROOT / "config" / "fundamentus_indicators_config.json"
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except FileNotFoundError:
            logger.error(f"Arquivo de configuração não encontrado em: {config_path}")
            return []
        
        approved_indicators = []
        for category in config.values():
            approved_indicators.extend(category)
        logger.debug(f"Indicadores aprovados para coleta: {approved_indicators}")

        all_indicators_data = []
        for full_ticker in tickers:
            try:
                normalized_ticker = full_ticker.split('.')[0]
                pipeline = fundamentus.Pipeline(normalized_ticker)
                response = pipeline.get_all_information()

                combined_data = {}
                for category_dict in response.transformed_information.values():
                    if isinstance(category_dict, dict):
                        combined_data.update(category_dict)

                for _, indicator_object in combined_data.items():
                    
                    def process_item(item):
                        if hasattr(item, 'title'):
                            # --- ADICIONE ESTA LINHA DE DEBUG ---
                            logger.debug(f"API retornou o indicador: '{item.title}' | Aprovado? {item.title in approved_indicators}")

                            if item.title in approved_indicators:
                                return {
                                    'ticker': full_ticker,
                                    'indicator': item.title.strip(),
                                    'value': item.value
                                }
                        elif isinstance(item, dict):
                            nested_records = []
                            for sub_item in item.values():
                                processed = process_item(sub_item)
                                if processed:
                                    nested_records.append(processed)
                            return nested_records
                        return None

                    records = process_item(indicator_object)
                    if records:
                        if isinstance(records, list):
                            all_indicators_data.extend(records)
                        else:
                            all_indicators_data.append(records)
            except Exception as e:
                logger.warning(f"Não foi possível buscar dados do pyfundamentus para o ticker '{full_ticker}'. Erro: {e}")
                continue

        logger.info(f"Total de {len(all_indicators_data)} indicadores aprovados e coletados da pyfundamentus.")
        return all_indicators_data