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
from .tools.tool_collect_fred_indicators import collect_and_store_fred_indicators
from . import prompt as agente_prompt

try:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())



agente_config = settings.AGENT_CONFIGS.get("coletor", {})
MODELO_LLM_AGENTE = agente_config.get("model_name", "gemini-1.5-flash-001")

collect_fred_tool = FunctionTool(func=collect_and_store_fred_indicators)

AgenteColetorFRED_ADK = Agent(
    name="agente_coletor_fred_adk_v1",
    model=MODELO_LLM_AGENTE,
    description="Agente responsável por coletar séries de dados do FRED.",
    instruction=agente_prompt.PROMPT,
    tools=[collect_fred_tool],
)

settings.logger.info(f"Agente '{AgenteColetorFRED_ADK.name}' carregado com o modelo '{MODELO_LLM_AGENTE}'.")

if __name__ == '__main__':
    settings.logger.info(f"--- Executando teste standalone para: {AgenteColetorFRED_ADK.name} ---")
    async def run_standalone_test():
        runner = Runner(agent=AgenteColetorFRED_ADK, app_name="test_app_fred", session_service=InMemorySessionService())
        await runner.session_service.create_session(app_name=runner.app_name, user_id="test_user", session_id="test_session")
        prompt_text = "Por favor, inicie a coleta de dados do FRED."
        message = types.Content(role='user', parts=[types.Part(text=prompt_text)])
        
        final_agent_response = ""
        async for event in runner.run_async(new_message=message, user_id="test_user", session_id="test_session"):
            if event.is_final_response():
                final_agent_response = event.content.parts[0].text
        
        print(f"\n--- Resumo do Teste ---\n📄 Resposta Final do Agente: {final_agent_response}")

    try:
        asyncio.run(run_standalone_test())
    except Exception as e:
        settings.logger.critical(f"❌ FALHA: Ocorreu um erro inesperado durante a execução do teste: {e}", exc_info=True)