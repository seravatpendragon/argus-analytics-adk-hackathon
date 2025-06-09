# /src/agents/coletores/agente_coletor_fundamentus_adk/agent.py

import os
import sys
from pathlib import Path
import asyncio

# --- Configuração de Caminhos e Imports ---
# Garante que o projeto seja importável, não importa de onde o script é chamado
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

# --- Imports do Projeto e do ADK ---
try:
    from config import settings # Usa nosso logger e configurações centralizadas
    from google.adk.agents import Agent
    from google.adk.tools import FunctionTool
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types
    from .tools.tool_collect_fundamentus_indicators import collect_and_store_fundamentus_indicators
    from . import prompt as agente_prompt
except ImportError as e:
    import logging
    logging.basicConfig(level=logging.INFO)
    _logger = logging.getLogger(__name__)
    _logger.critical(f"Erro CRÍTICO ao importar módulos para AgenteColetorFundamentus_ADK: {e}")
    sys.exit(1)

if settings.GEMINI_API_KEY:
    os.environ["GOOGLE_API_KEY"] = settings.GEMINI_API_KEY
else:
    raise ValueError("GEMINI_API_KEY não encontrada em config/settings.py. O agente não pode se autenticar.")
# --- Definições do Agente (Padrão ADK) ---
agente_config = settings.AGENT_CONFIGS.get("coletor", {})
MODELO_LLM_AGENTE = agente_config.get("model_name", "gemini-1.5-flash-001")

# 1. Instancia a ferramenta no formato do ADK
collect_fundamentus_tool_adk_instance = FunctionTool(func=collect_and_store_fundamentus_indicators)

# 2. Cria o Agente ADK
AgenteColetorFundamentus_ADK = Agent(
    name="agente_coletor_fundamentus_adk_v1",
    model=MODELO_LLM_AGENTE,
    description="Agente especialista em coletar indicadores fundamentalistas de empresas brasileiras usando o pyfundamentus.",
    instruction=agente_prompt.PROMPT,
    tools=[
        collect_fundamentus_tool_adk_instance,
    ],
)

settings.logger.info(f"Agente '{AgenteColetorFundamentus_ADK.name}' carregado com o modelo '{MODELO_LLM_AGENTE}'.")

# --- Bloco de Teste Standalone ---
if __name__ == '__main__':
    settings.logger.info(f"--- Executando teste standalone para: {AgenteColetorFundamentus_ADK.name} ---")

    async def run_standalone_test():
        # Configuração do Runner e da Sessão
        app_name = "test_app_fundamentus"
        user_id = "test_user"
        session_id = "test_session_fundamentus"
        
        session_service = InMemorySessionService()
        runner = Runner(agent=AgenteColetorFundamentus_ADK, app_name=app_name, session_service=session_service)
        await session_service.create_session(app_name=app_name, user_id=user_id, session_id=session_id)
        
        # Execução do Prompt
        prompt_text = "Por favor, inicie a coleta de dados de indicadores do Fundamentus."
        settings.logger.info(f"Enviando prompt de teste: '{prompt_text}'")
        message = types.Content(role='user', parts=[types.Part(text=prompt_text)])
        
        final_agent_response = ""
        async for event in runner.run_async(new_message=message, user_id=user_id, session_id=session_id):
            if event.is_final_response():
                final_agent_response = event.content.parts[0].text

        # Apresentação do Resultado
        print("\n--- Resumo do Teste ---")
        if "Sucesso" in final_agent_response or "Nenhum dado novo" in final_agent_response or "Nenhum ticker" in final_agent_response:
             print(f"✅ SUCESSO: Pipeline de teste executado.")
        else:
             print(f"❌ FALHA: Ocorreu um problema na execução.")
        print(f"📄 Resposta Final do Agente: {final_agent_response}")

    # Pré-requisito: Garanta que há um ticker com source 'Fundamentus' no seu BD.
    # Ex: INSERT INTO "Assets" (ticker, name, source) VALUES ('MGLU3', 'Magazine Luiza', 'Fundamentus');
    asyncio.run(run_standalone_test())