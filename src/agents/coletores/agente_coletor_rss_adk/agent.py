# src/agents/agente_coletor_rss_adk/agent.py

import os
import sys
from pathlib import Path
import json
import asyncio

# --- Bloco Padrão de Configuração e Imports ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

try:
    from config import settings
    from google.adk.agents import Agent
    from google.adk.tools import FunctionTool
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types
    from .tools.tool_collect_rss_articles import tool_collect_rss_articles
    from . import prompt as agent_prompt
except ImportError as e:
    import logging
    logging.basicConfig(level=logging.INFO)
    _logger = logging.getLogger(__name__)
    _logger.critical(f"Erro CRÍTICO ao importar módulos para AgenteColetorRSS_ADK: {e}")
    sys.exit(1)


# --- Definições do Agente ---
agente_config = settings.AGENT_CONFIGS.get("coletor", {})
MODELO_LLM_AGENTE = agente_config.get("model_name", "gemini-1.5-flash-001")
collect_rss_tool_adk_instance = FunctionTool(func=tool_collect_rss_articles)

AgenteColetorRSS_ADK = Agent(
    name="agente_coletor_rss_adk_v1",
    model=MODELO_LLM_AGENTE,
    description="Agente que inicia a coleta de notícias de Feeds RSS usando um arquivo de configuração.",
    instruction=agent_prompt.PROMPT,
    tools=[collect_rss_tool_adk_instance],
)

settings.logger.info(f"Agente '{AgenteColetorRSS_ADK.name}' carregado com o modelo '{MODELO_LLM_AGENTE}'.")

# --- Bloco de Teste Standalone ---
if __name__ == '__main__':
    settings.logger.info(f"--- Executando teste standalone para: {AgenteColetorRSS_ADK.name} ---")

    async def run_standalone_test():
        app_name = "test_app_rss"
        user_id = "test_user_rss"
        session_id = "test_session_rss"
        
        session_service = InMemorySessionService()
        runner = Runner(agent=AgenteColetorRSS_ADK, app_name=app_name, session_service=session_service)
        await session_service.create_session(app_name=app_name, user_id=user_id, session_id=session_id)
        
        prompt_text = "Inicie a coleta de notícias de Feeds RSS."
        settings.logger.info(f"Enviando prompt de teste: '{prompt_text}'")
        message = types.Content(role='user', parts=[types.Part(text=prompt_text)])
        
        final_tool_output = {}
        async for event in runner.run_async(new_message=message, user_id=user_id, session_id=session_id):
            if hasattr(event, "tool_response"): final_tool_output = event.tool_response.response

        print("\n--- Resumo do Teste RSS ---")
        if final_tool_output.get("status") == "success":
            print(f"✅ SUCESSO: {final_tool_output.get('message')}")
        else:
            print(f"❌ FALHA: {final_tool_output.get('message')}")

    try:
        asyncio.run(run_standalone_test())
    except Exception as e:
        settings.logger.critical(f"❌ FALHA: Ocorreu um erro inesperado durante a execução do teste: {e}", exc_info=True)

    settings.logger.info(f"--- Fim do teste standalone ---")