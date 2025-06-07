# src/data_collection/news_data/newsapi_collector.py
import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
import tldextract
import requests
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
    _logger.critical(f"Erro CRÍTICO em newsapi_collector.py ao importar módulos: {e}")
    sys.exit(1)


class NewsAPICollector:
    """ Encapsula a lógica de coleta e persistência de dados da NewsAPI. """

    def __init__(self, db_session: Session, credibility_data: dict):
        if not settings.NEWSAPI_API_KEY:
            raise ValueError("NEWSAPI_API_KEY não está configurada em settings.py!")
        self.db_session = db_session
        self.credibility_data = credibility_data
        self.headers = {"X-Api-Key": settings.NEWSAPI_API_KEY}

    def _get_domain_from_url(self, url: str) -> str | None:
        if not url: return None
        try:
            extracted = tldextract.extract(url)
            return extracted.registered_domain.lower() if extracted.registered_domain else None
        except Exception:
            return urlparse(url).hostname

    def _assign_initial_article_type(self, title: str | None, summary: str | None) -> str:
        text_to_search = (title or "").lower() + " " + (summary or "").lower()
        if "fato relevante" in text_to_search: return "Fato Relevante"
        return "Outros"

    def run_single_query_and_prepare_data(self, query_config: dict, base_url: str) -> list[tuple]:
        """ Executa uma query, processa os artigos e retorna uma lista de tuplas (article_dict, target_ticker, target_segment). """
        query_name = query_config.get("query_name", "Query Padrão")
        params = query_config.get("params", {})
        # CORREÇÃO: Capturamos o ticker e o segmento alvo da configuração da query
        target_company_ticker = query_config.get("target_company_ticker")
        target_segment_name = query_config.get("target_segment_name")
        
        settings.logger.info(f"Executando NewsAPI Query: '{query_name}' com ticker alvo: {target_company_ticker}")

        try:
            response = requests.get(base_url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            articles_from_api = response.json().get("articles", [])
        except requests.exceptions.RequestException as e:
            settings.logger.error(f"Erro na requisição à NewsAPI: {e}")
            return []

        if not articles_from_api:
            return []

        prepared_data_with_context = []
        for api_article in articles_from_api:
            article_link = api_article.get("url")
            if not article_link: continue

            headline_text = (api_article.get("title") or "Sem Título").strip()
            if not headline_text:
                headline_text = "Sem Título"
                settings.logger.warning(f"Artigo recebido sem título! Link: {article_link}")

            news_source_obj = get_or_create_news_source(self.db_session, self._get_domain_from_url(article_link), api_article.get("source", {}).get("name"), self.credibility_data)
            if not news_source_obj: continue
            
            publication_date_dt = None
            if published_at_str := api_article.get("publishedAt"):
                try: publication_date_dt = datetime.fromisoformat(published_at_str.replace("Z", "+00:00"))
                except ValueError: publication_date_dt = datetime.now(timezone.utc)
            
            article_dict = {
                "headline": headline_text,
                "article_link": article_link,
                "publication_date": publication_date_dt,
                "news_source_id": news_source_obj.news_source_id,
                "summary": api_article.get("description"),
                "article_type": self._assign_initial_article_type(headline_text, api_article.get("description")),
                "processing_status": 'pending_full_text_fetch',
                "source_feed_name": f"NewsAPI - {query_name}",
                "collection_date": datetime.now(timezone.utc)
            }
            # CORREÇÃO: Adiciona uma tupla com o dicionário e o contexto
            prepared_data_with_context.append((article_dict, target_company_ticker, target_segment_name))
            
        return prepared_data_with_context