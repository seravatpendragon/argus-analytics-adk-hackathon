import os
import sys
from pathlib import Path
import asyncio
from config import settings
from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from .tools.tool_collect_bcb_indicators import collect_and_store_bcb_indicators
from . import prompt as agente_prompt

# Bloco de configuração de caminho
try:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())

# Bloco de autenticação
if settings.GEMINI_API_KEY:
    os.environ["GOOGLE_API_KEY"] = settings.GEMINI_API_KEY
else:
    raise ValueError("GEMINI_API_KEY não encontrada em config/settings.py.")

# Definições do Agente
agente_config = settings.AGENT_CONFIGS.get("coletor", {})
MODELO_LLM_AGENTE = agente_config.get("model_name", "gemini-1.5-flash-001")

collect_bcb_tool = FunctionTool(func=collect_and_store_bcb_indicators)

AgenteColetorBCB_ADK = Agent(
    name="agente_coletor_bcb_adk_v1",
    model=MODELO_LLM_AGENTE,
    description="Agente responsável por coletar séries temporais do Banco Central do Brasil.",
    instruction=agente_prompt.PROMPT,
    tools=[collect_bcb_tool],
)

settings.logger.info(f"Agente '{AgenteColetorBCB_ADK.name}' carregado com o modelo '{MODELO_LLM_AGENTE}'.")

# Bloco de teste standalone
if __name__ == '__main__':
    settings.logger.info(f"--- Executando teste standalone para: {AgenteColetorBCB_ADK.name} ---")
    
    async def run_standalone_test():
        # --- Início da Correção ---
        app_name = "test_app_bcb"
        user_id = "test_user_bcb"
        session_id = "test_session_bcb"
        
        session_service = InMemorySessionService()
        runner = Runner(agent=AgenteColetorBCB_ADK, app_name=app_name, session_service=session_service)
        
        # Cria a sessão antes de usá-la
        await session_service.create_session(app_name=app_name, user_id=user_id, session_id=session_id)
        
        prompt_text = "Por favor, inicie a coleta de dados do BCB."
        message = types.Content(role='user', parts=[types.Part(text=prompt_text)])
        
        final_agent_response = ""
        # Passa os argumentos necessários para o run_async
        async for event in runner.run_async(new_message=message, user_id=user_id, session_id=session_id):
            if event.is_final_response():
                final_agent_response = event.content.parts[0].text
        # --- Fim da Correção ---
        
        print("\n--- Resumo do Teste ---")
        print(f"📄 Resposta Final do Agente: {final_agent_response}")

    try:
        asyncio.run(run_standalone_test())
    except Exception as e:
        settings.logger.critical(f"❌ FALHA: Ocorreu um erro inesperado durante a execução do teste: {e}", exc_info=True)
