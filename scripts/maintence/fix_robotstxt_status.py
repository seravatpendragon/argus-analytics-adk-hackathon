import os
import sys
from pathlib import Path

# Bloco de import padrão
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())

from config import settings
from src.database.db_utils import get_db_session
from src.database.create_db_tables import NewsArticle
from sqlalchemy import func

def fix_robotstxt_blocked_articles():
    """
    Encontra artigos marcados como bloqueados por robots.txt mas que não têm
    o status de processamento correto ('extraction_blocked') e os corrige.
    """
    settings.logger.info("--- Iniciando Script de Correção de Status para Artigos Bloqueados por robots.txt ---")

    with get_db_session() as session:
        try:
            # Query para encontrar os artigos com o status errado
            articles_to_fix_query = session.query(NewsArticle).filter(
                NewsArticle.article_text_content == 'EXTRACAO_BLOQUEADA_POR_ROBOTS_TXT',
                NewsArticle.processing_status != 'extraction_blocked'
            )

            count_to_update = articles_to_fix_query.count()

            if count_to_update == 0:
                print("Nenhum artigo bloqueado por robots.txt com status inconsistente foi encontrado. O banco de dados está limpo!")
                return

            print(f"Encontrados {count_to_update} artigos bloqueados por robots.txt com status incorreto. Atualizando para 'extraction_blocked'...")

            # Executa o update em lote
            articles_to_fix_query.update(
                {"processing_status": "extraction_blocked"},
                synchronize_session=False
            )

            session.commit()

            print(f"✅ Sucesso! {count_to_update} artigos tiveram seu status corrigido.")

        except Exception as e:
            session.rollback()
            settings.logger.error(f"Ocorreu um erro durante a correção de status: {e}", exc_info=True)
            print("❌ Erro durante a execução do script. Verifique os logs.")

if __name__ == "__main__":
    fix_robotstxt_blocked_articles()