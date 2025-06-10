import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from config import settings
from sqlalchemy.orm import Session
from src.database.db_utils import get_db_session # Não precisamos mais de update_article_with_full_text
from src.data_processing.content_extractor import ContentExtractor
from src.database.create_db_tables import NewsArticle

MAX_EXTRACTION_RETRIES = 5
BASE_RETRY_DELAY_SECONDS = 60 

def tool_extract_and_save_content(article_id: int, url: str) -> dict:
    time.sleep(1.5)
    settings.logger.info(f"Processando extração para article_id: {article_id}, URL: {url}")
    
    db_session: Session | None = None
    try:
        db_session = get_db_session()
        # Buscamos o objeto 'article' UMA VEZ e trabalhamos nele
        article = db_session.query(NewsArticle).filter(NewsArticle.news_article_id == article_id).first()
        if not article:
            raise ValueError(f"Artigo com ID {article_id} não encontrado no banco de dados.")

        is_cvm_link = "rad.cvm.gov.br" in url
        is_direct_file = url.lower().endswith(('.pdf', '.zip', '.docx', '.xlsx'))

        if is_cvm_link or is_direct_file:
            article.processing_status = 'processed_document'
            message = f"Artigo ID {article_id} identificado como documento direto. Extração não aplicável."
            status_retorno = "success_skipped"
        else:
            extractor = ContentExtractor()
            full_text = extractor.extract_text_from_url(url)
            
            palavras_inuteis = ["publicidade", "anúncio", "assine nosso boletim", "faça seu login"]
            
            if not full_text or len(full_text) < 250 or any(palavra in full_text.lower() for palavra in palavras_inuteis):
                article.retries_count = (article.retries_count or 0) + 1 # Segurança extra
                if article.retries_count < MAX_EXTRACTION_RETRIES:
                    delay = BASE_RETRY_DELAY_SECONDS * (2 ** article.retries_count)
                    article.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                    message = f"Extração falhou para article_id {article_id} (tentativa {article.retries_count}). Próxima tentativa agendada."
                    article.processing_status = 'pending_extraction_retry'
                    status_retorno = "partial_failure"
                else:
                    message = f"Extração falhou permanentemente para article_id {article_id}."
                    article.processing_status = 'extraction_failed'
                    article.next_retry_at = None
                    status_retorno = "failure"
            else:
                article.article_text_content = full_text
                article.processing_status = 'pending_llm_analysis'
                article.retries_count = 0
                article.next_retry_at = None
                message = f"Extração bem-sucedida para article_id {article_id}. {len(full_text)} caracteres."
                status_retorno = "success"
        
        # Todas as alterações são marcadas no objeto 'article'
        article.last_processed_at = datetime.now(timezone.utc)

        # O commit salva TODAS as alterações feitas no objeto 'article'
        db_session.commit()
        settings.logger.info(message)
        
        return {"status": status_retorno, "article_id": article_id, "message": message}

    except Exception as e:
        if db_session: db_session.rollback()
        settings.logger.error(f"Erro CRÍTICO na ferramenta 'extract_and_save' para article_id {article_id}: {e}", exc_info=True)
        return {"status": "error", "article_id": article_id, "message": str(e)}
    finally:
        if db_session: db_session.close()