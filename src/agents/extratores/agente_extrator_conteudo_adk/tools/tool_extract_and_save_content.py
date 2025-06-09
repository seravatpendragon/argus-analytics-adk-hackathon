# src/agents/extratores/agente_extrator_conteudo_adk/tools/tool_extract_and_save_content.py
import time
from config import settings
from sqlalchemy.orm import Session
from src.database.db_utils import get_db_session, update_article_with_full_text
from src.data_processing.content_extractor import ContentExtractor

def tool_extract_and_save_content(article_id: int, url: str) -> dict:
    """
    Extrai o texto de uma URL, valida sua qualidade, o salva no banco
    e reporta o status real da operação.
    """
    time.sleep(1) # Delay para um scraping cortês
    settings.logger.info(f"Iniciando extração para article_id: {article_id}")
    
    db_session: Session | None = None
    try:
        extractor = ContentExtractor()
        full_text = extractor.extract_text_from_url(url)
        
        # Filtro de qualidade robusto, como você especificou
        palavras_inuteis = ["publicidade", "anúncio", "deseja receber notificações", "assine nosso boletim"]
        
        status_retorno = "success"
        message = ""
        
        if not full_text or len(full_text) < 250 or any(palavra in full_text.lower() for palavra in palavras_inuteis):
            message = f"Extração para article_id {article_id} falhou: conteúdo ausente, curto ou irrelevante."
            new_status_db = 'extraction_failed'
            full_text_to_save = None
            status_retorno = "partial_failure"
        else:
            message = f"Extração para article_id {article_id} bem-sucedida. {len(full_text)} caracteres."
            new_status_db = 'pending_llm_analysis'
            full_text_to_save = full_text
        
        # Gestão de sessão de banco de dados, como você especificou
        db_session = get_db_session()
        update_success = update_article_with_full_text(db_session, article_id, full_text_to_save, new_status_db)
        
        if not update_success:
            raise Exception(f"Falha ao ATUALIZAR o banco para o article_id {article_id}")

        db_session.commit()
        settings.logger.info(message) # Log aprimorado
        
        return {"status": status_retorno, "article_id": article_id, "message": message}

    except Exception as e:
        if db_session: db_session.rollback() # Garante integridade
        settings.logger.error(f"Erro CRÍTICO na ferramenta 'extract_and_save' para article_id {article_id}: {e}", exc_info=True)
        return {"status": "error", "article_id": article_id, "message": str(e)}
    finally:
        if db_session: db_session.close() # Previne vazamentos de conexão