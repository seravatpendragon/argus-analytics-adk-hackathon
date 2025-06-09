# src/agents/extratores/agente_extrator_conteudo_adk/tools/tool_fetch_articles_pending_extraction.py
from config import settings
from src.database.db_utils import get_db_session, get_articles_pending_extraction

def tool_fetch_articles_pending_extraction() -> dict:
    """ Busca no banco uma lista de artigos pendentes de extração de texto. """
    # O limite agora é uma configuração interna da ferramenta.
    # Você pode mudar este número para controlar o tamanho do lote.
    LIMIT_DE_ARTIGOS_POR_LOTE = 50
    
    settings.logger.info(f"Buscando até {LIMIT_DE_ARTIGOS_POR_LOTE} artigos pendentes de extração...")
    db_session = None
    try:
        db_session = get_db_session()
        articles = get_articles_pending_extraction(db_session, limit=LIMIT_DE_ARTIGOS_POR_LOTE)
        articles_data = [
            {"article_id": a.news_article_id, "url": a.article_link}
            for a in articles
        ]
        return {"status": "success", "articles_to_process": articles_data}
    except Exception as e:
        settings.logger.error(f"Erro em tool_fetch_articles: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
    finally:
        if db_session: db_session.close()