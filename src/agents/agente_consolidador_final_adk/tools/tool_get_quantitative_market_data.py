# src/agents/agente_consolidador_analise_adk/tools/tool_get_quantitative_market_data.py
# -*- coding: utf-8 -*-

import os
import sys
from pathlib import Path
import json
from typing import List, Optional

# Bloco de import padrão
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())

from config import settings
from google.adk.tools import FunctionTool
from pydantic import BaseModel, Field
from src.database.db_utils import get_db_session, get_quantitative_data_for_topic # Importa a nova função


# Esquema de entrada para a ferramenta
class GetQuantitativeMarketDataInput(BaseModel):
    topic_or_ticker: str = Field(..., description="O tópico ou ticker da empresa (ex: 'Petrobras', 'PETR4', 'Petróleo', 'IPCA').")
    days_back: int = Field(7, description="O número de dias a olhar para trás para buscar dados.")
    specific_indicators: Optional[List[str]] = Field(None, description="Lista opcional de nomes de indicadores específicos a buscar (ex: ['BCB IPCA Variação Mensal', 'EIA Preço Petróleo Brent Spot (Diário)']).")

# Função que a ferramenta encapsula
def get_quantitative_market_data(topic_or_ticker: str, days_back: int = 7, specific_indicators: Optional[List[str]] = None) -> str:
    """
    Busca dados quantitativos (fundamentos da empresa, preços de commodities, indicadores macroeconômicos)
    relevantes para um tópico ou ticker nos últimos dias.
    Retorna os dados como uma string JSON formatada para o LLM.
    """
    with get_db_session() as session:
        data = get_quantitative_data_for_topic(session, topic_or_ticker, days_back, specific_indicators)
        return json.dumps(data, ensure_ascii=False, indent=2)

get_quantitative_market_data_tool = FunctionTool(
    func=get_quantitative_market_data
)