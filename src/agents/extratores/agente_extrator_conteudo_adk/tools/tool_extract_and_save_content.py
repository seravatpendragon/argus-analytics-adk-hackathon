from pathlib import Path
import time
import requests
from config import settings
from sqlalchemy.orm import Session
from src.database.db_utils import get_db_session, update_article_with_full_text
from src.data_processing.content_extractor import ContentExtractor

def tool_extract_and_save_content(article_id: int, url: str) -> dict:
    time.sleep(1.5) # Aumentando o delay para sermos ainda mais corteses
    settings.logger.info(f"Processando extração para article_id: {article_id}, URL: {url}")
    
    db_session: Session | None = None
    try:
        # SUA SUGESTÃO IMPLEMENTADA: Detecção de tipo de conteúdo
        if url.lower().endswith(('.pdf', '.zip', '.docx', '.xlsx')):
            message = f"Artigo ID {article_id} pulado: formato de arquivo não suportado ({Path(url).suffix})."
            new_status_db = 'unsupported_format'
            status_retorno = "success_skipped"
            full_text_to_save = None
        else:
            # A lógica de extração principal
            extractor = ContentExtractor()
            full_text = extractor.extract_text_from_url(url)
            
            palavras_inuteis = ["publicidade", "anúncio", "assine nosso boletim", "faça seu login"]
            
            if not full_text or len(full_text) < 250 or any(palavra in full_text.lower() for palavra in palavras_inuteis):
                message = f"Extração para article_id {article_id} falhou: conteúdo ausente, curto ou irrelevante."
                new_status_db = 'extraction_failed'
                full_text_to_save = None
                status_retorno = "partial_failure"
            else:
                message = f"Extração para article_id {article_id} bem-sucedida. {len(full_text)} caracteres."
                new_status_db = 'pending_llm_analysis'
                full_text_to_save = full_text

        # Persistência no Banco de Dados
        db_session = get_db_session()
        update_success = update_article_with_full_text(db_session, article_id, full_text_to_save, new_status_db)
        
        if not update_success:
            raise Exception(f"Falha ao salvar o resultado no banco para o article_id {article_id}")

        db_session.commit()
        settings.logger.info(message)
        return {"status": status_retorno, "article_id": article_id, "message": message}
    except Exception as e:
        if db_session: db_session.rollback()
        settings.logger.error(f"Erro CRÍTICO na ferramenta 'extract_and_save' para article_id {article_id}: {e}", exc_info=True)
        return {"status": "error", "article_id": article_id, "message": f"CRITICAL Error: {e}"}
    finally:
        if db_session: db_session.close()