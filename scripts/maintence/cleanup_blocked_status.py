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
from sqlalchemy import or_

def fix_incorrectly_queued_blocked_articles():
    """
    Encontra artigos que estão na fila de análise ('pending_llm_analysis')
    mas cujo conteúdo indica que a extração foi bloqueada (WAF/CAPTCHA)
    e corrige seu status para 'extraction_blocked'.
    """
    settings.logger.info("--- Iniciando Script de Correção para Artigos Bloqueados Incorretamente na Fila ---")
    
    # Mensagens que indicam um bloqueio definitivo
    BLOCKED_MESSAGES = [
        'EXTRACAO_BLOQUEADA_POR_ROBOTS_TXT',
        'CONTEUDO_BLOQUEADO_POR_WAF/CAPTCHA',
        'CONTEÚDO BLOQUEADO POR WAF/CAPTCHA'
    ]

    with get_db_session() as session:
        try:
            # Query para encontrar os artigos com o status errado
            articles_to_fix_query = session.query(NewsArticle).filter(
                NewsArticle.processing_status == 'pending_llm_analysis',
                NewsArticle.article_text_content.in_(BLOCKED_MESSAGES)
            )
            
            count_to_update = articles_to_fix_query.count()
            
            if count_to_update == 0:
                print("Nenhum artigo bloqueado com status inconsistente foi encontrado. A fila de análise está limpa!")
                return

            print(f"Encontrados {count_to_update} artigos bloqueados com status incorreto. Atualizando para 'extraction_blocked'...")

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
    fix_incorrectly_queued_blocked_articles()