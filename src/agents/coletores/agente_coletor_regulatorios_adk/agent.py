# src/agents/agente_coletor_regulatorios_adk/agent.py
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
    from .tools.ferramenta_downloader_cvm import tool_download_cvm_data
    from .tools.ferramenta_processador_ipe import tool_process_cvm_ipe_local
    from . import prompt as agent_prompt
except ImportError as e:
    import logging
    logging.basicConfig(level=logging.INFO)
    _logger = logging.getLogger(__name__)
    _logger.critical(f"Erro CRÍTICO ao importar módulos para AgenteColetorRegulatorios_ADK: {e}")
    sys.exit(1)

# --- Autenticação ---
if settings.GEMINI_API_KEY:
    os.environ["GOOGLE_API_KEY"] = settings.GEMINI_API_KEY
else:
    raise ValueError("GEMINI_API_KEY não encontrada!")

# --- Definições do Agente ---
agente_config = settings.AGENT_CONFIGS.get("coletor", {})
MODELO_LLM_AGENTE = agente_config.get("model_name", "gemini-1.5-flash-001")
downloader_tool = FunctionTool(func=tool_download_cvm_data)
processor_tool = FunctionTool(func=tool_process_cvm_ipe_local)

AgenteColetorRegulatorios_ADK = Agent(
    name="agente_coletor_regulatorios_cvm_v1",
    model=MODELO_LLM_AGENTE,
    description="Agente que coleta e processa documentos regulatórios IPE da CVM.",
    instruction=agent_prompt.PROMPT,
    tools=[downloader_tool, processor_tool],
)
settings.logger.info(f"Agente '{AgenteColetorRegulatorios_ADK.name}' carregado.")

# --- Bloco de Teste Standalone ---
if __name__ == '__main__':
    settings.logger.info(f"--- Executando teste standalone para: {AgenteColetorRegulatorios_ADK.name} ---")

    async def run_standalone_test():
        runner = Runner(agent=AgenteColetorRegulatorios_ADK, app_name="test_app_cvm", session_service=InMemorySessionService())
        user_id, session_id = "test_user_cvm", "test_session_cvm"
        await runner.session_service.create_session(app_name="test_app_cvm", user_id=user_id, session_id=session_id)
        
        prompt_text = "Inicie a coleta de regulatórios da CVM para a Petrobras."
        settings.logger.info(f"Enviando prompt de teste: '{prompt_text}'")
        message = types.Content(role='user', parts=[types.Part(text=prompt_text)])
        
        async for event in runner.run_async(new_message=message, user_id=user_id, session_id=session_id):
            if event.is_final_response():
                print(f"\n--- Resposta Final do Agente ---\n{event.content.parts[0].text}")

        print("\n--- Resumo do Teste ---")
        print(f"✅ SUCESSO: O pipeline de teste do agente de regulatórios foi executado sem erros de programação.")

    try:
        asyncio.run(run_standalone_test())
    except Exception as e:
        settings.logger.critical(f"❌ FALHA: Ocorreu um erro inesperado: {e}", exc_info=True)

    settings.logger.info(f"--- Fim do teste standalone ---")