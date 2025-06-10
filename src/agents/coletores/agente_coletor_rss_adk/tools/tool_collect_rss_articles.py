# src/agents/agente_coletor_rss_adk/tools/tool_collect_rss_articles.py

import json
from pathlib import Path
import time
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from config import settings
from src.database.db_utils import get_db_session, get_company_id_for_ticker, get_segment_id_by_name
from src.database.create_db_tables import NewsArticle, NewsArticleCompanyLink, NewsArticleSegmentLink
from src.data_collection.news_data.news_rss_collector import RSSCollector

def load_json_file(file_path: Path) -> list | None:
    if not file_path.exists():
        settings.logger.error(f"Arquivo de configuração não encontrado: {file_path}")
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        settings.logger.error(f"Erro ao ler {file_path}: {e}", exc_info=True)
        return None

def tool_collect_rss_articles() -> dict:
    """ Coleta artigos de Feeds RSS e os persiste no banco de dados. """
    settings.logger.info("Ferramenta 'tool_collect_rss_articles' iniciada...")
    db_session: Session | None = None
    collector: RSSCollector | None = None # Inicia como None
    try:
        db_session = get_db_session()
        
        config_dir = Path(settings.BASE_DIR) / "config"
        rss_sources_config = load_json_file(config_dir / "rss_news_config.json")
        if not isinstance(rss_sources_config, list):
             raise ValueError("Configuração de Feeds RSS não encontrada ou não é uma lista.")
        
        credibility_data = load_json_file(config_dir / "news_source_domain.json") or {}

        collector = RSSCollector(db_session=db_session, credibility_data=credibility_data)
        
        all_prepared_data = []
        for feed_config in rss_sources_config:
            prepared_tuples = collector.run_single_feed(feed_config)
            if prepared_tuples:
                all_prepared_data.extend(prepared_tuples)
            if len(rss_sources_config) > 1:
                time.sleep(0.5)

        if not all_prepared_data:
            return {"status": "success", "message": "Nenhum artigo novo para inserir dos Feeds RSS."}

        # Etapa A: Inserir todos os artigos
        all_article_dicts = [data[0] for data in all_prepared_data]
        stmt = pg_insert(NewsArticle).values(all_article_dicts).on_conflict_do_nothing(index_elements=['article_link'])
        result = db_session.execute(stmt)
        
        # Etapa B: Criar os Vínculos
        links_created = 0
        for article_dict, target_ticker, target_segment in all_prepared_data:
            article_id = db_session.query(NewsArticle.news_article_id).filter(NewsArticle.article_link == article_dict['article_link']).scalar()
            if not article_id: continue

            if target_ticker:
                company_id = get_company_id_for_ticker(db_session, target_ticker)
                if company_id:
                    link_stmt = pg_insert(NewsArticleCompanyLink).values(news_article_id=article_id, company_id=company_id).on_conflict_do_nothing()
                    db_session.execute(link_stmt)
                    links_created +=1
            
            if target_segment:
                segment_id = get_segment_id_by_name(db_session, target_segment)
                if segment_id:
                    link_stmt = pg_insert(NewsArticleSegmentLink).values(news_article_id=article_id, segment_id=segment_id).on_conflict_do_nothing()
                    db_session.execute(link_stmt)

        db_session.commit()
        
        return { "status": "success", "message": f"Coleta RSS concluída. {result.rowcount} novos artigos inseridos e {links_created} vínculos processados." }

    except Exception as e:
        if db_session: db_session.rollback()
        settings.logger.error(f"Erro na ferramenta tool_collect_rss_articles: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
    finally:
        # GARANTE QUE O NAVEGADOR SEJA FECHADO NO FINAL
        if collector:
            collector.close()
        if db_session:
            db_session.close()