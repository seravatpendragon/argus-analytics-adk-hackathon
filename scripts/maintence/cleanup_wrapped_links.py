import os
import sys
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import update

# --- Configuração de Caminhos ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from src.database.db_utils import get_db_session
from src.database.create_db_tables import NewsArticle, NewsArticleCompanyLink, NewsArticleSegmentLink
from src.data_collection.news_data.news_rss_collector import RSSCollector

def run_cleanup_task():
    """
    Orquestra a limpeza de links do Google News com transações granulares.
    """
    settings.logger.info("--- Iniciando Script de Limpeza de Links (Versão Robusta) ---")
    
    # ... (código para perguntar sobre Dry Run e Backup continua o mesmo) ...
    user_input = input("Executar em modo DRY RUN (simular, sem salvar)? (S/N): ").strip().lower()
    is_dry_run = user_input == 's'
    if not is_dry_run:
        confirm_input = input("ATENÇÃO: Script irá MODIFICAR o BD (UPDATE e DELETE). Fez BACKUP? (S/N): ").strip().lower()
        if confirm_input != 's':
            settings.logger.info("Limpeza abortada pelo usuário.")
            return

    db_session: Session | None = None
    collector: RSSCollector | None = None
    
    try:
        db_session = get_db_session()
        
        articles_to_fix = db_session.query(NewsArticle).filter(
            NewsArticle.article_link.like('%news.google.com/rss/articles%')
        ).all()

        if not articles_to_fix:
            settings.logger.info("Nenhum link para limpar. Trabalho concluído.")
            return

        settings.logger.info(f"Encontrados {len(articles_to_fix)} artigos para corrigir.")
        
        collector = RSSCollector(db_session=db_session, credibility_data={})
        
        updated_count, deleted_count, error_count = 0, 0, 0
        
        for article in articles_to_fix:
            try:
                original_google_link = article.article_link
                final_link, was_redirected = collector._get_final_article_link(original_google_link)
                
                if not was_redirected or final_link == original_google_link:
                    continue

                existing_article = db_session.query(NewsArticle.news_article_id).filter(
                    NewsArticle.article_link == final_link,
                    NewsArticle.news_article_id != article.news_article_id
                ).first()

                if existing_article:
                    settings.logger.warning(f"DUPLICATA: Artigo ID {article.news_article_id} -> link já existe no ID {existing_article.news_article_id}. {'DELETARIA' if is_dry_run else 'DELETANDO'}.")
                    if not is_dry_run:
                        db_session.query(NewsArticleCompanyLink).filter(NewsArticleCompanyLink.news_article_id == article.news_article_id).delete()
                        db_session.query(NewsArticleSegmentLink).filter(NewsArticleSegmentLink.news_article_id == article.news_article_id).delete()
                        db_session.delete(article)
                    deleted_count += 1
                else:
                    if is_dry_run:
                        settings.logger.info(f"[DRY RUN] Artigo ID {article.news_article_id} SERIA ATUALIZADO para: {final_link}")
                    else:
                        article.article_link = final_link
                        article.original_url = original_google_link
                        article.is_redirected = True
                        settings.logger.info(f"Artigo ID {article.news_article_id} marcado para ATUALIZAÇÃO.")
                    updated_count += 1
                
                # Se não for dry run, commita a transação para este artigo específico
                if not is_dry_run:
                    db_session.commit()

            except Exception as e:
                # Se algo der errado para ESTE artigo, desfaz a operação dele e continua
                settings.logger.error(f"Erro ao processar Artigo ID {article.news_article_id}. Pulando. Erro: {e}")
                error_count += 1
                if db_session and not is_dry_run:
                    db_session.rollback()

        settings.logger.info("--- Resumo da Limpeza ---")
        settings.logger.info(f"Artigos atualizados: {updated_count}")
        settings.logger.info(f"Duplicatas removidas: {deleted_count}")
        settings.logger.info(f"Erros encontrados: {error_count}")

    except Exception as e:
        settings.logger.error(f"Erro catastrófico no script: {e}", exc_info=True)
    finally:
        if db_session:
            db_session.close()
        if collector:
            collector.close()
            settings.logger.info("Driver do Selenium foi fechado.")

if __name__ == "__main__":
    run_cleanup_task()