# src/agents/agente_coletor_newsapi_adk/tools/tool_collect_newsapi_articles.py

import logging
import os
from datetime import datetime, timedelta, timezone 
from typing import Dict, Any, List, Optional
import json

# --- Configuração de Caminhos para Imports do Projeto ---
from pathlib import Path
import sys
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except Exception as e:
    logging.error(f"Erro ao configurar PROJECT_ROOT em tool_collect_newsapi_articles.py: {e}")
    PROJECT_ROOT = Path(os.getcwd())

# Importa o coletor NewsAPI real
try:
    from src.data_collection.news_data.newsapi_collector import NewsAPICollector
    from config import newsapi_news_config as newsapi_config
    _USING_MOCK_COLLECTOR = False
except ImportError as e:
    logging.error(f"Não foi possível importar NewsAPICollector ou newsapi_news_config: {e}. O teste usará mocks.")
    _USING_MOCK_COLLECTOR = True

logger = logging.getLogger(__name__)

# --- MOCK NewsAPICollector para testes standalone sem chave API ---
if _USING_MOCK_COLLECTOR:
    class MockNewsAPICollector:
        def __init__(self, api_key: str, base_url: str):
            self.api_key = api_key
            self.base_url = base_url
            logger.warning("Usando MockNewsAPICollector. Nenhuma chamada real à API será feita.")

        def get_articles(self, query: str, from_param: str, to_param: str, language: str, sort_by: str, page_size: int) -> List[Dict[str, Any]]:
            logger.info(f"MOCK NewsAPI: Simulando coleta para query='{query}' de {from_param} a {to_param}")
            mock_articles = [
                {
                    "source": {"id": "mock-source-1", "name": "Mock News Source"},
                    "author": "Mock Author",
                    "title": f"Mock NewsAPI Article 1 for {query}", # Removido timestamp
                    "description": "This is a mock description for the first article.",
                    "url": f"http://mock.com/newsapi/article1_{query}", # Removido timestamp
                    "urlToImage": "http://mock.com/image1.jpg",
                    "publishedAt": datetime.now(timezone.utc).isoformat(), # Mantém data atual para o campo publishedAt
                    "content": "Mock content for article 1."
                },
                {
                    "source": {"id": "mock-source-2", "name": "Another Mock Source"},
                    "author": "Another Mock Author",
                    "title": f"Mock NewsAPI Article 2 for {query}", # Removido timestamp
                    "description": "This is a mock description for the second article.",
                    "url": f"http://mock.com/newsapi/article2_{query}", # Removido timestamp
                    "urlToImage": "http://mock.com/image2.jpg",
                    "publishedAt": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                    "content": "Mock content for article 2."
                }
            ]
            for article in mock_articles:
                article["source_type"] = "NewsAPI"
            return mock_articles
    
    NewsAPICollector = MockNewsAPICollector
    newsapi_config = {
        "NEWSAPI_API_KEY": "MOCK_API_KEY",
        "NEWSAPI_BASE_URL": "http://mock.newsapi.org/v2/everything",
        "DEFAULT_QUERY_PARAMS": {
            "language": "pt",
            "sortBy": "publishedAt",
            "pageSize": 5
        }
    }


def tool_collect_newsapi_articles(
    query: str,
    days_back: int = 1,
    page_size: int = 10,
    tool_context: Any = None
) -> Dict[str, Any]:
    try:
        api_key = newsapi_config.get("NEWSAPI_API_KEY")
        base_url = newsapi_config.get("NEWSAPI_BASE_URL")
        default_params = newsapi_config.get("DEFAULT_QUERY_PARAMS", {})

        if not api_key or not base_url:
            raise ValueError("Chave API ou URL base da NewsAPI não configurada.")

        collector = NewsAPICollector(api_key=api_key, base_url=base_url)

        to_date = datetime.now(timezone.utc)
        from_date = to_date - timedelta(days=days_back)

        articles = collector.get_articles(
            query=query,
            from_param=from_date.isoformat(),
            to_param=to_date.isoformat(),
            language=default_params.get("language", "pt"),
            sort_by=default_params.get("sortBy", "publishedAt"),
            page_size=page_size
        )
        
        for article in articles:
            article["source_type"] = "NewsAPI"

        logger.info(f"Coleta NewsAPI: Encontrados {len(articles)} artigos para a query '{query}'.")
        return {"status": "success", "articles_data": articles}

    except Exception as e:
        logger.error(f"Erro ao coletar artigos da NewsAPI para query '{query}': {e}", exc_info=True)
        return {"status": "error", "message": str(e), "articles_data": []}