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
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except Exception as e:
    logging.error(f"Erro ao configurar PROJECT_ROOT em tool_collect_rss_articles.py: {e}")
    PROJECT_ROOT = Path(os.getcwd())

# Importa o coletor RSS real
try:
    from src.data_collection.news_data.news_rss_collector import RSSCollector
    from config import rss_news_config as rss_config
    from config import news_sources_feeds as news_feeds_config
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
            mock_articles = []
            for feed_url in feed_urls:
                feed_info = next((f for f in self.feeds_config.get("rss_feeds", []) if f.get("url") == feed_url), {})
                source_name_mock = feed_info.get("name", "Mock RSS Feed Source")
                publisher_domain_override_mock = feed_info.get("publisher_domain_override")

                mock_articles.extend([
                    {
                        "title": f"Mock RSS Article 1 from {source_name_mock}", # Removido timestamp
                        "link": f"http://mock.com/rss/{source_name_mock.replace(' ', '_')}/article1", # Removido timestamp
                        "summary": f"This is a mock summary for the first RSS article from {source_name_mock}.",
                        "published_parsed_iso": datetime.now(timezone.utc).isoformat(),
                        "source_name": source_name_mock,
                        "feed_url": feed_url,
                        "publisher_domain_override": publisher_domain_override_mock,
                        "source_type": "RSS"
                    },
                    {
                        "title": f"Mock RSS Article 2 from {source_name_mock}", # Removido timestamp
                        "link": f"http://mock.com/rss/{source_name_mock.replace(' ', '_')}/article2", # Removido timestamp
                        "summary": f"This is a mock summary for the second RSS article from {source_name_mock}.",
                        "published_parsed_iso": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                        "source_name": source_name_mock,
                        "feed_url": feed_url,
                        "publisher_domain_override": publisher_domain_override_mock,
                        "source_type": "RSS"
                    }
                ])
            return mock_articles
    
    RSSCollector = MockRSSCollector
    rss_config = {}
    news_feeds_config = { 
        "rss_feeds": [
            {"name": "Mock RSS Feed", "url": "http://mock.com/feed", "publisher_domain_override": "chathamhouse.org"},
            {"name": "Another Regular Feed", "url": "http://another.com/feed", "source_name": "Another Source"}
        ]
    }


def tool_collect_rss_articles(
    feed_names: Optional[List[str]] = None,
    tool_context: Any = None
) -> Dict[str, Any]:
    try:
        all_feeds_config = news_feeds_config.get("rss_feeds", [])
        
        feeds_to_collect_info = []
        if feed_names:
            for feed_name in feed_names:
                found_feed = next((f for f in all_feeds_config if f.get("name") == feed_name), None)
                if found_feed:
                    feeds_to_collect_info.append(found_feed)
                else:
                    logger.warning(f"Feed RSS '{feed_name}' não encontrado na configuração.")
        else:
            feeds_urls = [f.get("url") for f in all_feeds_config if f.get("url")]
            feeds_to_collect_info = [f for f in all_feeds_config if f.get("url") in feeds_urls]


        if not feeds_to_collect_info:
            raise ValueError("Nenhum feed RSS válido para coletar.")

        feeds_urls = [f.get("url") for f in feeds_to_collect_info if f.get("url")]
        
        collector = RSSCollector(feeds_config=news_feeds_config)
        articles = collector.collect_articles_from_feeds(feed_urls=feeds_urls)
        
        for article in articles:
            article["source_type"] = "RSS"
            feed_info_for_article = next((f for f in feeds_to_collect_info if f.get("url") == article.get("feed_url")), {})
            article["source_name"] = feed_info_for_article.get("name", article.get("source_name", "Unknown RSS Source"))
            article["publisher_domain_override"] = feed_info_for_article.get("publisher_domain_override")


        logger.info(f"Coleta RSS: Encontrados {len(articles)} artigos de {len(feeds_to_collect_info)} feeds configurados.")
        return {"status": "success", "articles_data": articles}

    except Exception as e:
        logger.error(f"Erro ao coletar artigos de feeds RSS: {e}", exc_info=True)
        return {"status": "error", "message": str(e), "articles_data": []}