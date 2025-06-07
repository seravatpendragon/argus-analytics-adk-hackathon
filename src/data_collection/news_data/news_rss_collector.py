# src/data_collection/news_data/news_rss_collector.py

import feedparser
import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
import tldextract
import requests
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pathlib import Path

# --- Bloco Padrão de Configuração e Imports ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
try:
    from src.database.db_utils import get_or_create_news_source, get_company_id_for_ticker, get_segment_id_by_name
    from src.database.create_db_tables import NewsArticle, NewsArticleCompanyLink, NewsArticleSegmentLink
except ImportError as e:
    import logging
    logging.basicConfig(level=logging.INFO)
    _logger = logging.getLogger(__name__)
    _logger.critical(f"Erro CRÍTICO em news_rss_collector.py ao importar módulos: {e}")
    sys.exit(1)


class RSSCollector:
    """ Encapsula a lógica de coleta de feeds RSS, incluindo limpeza e resolução de links. """

    def __init__(self, db_session: Session, credibility_data: dict):
        self.db_session = db_session
        self.credibility_data = credibility_data
        self.feedparser_agent = getattr(settings, 'USER_AGENT', "Mozilla/5.0 ArgusRSSCollector/1.3")
        self.request_headers = {'Accept': 'application/rss+xml,application/xml,application/atom+xml,*/*'}

    def _clean_google_alert_url(self, raw_url: str) -> str:
        try:
            return parse_qs(urlparse(raw_url).query)['url'][0]
        except (KeyError, IndexError):
            return raw_url

    def _resolve_redirect_url(self, raw_url: str) -> str:
        try:
            response = requests.head(raw_url, allow_redirects=True, timeout=10, headers={'User-Agent': self.feedparser_agent})
            return response.url
        except requests.exceptions.RequestException as e:
            settings.logger.warning(f"Falha ao resolver redirect para '{raw_url}': {e}. Usando URL original.")
            return raw_url

    def _get_final_article_link(self, raw_link: str):
        if not raw_link: return None
        if "google.com/url?" in raw_link:
            return self._clean_google_alert_url(raw_link)
        if "news.google.com/rss/articles/" in raw_link:
            return self._resolve_redirect_url(raw_link)
        return raw_link

    def _get_domain_from_url(self, url: str) -> str | None:
        if not url: return None
        try:
            extracted = tldextract.extract(url)
            return extracted.registered_domain.lower() if extracted.registered_domain else None
        except Exception:
            return urlparse(url).hostname
            
    def run_single_feed(self, feed_config: dict) -> list[tuple]:
        feed_name = feed_config.get("source_name", "Feed RSS Padrão")
        feed_url = feed_config.get("feed_url")
        if not feed_url: return []

        settings.logger.info(f"Processando Feed RSS: '{feed_name}'...")
        
        feed_data = feedparser.parse(feed_url, agent=self.feedparser_agent, request_headers=self.request_headers)

        if not feed_data.entries:
            return []

        prepared_data_with_context = []
        for entry in feed_data.entries:
            final_link = self._get_final_article_link(entry.get("link"))
            
            if not final_link or not final_link.startswith(('http://', 'https://')):
                settings.logger.warning(f"Item descartado por não ter um link HTTP válido. ID/Link recebido: '{final_link}'")
                continue

            headline_text = (entry.get("title") or "Sem Título").strip()
            if not headline_text: headline_text = "Sem Título"
            
            publisher_domain_override = feed_config.get("publisher_domain_override")
            source_domain = self._get_domain_from_url(publisher_domain_override or final_link)
            if not source_domain: continue
            
            source_name_hint = entry.source.get("title") if hasattr(entry, "source") else feed_name
            news_source_obj = get_or_create_news_source(self.db_session, source_domain, source_name_hint, self.credibility_data)
            if not news_source_obj: continue

            publication_date_dt = None
            if time_struct := entry.get("published_parsed"):
                try: publication_date_dt = datetime(*time_struct[:6], tzinfo=timezone.utc)
                except: publication_date_dt = datetime.now(timezone.utc)
            
            article_dict = {
                "headline": headline_text,
                "article_link": final_link,
                "publication_date": publication_date_dt,
                "news_source_id": news_source_obj.news_source_id,
                "summary": entry.get("summary"),
                "article_type": "Outros",
                "processing_status": 'pending_full_text_fetch',
                "source_feed_name": feed_name,
                "collection_date": datetime.now(timezone.utc)
            }
            prepared_data_with_context.append((article_dict, feed_config.get("target_company_ticker"), feed_config.get("target_segment_name")))
            
        return prepared_data_with_context