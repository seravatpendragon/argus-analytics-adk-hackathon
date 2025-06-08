# /src/data_collection/market_data/fundamentus_collector.py
import fundamentus
import pandas as pd
from typing import List, Dict, Any
from config import settings

logger = settings.logger

class FundamentusCollector:
    """
    O "Engenheiro Especialista" para dados do pyfundamentus.
    Usa a biblioteca 'fundamentus' da maneira correta, via classe Pipeline.
    """
    def get_fundamentus_data(self, tickers: List[str]) -> List[Dict[str, Any]]:
        logger.info(f"Buscando dados via pyfundamentus para {len(tickers)} tickers.")
        all_indicators_data = []

        for full_ticker in tickers:
            try:
                # Normaliza o ticker para a API (ex: PETR4.SA -> PETR4)
                normalized_ticker = full_ticker.split('.')[0]
                logger.debug(f"Ticker normalizado de '{full_ticker}' para '{normalized_ticker}' para a API.")

                # --- USO CORRETO DA BIBLIOTECA, SEGUINDO A DOCUMENTAÇÃO ---
                pipeline = fundamentus.Pipeline(normalized_ticker)
                response = pipeline.get_all_information()

                # A resposta vem em múltiplos dicionários, vamos unificar todos em um só.
                combined_data = {}
                for category_dict in response.transformed_information.values():
                    if isinstance(category_dict, dict):
                        combined_data.update(category_dict)

                # Agora, transformamos o dicionário unificado no formato que o BD espera
                for indicator_name, indicator_value in combined_data.items():
                    # Prepara o registro para inserção
                    record = {
                        'ticker': full_ticker,  # Usamos o ticker original para consistência no BD
                        'indicator': indicator_name.strip(),
                        'value': str(indicator_value).strip(), # Garante que o valor seja uma string
                        'source': 'Fundamentus',
                        'collected_at': pd.to_datetime('today').strftime('%Y-%m-%d')
                    }
                    all_indicators_data.append(record)

                logger.debug(f"Dados para {full_ticker} processados com sucesso via pyfundamentus.")

            except Exception as e:
                # Se a biblioteca falhar para um ticker (ex: não encontrado), ela levanta uma exceção.
                # Nós a capturamos, registramos e continuamos para o próximo.
                logger.warning(f"Não foi possível buscar dados do pyfundamentus para o ticker '{full_ticker}'. Erro: {e}")
                continue

        logger.info(f"Total de {len(all_indicators_data)} pares de indicador/valor coletados da pyfundamentus.")
        return all_indicators_data