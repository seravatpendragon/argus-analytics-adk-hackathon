import os
import sys
from pathlib import Path
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
    # Importa o LlmAgent em vez do ParallelAgent
    from google.adk.agents import LlmAgent
    from google.adk.tools import agent_tool
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai.types import Content, Part
    
    # Os agentes coletores continuam sendo importados
    from src.agents.coletores.agente_coletor_newsapi_adk.agent import AgenteColetorNewsAPI_ADK
    from src.agents.coletores.agente_coletor_rss_adk.agent import AgenteColetorRSS_ADK
    from src.agents.coletores.agente_coletor_regulatorios_adk.agent import AgenteColetorRegulatorios_ADK
    from src.agents.coletores.agente_coletor_yfinance_adk.agent import AgenteColetorYfinance_ADK
    from src.agents.coletores.agente_coletor_fundamentus_adk.agent import AgenteColetorFundamentus_ADK
    from src.agents.coletores.agente_coletor_bcb_adk.agent import AgenteColetorBCB_ADK
    from src.agents.coletores.agente_coletor_ibge_adk.agent import AgenteColetorIBGE_ADK
    from src.agents.coletores.agente_coletor_fgv_adk.agent import AgenteColetorFGV_ADK
    from src.agents.coletores.agente_coletor_fred_adk.agent import AgenteColetorFRED_ADK
    from src.agents.coletores.agente_coletor_eia_adk.agent import AgenteColetorEIA_ADK
    
    # Importa o novo prompt
    from . import prompt as agent_prompt
except ImportError as e:
    import logging
    logging.basicConfig(level=logging.INFO)
    _logger = logging.getLogger(__name__)
    _logger.critical(f"Erro CRÍTICO ao importar módulos para AgenteOrquestradorColeta_ADK: {e}", exc_info=True)
    sys.exit(1)


# --- PASSO 1: Transformar Sub-Agentes em Ferramentas ---
# Envolvemos cada agente coletor em um 'AgentTool' para que o orquestrador LLM possa usá-los.
# Pense nisso como dar um "cartão de visita" de cada especialista para o gerente.
lista_de_ferramentas = [
    agent_tool.AgentTool(agent=AgenteColetorNewsAPI_ADK),
    agent_tool.AgentTool(agent=AgenteColetorRSS_ADK),
    agent_tool.AgentTool(agent=AgenteColetorRegulatorios_ADK),
    agent_tool.AgentTool(agent=AgenteColetorYfinance_ADK),
    agent_tool.AgentTool(agent=AgenteColetorFundamentus_ADK),
    agent_tool.AgentTool(agent=AgenteColetorBCB_ADK),
    agent_tool.AgentTool(agent=AgenteColetorIBGE_ADK),
    agent_tool.AgentTool(agent=AgenteColetorFGV_ADK),
    agent_tool.AgentTool(agent=AgenteColetorFRED_ADK),
    agent_tool.AgentTool(agent=AgenteColetorEIA_ADK),
]

# --- PASSO 2: Definir o Agente Orquestrador Inteligente ---
# Agora, usamos um LlmAgent, que tem um "cérebro" (o modelo do Vertex AI).
agente_config = settings.AGENT_CONFIGS.get("orquestrador", {})
MODELO_LLM_ORQUESTRADOR = agente_config.get("model_name")

AgenteOrquestradorColeta_ADK = LlmAgent(
    name="agente_orquestrador_coleta_v2_vertex",
    model=MODELO_LLM_ORQUESTRADOR,
    instruction=agent_prompt.PROMPT,
    description="Agente inteligente que analisa um pedido e aciona os agentes coletores corretos em paralelo.",
    # Passamos a lista de "cartões de visita" (ferramentas) para o gerente.
    tools=lista_de_ferramentas,
)
settings.logger.info(f"Agente Orquestrador Inteligente '{AgenteOrquestradorColeta_ADK.name}' carregado com {len(lista_de_ferramentas)} ferramentas.")

# --- Bloco de Teste Atualizado ---
if __name__ == '__main__':
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        if hasattr(settings, 'PROJECT_ID') and settings.PROJECT_ID:
            os.environ["GOOGLE_CLOUD_PROJECT"] = settings.PROJECT_ID
        else:
            print("ERRO: GOOGLE_CLOUD_PROJECT não definida.")
            sys.exit(1)
            
    if not os.getenv("GOOGLE_CLOUD_LOCATION"):
        if hasattr(settings, 'LOCATION') and settings.LOCATION:
            os.environ["GOOGLE_CLOUD_LOCATION"] = settings.LOCATION
        else:
            print("AVISO: GOOGLE_CLOUD_LOCATION não definida. Usando 'global' como padrão.")

    settings.logger.info(f"--- Executando teste standalone para: {AgenteOrquestradorColeta_ADK.name} ---")
    
    async def run_orchestrator_test():
        runner = Runner(agent=AgenteOrquestradorColeta_ADK, app_name="test_app_orchestrator", session_service=InMemorySessionService())
        user_id, session_id = "test_user_orch", "test_session_orch"
        await runner.session_service.create_session(app_name="test_app_orchestrator", user_id=user_id, session_id=session_id)
        
        # Agora podemos fazer um pedido em linguagem natural
        prompt_text = "Por favor, inicie a coleta de notícias de portais RSS e busque os dados da CVM."
        message = Content(role='user', parts=[Part(text=prompt_text)])
        
        print(f"\n--- ENVIANDO PROMPT PARA O ORQUESTRADOR: '{prompt_text}' ---")
        async for event in runner.run_async(new_message=message, user_id=user_id, session_id=session_id):
            if event.is_final_response():
                print("\n--- RESPOSTA FINAL DO ORQUESTRADOR ---")
                print(event.content.parts[0].text)

        print("\n--- Resumo do Teste ---")
        print(f"SUCESSO: O pipeline de orquestração inteligente foi executado sem erros de programação.")

    try:
        asyncio.run(run_orchestrator_test())
    except Exception as e:
        settings.logger.critical(f"FALHA: Ocorreu um erro inesperado: {e}", exc_info=True)

    settings.logger.info(f"--- Fim do Teste de Orquestração ---")