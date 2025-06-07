# src/agents/agente_coletor_newsapi_adk/agent.py

import os
import sys
from pathlib import Path
import json
import asyncio

# --- Configuração de Caminhos e Imports ---
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
    from .tools.tool_collect_newsapi_articles import tool_collect_newsapi_articles
    from . import prompt as agente_prompt
except ImportError as e:
    import logging
    logging.basicConfig(level=logging.INFO)
    _logger = logging.getLogger(__name__)
    _logger.critical(f"Erro CRÍTICO ao importar módulos para AgenteColetorNewsAPI_ADK: {e}")
    sys.exit(1)

# --- Autenticação ---
# CORREÇÃO DEFINITIVA: Configura a API Key como uma variável de ambiente.
# A biblioteca do Google irá encontrá-la automaticamente.
if settings.GEMINI_API_KEY:
    os.environ["GOOGLE_API_KEY"] = settings.GEMINI_API_KEY
else:
    raise ValueError("GEMINI_API_KEY não encontrada em settings.py. O agente não pode se autenticar.")


# --- Definições do Agente ---
MODELO_LLM_AGENTE = "gemini-1.5-flash-001"
collect_newsapi_tool_adk_instance = FunctionTool(func=tool_collect_newsapi_articles)

# CORREÇÃO: O construtor do Agent volta a ser limpo, sem o parâmetro api_key.
AgenteColetorNewsAPI_ADK = Agent(
    name="agente_coletor_newsapi_adk_v1",
    model=MODELO_LLM_AGENTE,
    description="Agente responsável por coletar artigos de notícias da NewsAPI com base nas configurações em newsapi_news_config.json.",
    instruction=agente_prompt.PROMPT,
    tools=[
        collect_newsapi_tool_adk_instance,
    ],
)

settings.logger.info(f"Agente '{AgenteColetorNewsAPI_ADK.name}' carregado com o modelo '{MODELO_LLM_AGENTE}'.")

# --- Bloco de Teste Standalone (Correto) ---
if __name__ == '__main__':
    settings.logger.info(f"--- Executando teste standalone para: {AgenteColetorNewsAPI_ADK.name} ---")

    async def run_standalone_test():
        app_name = "test_app_newsapi"
        user_id = "test_user"
        session_id = "test_session_newsapi"
        
        session_service = InMemorySessionService()
        runner = Runner(agent=AgenteColetorNewsAPI_ADK, app_name=app_name, session_service=session_service)
        await session_service.create_session(app_name=app_name, user_id=user_id, session_id=session_id)
        
        prompt_text = "Inicie a coleta de notícias da NewsAPI."
        settings.logger.info(f"Enviando prompt de teste: '{prompt_text}'")
        message = types.Content(role='user', parts=[types.Part(text=prompt_text)])
        
        final_agent_response = ""
        async for event in runner.run_async(new_message=message, user_id=user_id, session_id=session_id):
            if event.is_final_response():
                final_agent_response = event.content.parts[0].text

        print("\n--- Resumo do Teste ---")
        print(f"✅ SUCESSO: O pipeline de teste foi executado sem erros de programação.")
        print(f"📄 Resposta Final do Agente: {final_agent_response}")


    try:
        asyncio.run(run_standalone_test())
    except Exception as e:
        settings.logger.critical(f"❌ FALHA: Ocorreu um erro inesperado durante a execução do teste: {e}", exc_info=True)

    settings.logger.info(f"--- Fim do teste standalone ---")