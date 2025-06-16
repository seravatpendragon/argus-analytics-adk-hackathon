# src/data_collection/news_data/news_rss_collector.py
import feedparser
import json
import os
import sys
import time
import random
import re
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
import tldextract
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By


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
    from src.database.db_utils import get_or_create_news_source
    from src.database.create_db_tables import NewsArticle
except ImportError as e:
    import logging
    _logger = logging.getLogger(__name__)
    _logger.critical(f"Erro CRÍTICO em news_rss_collector.py: {e}", exc_info=True)
    sys.exit(1)


class RSSCollector:
    """ Coletor de RSS com resolução de links de nível industrial e tratamento de timeout. """

    def __init__(self, db_session: Session, credibility_data: dict):
        self.db_session = db_session
        self.credibility_data = credibility_data
        self.request_headers = {'User-Agent': random.choice(settings.USER_AGENTS)}
        self.driver = self._start_driver()

    def _start_driver(self):
        """ Configura e inicia a instância do navegador Selenium. """
        try:
            options = Options()
            options.add_argument("--headless=new")
            options.add_argument(f"user-agent={self.request_headers['User-Agent']}")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            # Define um timeout MÁXIMO para o carregamento de qualquer página
            driver.set_page_load_timeout(25) 
            return driver
        except Exception as e:
            settings.logger.error(f"Falha ao iniciar o driver do Selenium: {e}")
            return None

    def _clean_google_alert_url(self, raw_url: str) -> str:
        """ Extrai a URL real de um link de Alerta do Google. """
        try:
            return parse_qs(urlparse(raw_url).query).get('url', [raw_url])[0]
        except (KeyError, IndexError):
            return raw_url

    def _resolve_redirect_with_requests(self, url: str) -> str:
        """ Tenta resolver redirects simples com requests.head. """
        try:
            response = requests.head(url, allow_redirects=True, timeout=10, headers=self.request_headers)
            return response.url
        except requests.exceptions.RequestException:
            return url

    def _resolve_redirect_with_selenium(self, url: str) -> str:
        """ Usa o navegador para resolver redirects complexos com espera explícita e autocura. """
        # Garante que temos um driver funcionando antes de começar.
        if not self.driver:
            settings.logger.warning("Driver do Selenium não estava ativo. Tentando reiniciar...")
            self.driver = self._start_driver()
            if not self.driver: # Se ainda assim falhar, não podemos continuar.
                settings.logger.error("Falha catastrófica ao reiniciar o driver do Selenium.")
                return url

        try:
            self.driver.get(url)
            
            # ESPERA EXPLÍCITA:
            # Espera por até 15 segundos até que a URL atual NÃO contenha mais 'news.google.com'.
            # A função lambda é executada repetidamente até retornar True (ou o tempo esgotar).
            WebDriverWait(self.driver, 15).until(
                lambda driver: 'news.google.com' not in driver.current_url
            )
            
            # Se a condição foi atendida, a URL mudou e podemos retorná-la.
            return self.driver.current_url
            
        except TimeoutException:
            # Se após 15s a URL não mudou, pode haver um pop-up ou erro.
            # Tentamos uma última vez pegar a URL, pois ela pode ter mudado no último instante.
            final_url_on_timeout = self.driver.current_url
            if final_url_on_timeout != url:
                settings.logger.warning(f"Timeout ao esperar a URL mudar de '{url}', mas a URL final foi capturada: {final_url_on_timeout}")
                return final_url_on_timeout
            else:
                 settings.logger.error(f"Timeout de redirecionamento com Selenium para '{url}'. A URL não mudou.")
                 return url

        except Exception as e:
            # LÓGICA DE AUTOCURA:
            # Se qualquer outro erro ocorrer, assume que o driver está instável.
            # Descarta o driver antigo para forçar a criação de um novo na próxima vez.
            settings.logger.error(f"Erro no Selenium para '{url}': {e}. O driver será reiniciado.")
            if self.driver:
                self.driver.quit()
            self.driver = None 
            return url
    
    def _get_final_article_link(self, raw_link: str) -> tuple[str, bool]:
        """ Implementa sua lógica de despachante para resolver o link. """
        if not raw_link: return None, False

        final_link = raw_link
        parsed_url = urlparse(raw_link)
        
        # Sua lógica de despachante está perfeita
        if "google.com/url?" in raw_link:
            final_link = self._clean_google_alert_url(raw_link)
        elif "news.google.com" in parsed_url.netloc:
            final_link = self._resolve_redirect_with_selenium(raw_link)
        elif any(domain in parsed_url.netloc for domain in ["t.co", "bit.ly"]):
            final_link = self._resolve_redirect_with_requests(raw_link)

        was_redirected = final_link != raw_link
        if was_redirected:
            settings.logger.info(f"Link resolvido: '{raw_link[:80]}...' -> '{final_link[:80]}...'")

        return final_link, was_redirected
        
    def _get_domain_from_url(self, url: str) -> str | None:
        if not url: return None
        try:
            extracted = tldextract.extract(url)
            return extracted.registered_domain.lower() if extracted.registered_domain else None
        except Exception:
            return urlparse(url).hostname
            
            
    def run_single_feed(self, feed_config: dict) -> list[tuple]:
        """ Executa a coleta de um único feed e prepara os dados para inserção. """
        feed_name = feed_config.get("source_name", "Feed RSS Padrão")
        feed_url = feed_config.get("feed_url")
        if not feed_url: return []

        settings.logger.info(f"Processando Feed RSS: '{feed_name}'...")
        feed_data = feedparser.parse(feed_url, request_headers=self.request_headers)

        if feed_data.bozo:
            settings.logger.warning(f"Feed '{feed_name}' pode estar malformado: {feed_data.bozo_exception}")

        prepared_data_with_context = []
        for entry in feed_data.entries:
            original_link = entry.get("link")
            if not original_link: continue

            # LÓGICA CHAVE: Resolve o link ANTES de qualquer outra coisa
            final_link, was_redirected = self._get_final_article_link(original_link)
            
            if not final_link or not final_link.startswith(('http://', 'https://')):
                settings.logger.warning(f"Item descartado, link inválido: '{final_link}'")
                continue

            headline_text = (entry.get("title") or "Sem Título").strip()
            
            # LÓGICA CHAVE: Usa o domínio do link final para criar a fonte
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
            
            # Prepara o dicionário para o banco com os novos campos de auditoria
            article_dict = {
                "headline": headline_text,
                "article_link": final_link, # A URL real e limpa
                "original_url": original_link if was_redirected else None, # A URL do Google, se aplicável
                "is_redirected": was_redirected, # Flag para sabermos que foi um redirect
                "publication_date": publication_date_dt,
                "news_source_id": news_source_obj.news_source_id,
                "summary": entry.get("summary"),
                "article_type": "RSS",
                "processing_status": 'pending_full_text_fetch',
                "source_feed_name": feed_name,
                "collection_date": datetime.now(timezone.utc)
            }
            prepared_data_with_context.append((article_dict, feed_config.get("target_company_ticker"), feed_config.get("target_segment_name")))
            
        return prepared_data_with_context
    
    def close(self):
        """ Fecha o navegador Selenium quando o trabalho termina. """
        if self.driver:
            self.driver.quit()