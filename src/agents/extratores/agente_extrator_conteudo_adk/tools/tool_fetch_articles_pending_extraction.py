# src/agents/extratores/agente_extrator_conteudo_adk/tools/tool_fetch_articles_pending_extraction.py
from datetime import datetime
from operator import or_
from config import settings
from database.create_db_tables import NewsArticle
from src.database.db_utils import get_db_session, get_articles_pending_extraction

def tool_fetch_articles_pending_extraction() -> dict:
    """ Busca no banco uma lista de artigos pendentes de extração de texto, incluindo retentativas. """
    LIMIT_DE_ARTIGOS_POR_LOTE = 20 # Pode ser configurável via settings.py se necessário

    db_session = None
    try:
        db_session = get_db_session()
        # Chama a função utilitária do banco de dados
        articles = get_articles_pending_extraction(db_session, limit=LIMIT_DE_ARTIGOS_POR_LOTE)
        
        articles_data = [
            {"article_id": a.news_article_id, "url": a.article_link}
            for a in articles
        ]
        
        # Opcional: Atualizar o status dos artigos pegos para 'extracting' para evitar que outros agentes peguem
        # Isso seria mais robusto se o status fosse atualizado *antes* de retornar,
        # para evitar concorrência se houver múltiplos extratores.
        # Por exemplo, definir 'extracting' e, se a extração falhar, voltar para 'pending_extraction_retry'
        # ou 'extraction_failed'.

        # Lógica para marcar como "em processamento" - isso é importante para evitar que múltiplas instâncias
        # do agente tentem processar o mesmo artigo simultaneamente.
        for article in articles:
            # Apenas muda se não for já 'extracting' (se a lógica de lock estiver sendo usada)
            if article.processing_status != 'extracting':
                article.processing_status = 'extracting'
        db_session.commit()
        
        return {"status": "success", "articles_to_process": articles_data}
    except Exception as e:
        if db_session: db_session.rollback()
        settings.logger.error(f"Erro em tool_fetch_articles_pending_extraction: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
    finally:
        if db_session: db_session.close()