import os
import sys
import json
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any

# --- Bloco Padrão de Configuração e Imports ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())

try:
    from config import settings
    from google.adk.agents import LlmAgent
    from google.adk.tools import google_search
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai.types import Content, Part
    from src.database.db_utils import get_db_session, get_sources_pending_craap_analysis, update_source_craap_analysis
    from src.database.create_db_tables import NewsSource
    from . import prompt as agent_prompt
except ImportError as e:
    import logging
    _logger = logging.getLogger(__name__)
    _logger.critical(f"Erro CRÍTICO de importação: {e}", exc_info=True)
    sys.exit(1)


# --- Bloco de Autenticação ---
if settings.GEMINI_API_KEY:
    os.environ["GOOGLE_API_KEY"] = settings.GEMINI_API_KEY
else:
    raise ValueError("GEMINI_API_KEY não encontrada!")

agente_config = settings.AGENT_CONFIGS.get("avaliador", {})
MODELO_LLM_AGENTE = agente_config.get("model_name", "gemini-1.5-pro-001")

# --- Definição do Agente ---
AgenteAvaliadorDeFontes_ADK = LlmAgent(
    name="agente_avaliador_fontes_v1",
    model=MODELO_LLM_AGENTE,
    instruction=agent_prompt.PROMPT,
    description="Agente especialista que usa google_search para avaliar a credibilidade.",
    tools=[google_search],
)

async def analyze_one_source(runner: Runner, source: NewsSource) -> tuple[int, Optional[Dict[str, Any]]]:
    """ Função assíncrona que executa a análise para UMA única fonte. """
    session_id = f"craap_session_{source.news_source_id}"
    await runner.session_service.create_session(
        app_name=runner.app_name, user_id="system_user", session_id=session_id
    )
    
    prompt_text = f"Analise o domínio: {source.url_base}"
    
    # CORREÇÃO: Voltando para a forma padrão e correta de criar o objeto Part.
    message = Content(role='user', parts=[Part(text=prompt_text)])
    
    final_agent_response = None
    try:
        async for event in runner.run_async(user_id="system_user", session_id=session_id, new_message=message):
            if event.is_final_response() and event.content and event.content.parts:
                final_agent_response = event.content.parts[0].text
        
        if final_agent_response:
            try:
                json_str = final_agent_response.strip().removeprefix("```json").removesuffix("```")
                return source.news_source_id, json.loads(json_str)
            except json.JSONDecodeError as e:
                settings.logger.error(f"Não foi possível decodificar JSON para a fonte '{source.name}': {e}")
    except Exception as e:
        settings.logger.error(f"Erro na execução do runner para a fonte '{source.name}': {e}", exc_info=True)

    return source.news_source_id, None

async def run_craap_analysis_pipeline():
    """ Orquestra o processo completo, agora de forma concorrente. """
    settings.logger.info("--- Iniciando Pipeline de Análise de Credibilidade (v2 - Concorrente) ---")
    
    with get_db_session() as db_session:
        sources = get_sources_pending_craap_analysis(db_session, limit=settings.QUANTIDADE_AVALIACAO)
        if not sources:
            print("Nenhuma fonte nova para analisar.")
            return

        print(f"Encontradas {len(sources)} fontes. Criando tarefas de análise...")
        
        runner = Runner(agent=AgenteAvaliadorDeFontes_ADK, app_name="craap_app", session_service=InMemorySessionService())
        
        # Cria uma lista de tarefas assíncronas
        tasks = [analyze_one_source(runner, source) for source in sources]
        
        # Executa todas as tarefas de forma concorrente
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        updates_succeeded = 0
        for result in results:
            if isinstance(result, Exception):
                settings.logger.error(f"Uma tarefa de análise falhou com uma exceção: {result}")
                continue

            source_id, analysis_json = result
            if analysis_json:
                score = analysis_json.get("overall_credibility_score")
                if score is not None:
                    print(f"-> Análise para source_id {source_id} concluída. Score: {score}")
                    update_source_craap_analysis(db_session, source_id, float(score), analysis_json)
                    updates_succeeded += 1
                else:
                    settings.logger.warning(f"Análise para source_id {source_id} não continha score.")
            else:
                settings.logger.error(f"Análise para source_id {source_id} retornou nula.")
        
        if updates_succeeded > 0:
            db_session.commit()
            print(f"\n{updates_succeeded} análises salvas no banco com sucesso.")
        else:
            print("\nNenhuma análise bem-sucedida para salvar.")

if __name__ == '__main__':
    try:
        asyncio.run(run_craap_analysis_pipeline())
    except Exception as e:
        settings.logger.critical(f"❌ FALHA GERAL NO PIPELINE: {e}", exc_info=True)