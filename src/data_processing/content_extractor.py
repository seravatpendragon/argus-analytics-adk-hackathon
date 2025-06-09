# src/data_processing/content_extractor.py
from newspaper import Article, ArticleException
from config import settings

class ContentExtractor:
    """ Especialista em receber uma URL e extrair o texto limpo do artigo. """
    def __init__(self):
        # Usa a configuração aprimorada que definimos no settings.py
        self.config = settings.get_newspaper3k_config()

    def extract_text_from_url(self, url: str) -> str | None:
        """ Baixa, processa e extrai o texto principal de uma URL. """
        try:
            settings.logger.info(f"Extraindo conteúdo de: {url}")
            article = Article(url, config=self.config)
            article.download()
            article.parse()
            return article.text
        # Separa erros esperados (ex: 404, página inválida) de erros inesperados
        except ArticleException as e:
            settings.logger.warning(f"Falha de extração com newspaper3k para a URL: {url}. Erro: {e}")
            return None
        except Exception as e:
            settings.logger.error(f"Erro inesperado ao extrair de {url}: {e}", exc_info=True)
            return None