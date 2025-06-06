# src/agents/agente_consolidador_analise_adk/agent.py

import asyncio
import os
import sys
from pathlib import Path
import json
from datetime import datetime
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
    # from google.adk.tools import FunctionTool # Não precisamos mais importar FunctionTool aqui
    
    # Importa a ferramenta de atualização de análise (para referenciar, não para usar como ferramenta do agente)
    from .tools.tool_update_article_analysis import tool_update_article_analysis 

    # Importa o prompt local
    from . import prompt as agente_prompt

    # Fallback do logger se settings.logger não estiver disponível
    if not hasattr(settings, 'logger'):
        import logging
        log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        settings.logger = logging.getLogger("agente_consolidador_analise_adk_fb_logger")
        settings.logger.info("Logger fallback inicializado em agent.py.")
    settings.logger.info("Módulos do projeto e ADK importados com sucesso para AgenteConsolidadorDeAnalise_ADK.")
except ImportError as e:
    settings.logger.error(f"Erro CRÍTICO em agent.py (AgenteConsolidadorDeAnalise_ADK) ao importar módulos: {e}")
    settings.logger.error(f"PROJECT_ROOT calculado: {PROJECT_ROOT}")
    settings.logger.error(f"sys.path atual: {sys.path}")
    sys.exit(1)
except Exception as e:
    settings.logger.error(f"Erro INESPERADO durante imports iniciais em agent.py (AgenteConsolidadorDeAnalise_ADK): {e}")
    sys.exit(1)

# --- Definição do Modelo LLM a ser usado por este agente ---
MODELO_LLM_AGENTE = "gemini-2.0-flash-001" 
settings.logger.info(f"Modelo LLM para AgenteConsolidadorDeAnalise_ADK: {MODELO_LLM_AGENTE}")

# --- Definição do Agente ---
AgenteConsolidadorDeAnalise_ADK = Agent(
    name="agente_consolidador_analise_adk_v1",
    model=MODELO_LLM_AGENTE, 
    description=(
        "Agente responsável por consolidar os resultados da análise LLM de um artigo e gerar os parâmetros "
        "para persistir esses insights no banco de dados."
    ),
    instruction=agente_prompt.PROMPT,
    tools=[], # <-- REMOVIDO: Este agente não chama ferramentas diretamente, apenas gera os parâmetros.
)

if __name__ == '__main__':
    settings.logger.info(f"--- Teste Standalone da Definição e Fluxo Simulado do Agente: {AgenteConsolidadorDeAnalise_ADK.name} ---")
    settings.logger.info(f"  Modelo Configurado: {AgenteConsolidadorDeAnalise_ADK.model}") 

    # --- SIMULANDO EXECUÇÃO DO AGENTE (APENAS GERAÇÃO DE JSON) ---
    from google.adk.sessions import InMemorySessionService
    from google.adk.runners import Runner
    from google.genai import types

    async def run_mock_consolidation():
        session_service = InMemorySessionService()
        session = await session_service.create_session(app_name="mock_app", user_id="mock_user", session_id="mock_session")
        
        mock_runner = Runner(
            agent=AgenteConsolidadorDeAnalise_ADK,
            app_name="mock_app",
            session_service=session_service
        )

        mock_llm_analysis_data = {
            "news_article_id": 999,
            "llm_analysis_json": {
                "sentiment_analysis": {"sentiment_petr4": "positivo", "score": 0.8, "justification": "Mock sentiment."},
                "relevance_type_analysis": {"relevance_petr4": "Alta", "suggested_article_type": "Fato Relevante", "justification": "Mock relevance."},
                "stakeholders_analysis": {"stakeholders": ["Investidores"], "impacto_no_stakeholder_primario": "Positivo", "justificativa_impacto_stakeholder": "Mock stakeholders."},
                "maslow_analysis": {"maslow_impact_primary": "Segurança", "justification_impact_maslow": "Mock maslow."}
            },
            "suggested_article_type": "Fato Relevante"
        }
        
        mock_input_content = types.Content(role='user', parts=[types.Part(text=json.dumps(mock_llm_analysis_data))])

        settings.logger.info("\nSimulando chamada ao AgenteConsolidadorDeAnalise_ADK para gerar JSON de parâmetros...")
        events = mock_runner.run_async(user_id="mock_user", session_id="mock_session", new_message=mock_input_content)
        
        async for event in events:
            if event.is_final_response() and event.content and event.content.parts and event.content.parts[0].text:
                generated_json_str = event.content.parts[0].text.strip()
                settings.logger.info(f"JSON de parâmetros gerado pelo Consolidador:\n{generated_json_str}")
                try:
                    parsed_params = json.loads(generated_json_str)
                    settings.logger.info(f"JSON de parâmetros PARSEADO com sucesso: {parsed_params}")
                    # Aqui você chamaria tool_update_article_analysis(news_article_id=parsed_params['news_article_id'], ...)
                except json.JSONDecodeError as e:
                    settings.logger.error(f"Erro ao parsear JSON gerado pelo Consolidador: {e}")
            elif hasattr(event, 'tool_code') and event.tool_code: # Se o LLM ainda tentar gerar tool_code
                 settings.logger.warning(f"Consolidador gerou tool_code inesperado: {event.tool_code}")

    asyncio.run(run_mock_consolidation())
    settings.logger.info("\n--- Fim do Teste Standalone do Agente Consolidador de Análise ---")