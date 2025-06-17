import os
import sys
from pathlib import Path
import json

# Bloco de import padrão
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())

from src.database.db_utils import get_analyses_for_topic, get_db_session

def fetch_topic_analysis_from_db(topic: str, days_back: int = 7) -> str:
    """
    Busca no banco de dados todas as análises de artigos que mencionam um tópico
    específico nos últimos dias e retorna os resultados como uma string JSON.
    
    Args:
        topic: O tópico ou empresa a ser pesquisado (ex: "Petrobras").
        days_back: O número de dias a olhar para trás.
    """
    with get_db_session() as session:
        analyses = get_analyses_for_topic(session, topic, days_back)
        if not analyses:
            return json.dumps({"error": "Nenhuma análise encontrada para este tópico no período."})
        # Converte a lista de dicionários para uma string JSON para o LLM consumir
        return json.dumps(analyses, ensure_ascii=False, indent=2)