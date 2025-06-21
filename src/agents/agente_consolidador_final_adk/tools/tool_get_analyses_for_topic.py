# src/agents/agente_consolidador_final_adk/tools/tool_get_analyses_for_topic.py
# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path
import json
from google.adk.tools import FunctionTool 
from pydantic import BaseModel, Field # Mantenha esses imports, FetchTopicAnalysisInput os usa
from src.database.db_utils import get_db_session, get_analyses_for_topic

# Bloco de import padrão
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent # Ajuste se o root for diferente
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())


# Define o esquema de entrada para a ferramenta (usado para documentação/validação)
class FetchTopicAnalysisInput(BaseModel):
    topic: str = Field(..., description="O tópico ou empresa a ser pesquisado (ex: 'Petrobras').")
    days_back: int = Field(7, description="O número de dias a olhar para trás para buscar análises.")

# A função Python que a ferramenta encapsula
def fetch_topic_analysis_from_db(topic: str, days_back: int = 7) -> str:
    """
    Busca no banco de dados todas as análises de artigos que mencionam um tópico
    específico nos últimos dias e retorna os resultados como uma string JSON.
    Esta ferramenta é para ser usada pelo Agente Consolidador para obter dados.
    """
    with get_db_session() as session:
        analyses = get_analyses_for_topic(session, topic, days_back)
        if not analyses:
            return json.dumps({"error": "Nenhuma análise encontrada para este tópico no período."})
        return json.dumps(analyses, ensure_ascii=False, indent=2)

fetch_topic_analysis_from_db_tool = FunctionTool(
    func=fetch_topic_analysis_from_db
)