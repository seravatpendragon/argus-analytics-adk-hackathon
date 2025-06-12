import os
import sys
import json
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any

# --- Imports do Projeto ---
try:
    from config import settings
    from google import genai
    from google.genai.types import Tool, GoogleSearch
    from src.database.db_utils import get_db_session, get_sources_pending_craap_analysis, update_source_craap_analysis
    from src.database.create_db_tables import NewsSource
    from . import prompt as agent_prompt
except ImportError as e:
    import logging
    logging.basicConfig(level=logging.CRITICAL)
    logging.critical(f"Erro CRÍTICO de importação: {e}.")
    sys.exit(1)

logger = settings.logger

# --- Interação Direta usando o padrão do Notebook ---

# 1. Configura o cliente genai para usar o Vertex AI
try:
    # Garantimos que as configurações existem antes de tentar usá-las
    if not settings.PROJECT_ID or not settings.LOCATION:
        raise ValueError("As variáveis de ambiente GOOGLE_CLOUD_PROJECT e GOOGLE_CLOUD_LOCATION precisam ser definidas.")
        
    logger.info(f"Configurando cliente para o projeto: {settings.PROJECT_ID} na localização: {settings.LOCATION}")
    client = genai.Client(project=settings.PROJECT_ID, location=settings.LOCATION)
    
    # 2. Habilita a ferramenta google_search
    google_search_tool = Tool(google_search=GoogleSearch())
    
    # 3. Inicializa o modelo através do cliente
    vertex_model = client.get_model("gemini-1.5-pro")

except Exception as e:
    logger.critical(f"Falha ao inicializar o cliente ou modelo do Google GenAI. Verifique o projeto e a autenticação. Erro: {e}")
    sys.exit(1)


async def process_single_source(source: NewsSource) -> Optional[Dict[str, Any]]:
    """Usa o cliente genai diretamente para analisar uma única fonte."""
    
    logger.info(f"Iniciando análise para: {source.name} ({source.url_base})")
    
    try:
        prompt_completo = (
            f"{agent_prompt.PROMPT}\n\n"
            f"Sua tarefa é executar essa análise para o seguinte domínio: **{source.url_base}**"
        )
        
        response = await vertex_model.generate_content_async(
            contents=prompt_completo,
            tools=[google_search_tool]
        )
        
        final_agent_response = response.text
        
        if final_agent_response:
            json_str = final_agent_response.strip().removeprefix("```json").removesuffix("```")
            return json.loads(json_str)

    except json.JSONDecodeError:
        logger.error(f"Não foi possível decodificar a resposta JSON do LLM para a fonte {source.name}: '{final_agent_response}'")
    except Exception as e:
        logger.error(f"Erro inesperado durante a chamada do modelo para {source.name}: {e}", exc_info=True)
        
    return None

async def run_craap_analysis_pipeline():
    """Orquestra o processo de ponta a ponta: buscar, analisar e salvar."""
    logger.info("--- Iniciando Pipeline de Análise de Credibilidade de Fontes ---")
    
    with get_db_session() as db_session:
        sources_to_analyze = get_sources_pending_craap_analysis(db_session, limit=3)
        
        if not sources_to_analyze:
            logger.info("Nenhuma fonte nova para analisar. Pipeline concluído.")
            return

        logger.info(f"Encontradas {len(sources_to_analyze)} fontes para análise CRAAP.")
        
        tasks = [process_single_source(source) for source in sources_to_analyze]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            source = sources_to_analyze[i]
            if isinstance(result, Exception):
                logger.error(f"A tarefa para '{source.name}' falhou com uma exceção: {result}")
                continue

            if result:
                score = result.get("overall_credibility_score")
                if score is not None:
                    logger.info(f"Análise de '{source.name}' concluída. Score: {score}")
                    update_source_craap_analysis(db_session, source.news_source_id, float(score), result)
                else:
                    logger.warning(f"Análise para '{source.name}' não continha 'overall_credibility_score'.")
            else:
                 logger.error(f"Falha ao processar a análise para '{source.name}'. Pulando.")
        
        try:
            db_session.commit()
            logger.info("Todas as análises foram salvas no banco de dados com sucesso.")
        except Exception as e:
            logger.error(f"Falha ao commitar as análises no banco. Revertendo alterações. Erro: {e}", exc_info=True)
            db_session.rollback()

    logger.info("--- Fim do Pipeline de Análise de Credibilidade ---")


if __name__ == '__main__':
    asyncio.run(run_craap_analysis_pipeline())