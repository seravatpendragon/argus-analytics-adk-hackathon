# src/agents/agente_coletor_rss_adk/tools/tool_collect_rss_articles.py

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
    # Sobe 4 níveis (tools/ -> agente_coletor_rss_adk/ -> agents/ -> src/ -> PROJECT_ROOT)
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except Exception as e:
    logging.error(f"Erro ao configurar PROJECT_ROOT em tool_collect_rss_articles.py: {e}")
    PROJECT_ROOT = Path(os.getcwd())

# Importa o coletor RSS real
try:
    from src.data_collection.news_data.news_rss_collector import RSSCollector
    # Importa as configurações do RSS
    from config import rss_news_config as rss_config
    from config import news_sources_feeds as news_feeds_config # Para feeds específicos
    _USING_MOCK_COLLECTOR = False
except ImportError as e:
    logging.error(f"Não foi possível importar RSSCollector ou configurações RSS: {e}. O teste usará mocks.")
    _USING_MOCK_COLLECTOR = True

logger = logging.getLogger(__name__)

# --- MOCK RSSCollector para testes standalone sem configuração real ---
if _USING_MOCK_COLLECTOR:
    class MockRSSCollector:
        def __init__(self, feeds_config: Dict[str, Any]):
            self.feeds_config = feeds_config
            logger.warning("Usando MockRSSCollector. Nenhuma chamada real a feeds RSS será feita.")

        def collect_articles_from_feeds(self, feed_urls: List[str]) -> List[Dict[str, Any]]:
            logger.info(f"MOCK RSS: Simulando coleta para feeds: {feed_urls}")
            # Retorna dados mockados
            mock_articles = [
                {
                    "title": f"Mock RSS Article 1 - {datetime.now().isoformat()}",
                    "link": f"http://mock.com/rss/article1-{datetime.now().timestamp()}",
                    "summary": "This is a mock summary for the first RSS article.",
                    "published_parsed_iso": datetime.now(timezone.utc).isoformat(),
                    "source_name": "Mock RSS Feed Source",
                    "feed_url": feed_urls[0] if feed_urls else "http://mock.com/feed"
                },
                {
                    "title": f"Mock RSS Article 2 - {datetime.now().isoformat()}",
                    "link": f"http://mock.com/rss/article2-{datetime.now().timestamp()}",
                    "summary": "This is a mock summary for the second RSS article.",
                    "published_parsed_iso": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                    "source_name": "Another Mock RSS Source",
                    "feed_url": feed_urls[0] if feed_urls else "http://mock.com/feed"
                }
            ]
            return mock_articles
    
    RSSCollector = MockRSSCollector # Atribui o mock à variável real para uso abaixo
    rss_config = {} # Configuração mock
    news_feeds_config = { # Configuração mock para feeds
        "rss_feeds": [
            {"name": "Mock RSS Feed", "url": "http://mock.com/feed"}
        ]
    }


def tool_collect_rss_articles(
    feed_names: Optional[List[str]] = None, # Nomes dos feeds a coletar (ex: "Alertas Google PETR4")
    tool_context: Any = None # ToolContext é opcional para esta ferramenta
) -> Dict[str, Any]:
    """
    Coleta artigos de notícias de feeds RSS configurados.

    Args:
        feed_names (Optional[List[str]]): Lista de nomes de feeds a coletar. Se None, coleta de todos os feeds configurados.
        tool_context (Any): O contexto da ferramenta (opcional, injetado pelo ADK).

    Returns:
        Dict[str, Any]: Um dicionário com 'status' ('success' ou 'error') e uma lista
                        de artigos brutos ('articles_data').
    """
    try:
        all_feeds = news_feeds_config.get("rss_feeds", [])
        
        feeds_to_collect_urls = []
        if feed_names:
            for feed_name in feed_names:
                found_feed = next((f for f in all_feeds if f.get("name") == feed_name), None)
                if found_feed and found_feed.get("url"):
                    feeds_to_collect_urls.append(found_feed["url"])
                else:
                    logger.warning(f"Feed RSS '{feed_name}' não encontrado na configuração ou sem URL.")
        else: # Coleta de todos os feeds se nenhum nome for especificado
            feeds_to_collect_urls = [f["url"] for f in all_feeds if f.get("url")]

        if not feeds_to_collect_urls:
            raise ValueError("Nenhum feed RSS válido para coletar.")

        collector = RSSCollector(feeds_config=news_feeds_config) # Passa a config completa se o real precisar
        articles = collector.collect_articles_from_feeds(feed_urls=feeds_to_collect_urls)
        
        # Adiciona o source_type para o pipeline de pré-processamento
        for article in articles:
            article["source_type"] = "RSS"

        logger.info(f"Coleta RSS: Encontrados {len(articles)} artigos de {len(feeds_to_collect_urls)} feeds.")
        return {"status": "success", "articles_data": articles}

    except Exception as e:
        logger.error(f"Erro ao coletar artigos de feeds RSS: {e}", exc_info=True)
        return {"status": "error", "message": str(e), "articles_data": []}