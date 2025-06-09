# src/agents/extratores/agente_extrator_conteudo_adk/agent.py
import os
import sys
from pathlib import Path
import json
import asyncio

# --- Bloco Padrão de Configuração e Imports ---
try:
    # CORREÇÃO: Padronizando o sys.path para consistência com outros agentes
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    # sobe 3 níveis: /extratores, /agents, /src -> chega na raiz do projeto
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
    # CORREÇÃO: Importando 'types' da biblioteca correta
    from google.genai import types
    
    # Lembre-se de importar as DUAS novas ferramentas
    from .tools.tool_fetch_articles_pending_extraction import tool_fetch_articles_pending_extraction
    from .tools.tool_extract_and_save_content import tool_extract_and_save_content
    from . import prompt as agente_prompt
except ImportError as e:
    import logging
    logging.basicConfig(level=logging.INFO)
    _logger = logging.getLogger(__name__)
    _logger.critical(f"Erro CRÍTICO ao importar módulos para AgenteExtratorDeConteudo: {e}", exc_info=True)
    sys.exit(1)


# --- Bloco de autenticação ---
if settings.GEMINI_API_KEY:
    os.environ["GOOGLE_API_KEY"] = settings.GEMINI_API_KEY
else:
    raise ValueError("GEMINI_API_KEY não encontrada em config/settings.py.")

# --- Definições do Agente ---
agente_config = settings.AGENT_CONFIGS.get("extrator", {})
MODELO_LLM_AGENTE = agente_config.get("model_name", "gemini-1.5-flash-001")

fetch_tool = FunctionTool(func=tool_fetch_articles_pending_extraction)
extract_tool = FunctionTool(func=tool_extract_and_save_content)

AgenteExtratorDeConteudo_ADK = Agent(
    name="agente_extrator_conteudo_v1",
    model=MODELO_LLM_AGENTE,
    description="Agente que orquestra a extração do texto completo de artigos de notícias.",
    instruction=agente_prompt.PROMPT,
    tools=[fetch_tool, extract_tool],
)
settings.logger.info(f"Agente '{AgenteExtratorDeConteudo_ADK.name}' carregado.")

# --- Bloco de Teste ---
if __name__ == '__main__':
    settings.logger.info(f"--- Executando teste standalone para: {AgenteExtratorDeConteudo_ADK.name} ---")

    async def run_standalone_test():
        app_name = "test_app_extrator"
        user_id = "test_user_extrator"
        session_id = "test_session_extrator"
        
        session_service = InMemorySessionService()
        runner = Runner(agent=AgenteExtratorDeConteudo_ADK, app_name=app_name, session_service=session_service)
        await session_service.create_session(app_name=app_name, user_id=user_id, session_id=session_id)
        
        prompt_text = "Execute o processo de extração de conteúdo para artigos pendentes."
        settings.logger.info(f"Enviando prompt de teste: '{prompt_text}'")
        message = types.Content(role='user', parts=[types.Part(text=prompt_text)])
        
        final_agent_response = "Nenhuma resposta final do agente foi capturada."
        
        async for event in runner.run_async(new_message=message, user_id=user_id, session_id=session_id):
            # CORREÇÃO: Checa se o conteúdo do evento não é nulo antes de acessá-lo
            if event.is_final_response() and event.content and event.content.parts:
                final_agent_response = event.content.parts[0].text

        print("\n--- Resumo do Teste ---")
        print(f"✅ SUCESSO: O pipeline de teste foi executado.")
        print(f"📄 Resposta Final do Agente: {final_agent_response}")

    try:
        asyncio.run(run_standalone_test())
    except Exception as e:
        settings.logger.critical(f"❌ FALHA: Ocorreu um erro inesperado: {e}", exc_info=True)

    settings.logger.info(f"--- Fim do teste standalone ---")