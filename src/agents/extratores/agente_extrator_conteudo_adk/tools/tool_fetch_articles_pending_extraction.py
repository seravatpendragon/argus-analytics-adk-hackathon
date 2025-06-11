from config import settings
from src.database.db_utils import get_db_session, get_articles_pending_extraction

def tool_fetch_articles_pending_extraction(limit: int = 50) -> dict:
    """
    Busca no banco uma lista de artigos pendentes de extração de texto.
    """
    settings.logger.info(f"Buscando até {limit} artigos pendentes ou para retentativa de extração...")
    db_session = None
    try:
        db_session = get_db_session()
        articles = get_articles_pending_extraction(db_session, limit)
        
        # Converte os objetos SQLAlchemy em dicionários simples
        articles_data = [
            {"article_id": a.news_article_id, "url": a.article_link}
            for a in articles
        ]
        return {"status": "success", "articles_to_process": articles_data}
    except Exception as e:
        settings.logger.error(f"Erro em tool_fetch_articles: {e}", exc_info=True)
        return {"status": "error", "message": str(e), "articles_to_process": []}
    finally:
        if db_session:
            db_session.close()