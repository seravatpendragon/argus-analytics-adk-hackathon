# src/agents/agente_orquestrador_coleta_adk/agent.py
import os
import sys
from pathlib import Path
import asyncio
import json

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
    from google.adk.agents import ParallelAgent
    from google.adk.tools import agent_tool
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types
    
    from src.agents.coletores.agente_coletor_newsapi_adk.agent import AgenteColetorNewsAPI_ADK
    from src.agents.coletores.agente_coletor_rss_adk.agent import AgenteColetorRSS_ADK
    from src.agents.coletores.agente_coletor_regulatorios_adk.agent import AgenteColetorRegulatorios_ADK
    
    from . import prompt as agent_prompt
except ImportError as e:
    import logging
    logging.basicConfig(level=logging.INFO)
    _logger = logging.getLogger(__name__)
    _logger.critical(f"Erro CRÍTICO ao importar módulos para AgenteOrquestradorColeta_ADK: {e}", exc_info=True)
    sys.exit(1)


# --- AUTENTICAÇÃO PARA A EQUIPE ---
# O orquestrador, como ponto de entrada, é responsável por configurar o ambiente
# para todos os sub-agentes que usam o LLM.
if settings.GEMINI_API_KEY:
    os.environ["GOOGLE_API_KEY"] = settings.GEMINI_API_KEY
else:
    raise ValueError("GEMINI_API_KEY não encontrada em settings.py! O orquestrador não pode operar.")


# --- Definição do Agente Orquestrador ---
# Os sub-agentes agora são passados diretamente para o ParallelAgent
AgenteOrquestradorColeta_ADK = ParallelAgent(
    name="agente_orquestrador_coleta_v1",
    description="Agente que executa todos os coletores de dados em paralelo.",
    sub_agents=[
        AgenteColetorNewsAPI_ADK,
        AgenteColetorRSS_ADK,
        AgenteColetorRegulatorios_ADK
    ],
)
settings.logger.info(f"Agente Orquestrador Paralelo '{AgenteOrquestradorColeta_ADK.name}' carregado.")

# --- Bloco de Teste ---
if __name__ == '__main__':
    settings.logger.info(f"--- Executando teste standalone para: {AgenteOrquestradorColeta_ADK.name} ---")
    
    async def run_orchestrator_test():
        runner = Runner(agent=AgenteOrquestradorColeta_ADK, app_name="test_app_orchestrator", session_service=InMemorySessionService())
        user_id, session_id = "test_user_orch", "test_session_orch"
        await runner.session_service.create_session(app_name="test_app_orchestrator", user_id=user_id, session_id=session_id)
        
        message = types.Content(role='user', parts=[types.Part(text="Inicie a coleta de todos os dados.")])
        
        print("\n--- INICIANDO ORQUESTRADOR DE COLETA PARALELA ---")
        async for event in runner.run_async(new_message=message, user_id=user_id, session_id=session_id):
            if event.is_final_response():
                print("\n--- RESPOSTA FINAL DO ORQUESTRADOR ---")
                print(event.content.parts[0].text)

        print("\n--- Resumo do Teste ---")
        print(f"✅ SUCESSO: O pipeline de orquestração foi executado sem erros de programação.")

    try:
        asyncio.run(run_orchestrator_test())
    except Exception as e:
        settings.logger.critical(f"❌ FALHA: Ocorreu um erro inesperado: {e}", exc_info=True)

    settings.logger.info(f"--- Fim do Teste de Orquestração ---")