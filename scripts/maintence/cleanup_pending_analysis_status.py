import os
import sys
from pathlib import Path

# Bloco de import padrão
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
from src.database.create_db_tables import NewsArticle
from sqlalchemy import or_, func

def cleanup_invalid_pending_articles():
    """
    Encontra artigos que estão na fila de análise ('pending_llm_analysis')
    mas não têm conteúdo de texto válido e os move para um status de falha.
    """
    settings.logger.info("--- Iniciando Script de Limpeza de Fila de Análise ---")
    
    MIN_LENGTH = 250 # O mesmo comprimento mínimo que usamos no extrator

    with get_db_session() as session:
        try:
            # Constrói a query para encontrar os "artigos-fantasma"
            invalid_articles_query = session.query(NewsArticle).filter(
                NewsArticle.processing_status == 'pending_llm_analysis',
                or_(
                    NewsArticle.article_text_content == None,
                    func.length(NewsArticle.article_text_content) < MIN_LENGTH
                )
            )
            
            # Conta quantos artigos serão atualizados antes de fazer a mudança
            count_to_update = invalid_articles_query.count()
            
            if count_to_update == 0:
                print("Nenhum artigo com status inválido encontrado. A fila de análise está limpa!")
                return

            print(f"Encontrados {count_to_update} artigos na fila de análise com conteúdo inválido. Atualizando status para 'extraction_failed'...")

            # Executa o update em lote para eficiência
            invalid_articles_query.update(
                {
                    "processing_status": "extraction_failed",
                    "last_processed_at": func.now()
                },
                synchronize_session=False
            )
            
            session.commit()
            
            print(f"✅ Sucesso! {count_to_update} artigos foram removidos da fila de análise e marcados como 'extraction_failed'.")

        except Exception as e:
            session.rollback()
            settings.logger.error(f"Ocorreu um erro durante a limpeza da fila de análise: {e}", exc_info=True)
            print("❌ Erro durante a execução do script. Verifique os logs.")

    settings.logger.info("--- Script de Limpeza Concluído ---")

if __name__ == "__main__":
    cleanup_invalid_pending_articles()