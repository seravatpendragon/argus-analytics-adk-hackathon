import os
import sys
from pathlib import Path
import asyncio

# --- Bloco Padrão de Configuração e Imports ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())

try:
    from config import settings
    from src.agents.extratores.agente_extrator_conteudo_adk.tools.tool_fetch_articles_pending_extraction import tool_fetch_articles_pending_extraction
    from src.agents.extratores.agente_extrator_conteudo_adk.tools.tool_extract_and_save_content import tool_extract_and_save_content
except ImportError as e:
    import logging
    _logger = logging.getLogger(__name__)
    _logger.critical(f"Erro CRÍTICO de import no script extrator: {e}", exc_info=True)
    sys.exit(1)


# --- Bloco Principal de Execução ---
if __name__ == '__main__':
    settings.logger.info("--- Iniciando Pipeline de Extração de Conteúdo (Modo Script) ---")
    
    erros = 0
    sucessos = 0
    
    try:
        fetch_result = tool_fetch_articles_pending_extraction()
        articles_to_process = fetch_result.get("articles_to_process", [])
        
        if not articles_to_process:
            print("Nenhum artigo para processar. Encerrando.")
        else:
            print(f"Encontrados {len(articles_to_process)} artigos. Iniciando extração...")
            
            for article in articles_to_process:
                article_id = article.get("article_id")
                url = article.get("url")
                if not article_id or not url: continue
                
                result = tool_extract_and_save_content(article_id=article_id, url=url)
                
                if result.get("status") in ["success", "success_skipped"]:
                    sucessos += 1
                else:
                    erros += 1

    except Exception as e:
        settings.logger.critical(f"FALHA GERAL NO PIPELINE DE EXTRAÇÃO: {e}", exc_info=True)
    finally:
        print("\n--- Resumo da Execução ---")
        print(f"Pipeline de extração concluído.")
        print(f"Artigos com Sucesso (ou pulados corretamente): {sucessos}")
        print(f"Artigos com Falha: {erros}")
        settings.logger.info("--- Fim do Pipeline de Extração ---")