import os
import sys
import asyncio
import json
from pathlib import Path

# Bloco de import padrão
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())

from src.agents.agent_utils import run_agent_and_get_final_response
from config import settings
# Importa nosso Gerente de Análise e as ferramentas de banco de dados
from src.agents.analistas.agente_gerenciador_analise_adk.agent import AgenteGerenciadorAnalise_ADK
from src.utils.parser_utils import parse_llm_json_response 
from src.database.db_utils import get_articles_pending_analysis, get_db_session, update_article_with_analysis

MAX_CONCURRENT_TASKS = 5

async def analyze_and_save_article(article: dict, semaphore: asyncio.Semaphore):
    """Orquestra a análise, agora com parsing, de um único artigo."""
    async with semaphore:
        article_id = article.get("article_id")
        text = article.get("text")

        if not all([article_id, text]):
            return False

        settings.logger.info(f"Iniciando análise 360° para o artigo ID: {article_id}")

        try:
            # Etapa 1: Rodar o agente e obter a resposta de texto bruta
            raw_response_text = await run_agent_and_get_final_response(
                agent=AgenteGerenciadorAnalise_ADK,
                user_prompt=text,
                user_id_prefix=f"pipeline_{article_id}"
            )

            if raw_response_text:
                # Etapa 2: Usar nosso parser para limpar e converter a resposta em um dicionário
                analysis_dict = parse_llm_json_response(raw_response_text)
                
                if analysis_dict:
                    # Etapa 3: Salvar o dicionário limpo no banco de dados
                    update_article_with_analysis(article_id, analysis_dict)
                    return True
                else:
                    settings.logger.error(f"Falha ao fazer o PARSE da resposta JSON para o artigo {article_id}.")
                    return False
            else:
                settings.logger.error(f"O agente gerenciador não retornou uma análise final para o artigo {article_id}.")
                return False
        except Exception as e:
            settings.logger.critical(f"Falha crítica ao analisar o artigo {article_id}: {e}", exc_info=True)
            return False



async def main():
    """Função principal que busca artigos e dispara as análises com controle de concorrência."""
    settings.logger.info("--- INICIANDO PIPELINE DE ANÁLISE DE CONTEÚDO EM LOTE ---")
    
    with get_db_session() as session:
        articles_to_analyze = get_articles_pending_analysis(session, limit=1) 
    
    if not articles_to_analyze:
        print("Nenhum artigo novo para analisar. Pipeline concluído.")
        return

    print(f"Encontrados {len(articles_to_analyze)} artigos. Iniciando análise com concorrência máxima de {MAX_CONCURRENT_TASKS}...")
    
    # --- MUDANÇA 2: Criando o Semáforo ---
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

    # Não precisamos mais criar o Runner aqui, a função auxiliar cuida disso.
    tasks = [analyze_and_save_article(article, semaphore) for article in articles_to_analyze]
    results = await asyncio.gather(*tasks)
    
    sucessos = sum(1 for r in results if r)
    falhas = len(results) - sucessos
    
    print("\n--- RESUMO DO PIPELINE DE ANÁLISE ---")
    print(f"Análise em lote concluída.")
    print(f"Artigos analisados com sucesso: {sucessos}")
    print(f"Falhas na análise: {falhas}")

if __name__ == "__main__":
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    asyncio.run(main())