import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from config import settings
from sqlalchemy.orm import Session
from src.database.db_utils import get_db_session
from src.data_processing.content_extractor import ContentExtractor
from src.database.create_db_tables import NewsArticle

MAX_EXTRACTION_RETRIES = 5
BASE_RETRY_DELAY_SECONDS = 60

def tool_extract_and_save_content(article_id: int, url: str) -> dict:
    """
    Extrai o texto de uma URL, lida com diferentes formatos e falhas,
    e atualiza o status do artigo no banco de dados.
    """
    time.sleep(1.5) # Delay para um scraping cortês
    settings.logger.info(f"Processando extração para article_id: {article_id}, URL: {url}")

    db_session: Session | None = None
    try:
        db_session = get_db_session()
        article = db_session.query(NewsArticle).filter(NewsArticle.news_article_id == article_id).first()
        if not article:
            raise ValueError(f"Artigo com ID {article_id} não encontrado.")

        status_retorno = "error"
        message = f"Erro inesperado no processamento do article_id {article_id}."

        extractor = ContentExtractor()
        full_text = extractor.extract_text_from_url(url)

        # --- INÍCIO DA CORREÇÃO ---
        # Limpa caracteres NUL (0x00) do texto extraído antes de qualquer processamento ou salvamento.
        if full_text is not None: # Garante que full_text não é None antes de tentar o replace
            full_text = full_text.replace('\x00', '')
        # --- FIM DA CORREÇÃO ---

        palavras_inuteis = ["publicidade", "anúncio", "assine nosso boletim", "faça seu login"]

        if full_text == "EXTRACAO_BLOQUEADA_POR_ROBOTS_TXT":
            message = f"Extração para article_id {article_id} bloqueada por robots.txt."
            article.processing_status = 'extraction_blocked'
            status_retorno = "skipped_robots"
        # O 'elif' abaixo também se beneficia da limpeza, pois o len() e 'any()' usarão o texto limpo
        elif not full_text or len(full_text) < 250 or any(palavra in full_text.lower() for palavra in palavras_inuteis):
            article.retries_count = (article.retries_count or 0) + 1
            if article.retries_count < MAX_EXTRACTION_RETRIES:
                delay = BASE_RETRY_DELAY_SECONDS * (2 ** article.retries_count)
                article.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                message = f"Extração falhou para article_id {article_id} (tentativa {article.retries_count}). Próxima agendada."
                article.processing_status = 'pending_extraction_retry'
                status_retorno = "partial_failure"
            else:
                message = f"Extração falhou permanentemente para article_id {article_id} após {MAX_EXTRACTION_RETRIES} tentativas."
                article.processing_status = 'extraction_failed'
                status_retorno = "failure"
        else:
            article.article_text_content = full_text # Aqui o texto já estará limpo
            article.processing_status = 'pending_llm_analysis'
            article.retries_count = 0
            article.next_retry_at = None
            message = f"Extração bem-sucedida para article_id {article_id}. {len(full_text)} caracteres."
            status_retorno = "success"

        article.last_processed_at = datetime.now(timezone.utc)
        db_session.commit() # <--- Esta é a linha onde o erro original ocorreu
                            # Agora, o full_text que chega aqui estará limpo de '\x00'.

        settings.logger.info(message)
        return {"status": status_retorno, "article_id": article_id, "message": message}

    except Exception as e:
        if db_session: db_session.rollback()
        settings.logger.error(f"Erro CRÍTICO na ferramenta 'extract_and_save' para article_id {article_id}: {e}", exc_info=True)
        return {"status": "error", "article_id": article_id, "message": str(e)}
    finally:
        if db_session: db_session.close()