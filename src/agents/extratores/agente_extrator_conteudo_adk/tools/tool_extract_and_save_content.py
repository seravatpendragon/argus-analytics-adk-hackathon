import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from config import settings
from sqlalchemy.orm import Session
from src.database.db_utils import get_db_session
from src.data_processing.content_extractor import ArgusContentExtractor
from src.database.create_db_tables import NewsArticle

MAX_EXTRACTION_RETRIES = 5
BASE_RETRY_DELAY_SECONDS = 60

def tool_extract_and_save_content(article_id: int, url: str) -> dict:
    """
    Extrai o texto de uma URL e atualiza o status do artigo no banco de dados
    com uma lógica de estados robusta.
    """
    time.sleep(1.5) 
    settings.logger.info(f"Processando extração para article_id: {article_id}, URL: {url}")

    db_session: Session | None = None
    try:
        db_session = get_db_session()
        article = db_session.query(NewsArticle).filter(NewsArticle.news_article_id == article_id).first()
        if not article:
            raise ValueError(f"Artigo com ID {article_id} não encontrado.")

        # Instancia nosso extrator
        extractor = ArgusContentExtractor()
        full_text = extractor.extract_text_from_url(url)
        
        status_retorno = "error"
        message = ""

        # --- NOVA LÓGICA DE ESTADOS ---

        # Cenário 1: Extração bem-sucedida
        if full_text and len(full_text) > settings.MIN_ARTICLE_LENGTH:
            article.article_text_content = full_text
            article.processing_status = 'pending_llm_analysis' # PRONTO PARA ANÁLISE
            article.retries_count = 0
            article.next_retry_at = None
            status_retorno = "success"
            message = f"Extração bem-sucedida para article_id {article_id}. {len(full_text)} caracteres."

        # Cenário 2: Extração bloqueada por CAPTCHA ou robots.txt
        elif full_text in ["EXTRACAO_BLOQUEADA_POR_ROBOTS_TXT", "CONTEUDO_BLOQUEADO_POR_WAF/CAPTCHA"]:
            article.processing_status = 'extraction_blocked' # FIM DA LINHA (BLOQUEADO)
            article.article_text_content = full_text
            status_retorno = "failure_blocked"
            message = f"Extração para article_id {article_id} bloqueada permanentemente."

        # Cenário 3: Falha na extração, mas ainda há tentativas
        elif article.retries_count < settings.MAX_EXTRACTION_RETRIES:
            article.retries_count += 1
            delay = settings.BASE_RETRY_DELAY_SECONDS * (2 ** article.retries_count)
            article.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            article.processing_status = 'pending_extraction_retry' # TENTAR DE NOVO
            status_retorno = "partial_failure"
            message = f"Extração falhou para article_id {article_id} (tentativa {article.retries_count}). Próxima agendada."
        
        # Cenário 4: Falha na extração, sem mais tentativas
        else:
            article.processing_status = 'extraction_failed' # FIM DA LINHA (FALHA)
            status_retorno = "failure"
            message = f"Extração falhou permanentemente para article_id {article_id} após {settings.MAX_EXTRACTION_RETRIES} tentativas."

        article.last_processed_at = datetime.now(timezone.utc)
        db_session.commit()
        
        settings.logger.info(message)
        return {"status": status_retorno, "article_id": article_id, "message": message}

    except Exception as e:
        if db_session: db_session.rollback()
        settings.logger.error(f"Erro CRÍTICO na ferramenta 'extract_and_save' para article_id {article_id}: {e}", exc_info=True)
        return {"status": "error", "article_id": article_id, "message": str(e)}
    finally:
        if db_session: db_session.close()