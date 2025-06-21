# Em: scripts/maintenance/run_conflict_detection_backfill.py

import sys
import asyncio
from pathlib import Path

# Adiciona o root do projeto ao path para permitir imports
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent
    if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path.cwd()
    if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.orm import Session, joinedload
from config import settings
from src.database.db_utils import get_db_session
from src.database.create_db_tables import NewsArticle, NewsSource
from src.data_processing.conflict_detector import ConflictDetector

def get_articles_for_reprocessing(session: Session, limit: int = 5000):
    """Busca artigos que já têm análise mas ainda não passaram pelo detector de conflitos."""
    settings.logger.info(f"Buscando até {limit} artigos para reprocessamento de conflitos...")
    return (
        session.query(NewsArticle)
        .options(joinedload(NewsArticle.news_source))
        .filter(
            NewsArticle.processing_status == 'analysis_complete',
            NewsArticle.llm_analysis_json.isnot(None),
            NewsArticle.conflict_analysis_json.is_(None) # Pega apenas os que não foram auditados
        )
        .limit(limit)
        .all()
    )

async def main():
    """
    Script principal para rodar o detector de conflitos em análises existentes.
    """
    settings.logger.info("--- INICIANDO SCRIPT DE BACKFILL DO DETECTOR DE CONFLITOS ---")
    
    processed_count = 0
    with get_db_session() as session:
        articles_to_reprocess = get_articles_for_reprocessing(session)
        
        if not articles_to_reprocess:
            settings.logger.info("Nenhum artigo para reprocessar. Todos já possuem análise de conflito.")
            return

        settings.logger.info(f"Encontrados {len(articles_to_reprocess)} artigos para terem seus conflitos analisados.")
        
        for article in articles_to_reprocess:
            try:
                analysis_data = article.llm_analysis_json
                credibility = article.news_source.base_credibility_score if article.news_source else 0.5
                
                detector = ConflictDetector(analysis_data, credibility)
                conflict_result = detector.run()
                
                # Atualiza a nova coluna no banco de dados
                article.conflict_analysis_json = conflict_result
                
                processed_count += 1
                if processed_count % 100 == 0:
                    settings.logger.info(f"{processed_count}/{len(articles_to_reprocess)} artigos reprocessados...")

            except Exception as e:
                settings.logger.error(f"Erro ao processar o artigo {article.news_article_id}: {e}")
                article.conflict_analysis_json = {
                    "confidence_score": 0, "conflicts": [f"Erro no processamento: {e}"]
                }

        settings.logger.info("Salvando todas as atualizações no banco de dados...")
        session.commit()
        settings.logger.info("Backfill concluído com sucesso!")

if __name__ == "__main__":
    asyncio.run(main())