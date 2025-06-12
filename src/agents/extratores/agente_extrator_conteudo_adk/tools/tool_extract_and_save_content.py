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
        
        # Lista de termos que indicam uma página de CAPTCHA ou bloqueio
        palavras_de_bloqueio = [
            "not a robot", "unusual activity", "are you a robot", 
            "enable javascript", "please make sure your browser supports",
            "verificar que não é um robô"
        ]
        
        # Checagem 1: É uma página de bloqueio permanente?
        if full_text and any(palavra in full_text.lower() for palavra in palavras_de_bloqueio):
            message = f"Extração para article_id {article_id} bloqueada por página de CAPTCHA/WAF."
            article.processing_status = 'extraction_blocked' # Status final, não tenta de novo
            article.article_text_content = "CONTEÚDO BLOQUEADO POR WAF/CAPTCHA" # Salva um registro claro
            article.retries_count = MAX_EXTRACTION_RETRIES # Define para o máximo para sair da fila de retry
            article.next_retry_at = None
            status_retorno = "failure_blocked"
        
        # Checagem 2: Se não for um bloqueio, é uma falha normal (texto nulo ou curto)?
        elif not full_text or len(full_text) < 250:
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
        
        # Checagem 3: Se passou por tudo, é um sucesso!
        else:
            article.article_text_content = full_text
            article.processing_status = 'pending_llm_analysis'
            article.retries_count = 0
            article.next_retry_at = None
            message = f"Extração bem-sucedida para article_id {article_id}. {len(full_text)} caracteres."
            status_retorno = "success"

        # O resto da função, com o commit e o return, permanece o mesmo
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