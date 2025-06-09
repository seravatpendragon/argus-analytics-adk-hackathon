# src/data_processing/content_extractor.py
from newspaper import Article, ArticleException
from urllib.parse import urlparse
from config import settings
import requests
from bs4 import BeautifulSoup

class ContentExtractor:
    """ Orquestra a extração de conteúdo, usando o método certo para cada domínio. """
    def __init__(self):
        self.config = settings.get_newspaper3k_config()
        self.request_headers = {'User-Agent': self.config.browser_user_agent}

    def _extract_with_newspaper(self, url: str) -> str | None:
        """ Método de extração padrão usando newspaper3k, com checagem de download correta. """
        try:
            article = Article(url, config=self.config)
            article.download()

            # CORREÇÃO: A forma correta de checar se o download funcionou
            # é verificar se o conteúdo HTML foi preenchido.
            if not article.html:
                # Se o download falhou, o ideal é não prosseguir.
                # A própria biblioteca geralmente lança uma exceção antes,
                # mas esta é uma segurança extra.
                raise ArticleException("O download do HTML falhou, o conteúdo está vazio.")

            article.parse()
            return article.text
            
        except ArticleException as e:
            settings.logger.warning(f"Falha de extração com newspaper3k para a URL: {url}. Erro: {e}")
            return None
        except Exception as e:
            settings.logger.error(f"Erro inesperado no newspaper3k para {url}: {e}", exc_info=True)
            return None
    
    def _extract_with_fallback_infomoney(self, url: str) -> str | None:
        """ Parser customizado para o InfoMoney. """
        settings.logger.info(f"Usando fallback de extração para InfoMoney: {url}")
        try:
            response = requests.get(url, headers=self.request_headers, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            content_div = soup.find('div', class_='article-content') # Este seletor é um palpite
            if content_div:
                return content_div.get_text(separator='\n', strip=True)
            return None
        except Exception as e:
            settings.logger.error(f"Erro no fallback para InfoMoney: {e}")
            return None

    def extract_text_from_url(self, url: str) -> str | None:
        """ Método principal que decide qual extrator usar. """
        hostname = urlparse(url).hostname or ""
        
        if "infomoney.com.br" in hostname:
            return self._extract_with_fallback_infomoney(url)
        # elif "veja.abril.com.br" in hostname:
        #     return self._extract_with_fallback_veja(url)
        
        return self._extract_with_newspaper(url)