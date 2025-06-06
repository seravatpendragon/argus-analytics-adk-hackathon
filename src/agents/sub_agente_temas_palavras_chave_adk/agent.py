# src/agents/sub_agente_temas_palavras_chave_adk/agent.py

import os
import sys
from pathlib import Path
import json
import logging

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent # Sobe 3 níveis
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

try:
    from config import settings
    from google.adk.agents import Agent
    # from google.adk.tools import FunctionTool # Remova se não houver ferramentas neste agente
    
    # Importa o prompt local
    from . import prompt as agente_prompt

    # Fallback do logger se settings.logger não estiver disponível
    if not hasattr(settings, 'logger'):
        import logging
        log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        settings.logger = logging.getLogger("sub_agente_temas_palavras_chave_adk_fb_logger")
        settings.logger.info("Logger fallback inicializado em agent.py.")
    settings.logger.info("Módulos do projeto e ADK importados com sucesso para SubAgenteTemasPalavrasChave_ADK.")
except ImportError as e:
    settings.logger.error(f"Erro CRÍTICO em agent.py (SubAgenteTemasPalavrasChave_ADK) ao importar módulos: {e}")
    settings.logger.error(f"PROJECT_ROOT calculado: {PROJECT_ROOT}")
    settings.logger.error(f"sys.path atual: {sys.path}")
    sys.exit(1)
except Exception as e:
    settings.logger.error(f"Erro INESPERADO durante imports iniciais em agent.py (SubAgenteTemasPalavrasChave_ADK): {e}")
    sys.exit(1)

# --- Definição do Modelo LLM a ser usado por este agente ---
MODELO_LLM_AGENTE = "gemini-2.0-flash-001" 
settings.logger.info(f"Modelo LLM para SubAgenteTemasPalavrasChave_ADK: {MODELO_LLM_AGENTE}")

# --- Definição do Agente ---
SubAgenteTemasPalavrasChave_ADK = Agent(
    name="sub_agente_temas_palavras_chave_adk_v1",
    model=MODELO_LLM_AGENTE, 
    description=(
        "Sub-agente especializado em extrair os principais temas e palavras-chave significativas de notícias financeiras, "
        "em relação à entidade principal identificada."
    ),
    instruction=agente_prompt.PROMPT,
    tools=[], # Este agente não precisa de ferramentas se apenas gera texto/JSON
)

if __name__ == '__main__':
    settings.logger.info(f"--- Teste Standalone da Definição e Fluxo Simulado do Agente: {SubAgenteTemasPalavrasChave_ADK.name} ---")
    settings.logger.info(f"  Modelo Configurado: {SubAgenteTemasPalavrasChave_ADK.model}") 

    from google.adk.sessions import InMemorySessionService
    from google.adk.runners import Runner
    from google.genai import types
    import asyncio

    async def run_mock_keyword_extraction():
        session_service = InMemorySessionService()
        session = await session_service.create_session(app_name="mock_keywords_app", user_id="mock_user", session_id="mock_kw_session")
        
        mock_runner = Runner(
            agent=SubAgenteTemasPalavrasChave_ADK,
            app_name="mock_keywords_app",
            session_service=session_service
        )

        # Exemplo de input (o mesmo formato que virá do run_llm_analysis_pipeline_test.py)
        # Lembre-se que o prompt foi ajustado para esperar "Contexto da Notícia" no texto
        text_content_with_context = """
        Contexto da Notícia: A notícia é predominantemente sobre: EMPRESA. A entidade/tema principal é 'Petrobras'. O identificador padronizado é 'PETR4-SA'.

        Texto Original para Análise:
        O conselho de administração da Petrobras aprovou a venda de sua participação na Refinaria Landulpho Alves (RLAM) para o fundo Mubadala, como parte do plano de desinvestimentos da companhia e foco no pré-sal.
        """
        
        llm_input_content = types.Content(role='user', parts=[types.Part(text=text_content_with_context)])
        
        settings.logger.info("\nSimulando chamada ao SubAgenteTemasPalavrasChave_ADK para extrair temas/palavras-chave...")
        events = mock_runner.run_async(user_id="mock_user", session_id="mock_kw_session", new_message=llm_input_content)
        
        async for event in events:
            if event.is_final_response() and event.content and event.content.parts and event.content.parts[0].text:
                generated_json_str = event.content.parts[0].text.strip()
                settings.logger.info(f"  JSON de temas/palavras-chave gerado:\n{generated_json_str}")
                try:
                    parsed_keywords = json.loads(generated_json_str)
                    settings.logger.info(f"  Temas/Palavras-chave PARSEADAS com sucesso: {parsed_keywords}")
                except json.JSONDecodeError as e:
                    settings.logger.error(f"  Erro ao parsear JSON de temas/palavras-chave: {e}. Conteúdo: {generated_json_str[:100]}...")
            elif hasattr(event, 'tool_code') and event.tool_code:
                settings.logger.warning(f"  Agente Temas/Palavras-chave gerou tool_code inesperado: {event.tool_code[:100]}...")

    asyncio.run(run_mock_keyword_extraction())
    settings.logger.info("\n--- Fim do Teste Standalone do SubAgenteTemasPalavrasChave_ADK ---")