# src/agents/sub_agente_identificador_entidade_adk/agent.py

import os
import sys
from pathlib import Path
import json

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent # Sobe 3 níveis
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    # print(f"PROJECT_ROOT ({PROJECT_ROOT}) foi adicionado/confirmado no sys.path para agent.py (SubAgenteIdentificadorEntidade).")
except NameError:
    PROJECT_ROOT = Path(os.getcwd())
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    # print(f"AVISO (agent.py SubAgenteIdentificadorEntidade): __file__ não definido. Usando PROJECT_ROOT como: {PROJECT_ROOT}")

try:
    from config import settings
    from google.adk.agents import Agent
    from google.adk.tools import FunctionTool # Se precisar de ferramentas internas (como padronizar ticker)
    
    # Importa o prompt local
    from . import prompt as agente_prompt

    # Fallback do logger se settings.logger não estiver disponível
    if not hasattr(settings, 'logger'):
        import logging
        log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        settings.logger = logging.getLogger("sub_agente_identificador_entidade_adk_fb_logger")
        settings.logger.info("Logger fallback inicializado em agent.py.")
    print("Módulos do projeto e ADK importados com sucesso para SubAgenteIdentificadorDeEntidade_ADK.")
except ImportError as e:
    settings.logger.error(f"Erro CRÍTICO em agent.py (SubAgenteIdentificadorDeEntidade_ADK) ao importar módulos: {e}")
    settings.logger.error(f"PROJECT_ROOT calculado: {PROJECT_ROOT}")
    settings.logger.error(f"sys.path atual: {sys.path}")
    sys.exit(1)
except Exception as e:
    settings.logger.error(f"Erro INESPERADO durante imports iniciais em agent.py (SubAgenteIdentificadorDeEntidade_ADK): {e}")
    sys.exit(1)

# --- Definição do Modelo LLM a ser usado por este agente ---
MODELO_LLM_AGENTE = "gemini-2.0-flash-001" 
settings.logger.info(f"Modelo LLM para SubAgenteIdentificadorDeEntidade_ADK: {MODELO_LLM_AGENTE}")

# --- Definição do Agente ---
SubAgenteIdentificadorDeEntidade_ADK = Agent(
    name="sub_agente_identificador_entidade_adk_v1",
    model=MODELO_LLM_AGENTE, 
    description=(
        "Sub-agente especializado em identificar a entidade principal (empresa, segmento B3, macroeconômico) "
        "ou o foco temático de uma notícia e padronizar seu identificador."
    ),
    instruction=agente_prompt.PROMPT,
    tools=[], # Por enquanto, sem ferramentas diretas; a padronização será externa no `run_test_pipeline`.
              # Ou poderíamos ter uma ferramenta `tool_padronizar_ticker_segmento` aqui.
)

if __name__ == '__main__':
    settings.logger.info(f"--- Teste Standalone da Definição e Fluxo Simulado do Agente: {SubAgenteIdentificadorDeEntidade_ADK.name} ---")
    settings.logger.info(f"  Modelo Configurado: {SubAgenteIdentificadorDeEntidade_ADK.model}") 

    from google.adk.sessions import InMemorySessionService
    from google.adk.runners import Runner
    from google.genai import types
    import asyncio

    async def run_mock_entity_identification():
        session_service = InMemorySessionService()
        session = await session_service.create_session(app_name="mock_app", user_id="mock_user", session_id="mock_session")
        
        mock_runner = Runner(
            agent=SubAgenteIdentificadorDeEntidade_ADK,
            app_name="mock_app",
            session_service=session_service
        )

        test_news_texts = [
            "Petrobras anuncia lucro recorde no segundo trimestre, superando expectativas de analistas e impulsionando ações PETR4.",
            "Inflação no Brasil atinge 0.5% em julho, acima do esperado, pressionada por preços de alimentos e energia. O IPCA preocupa.",
            "Setor de mineração no Brasil enfrenta desafios com a queda do preço do minério de ferro global e aumento da pressão regulatória ambiental."
        ]

        for i, text in enumerate(test_news_texts):
            settings.logger.info(f"\nSimulando identificação para Notícia {i+1}: '{text[:70]}...'")
            llm_input_content = types.Content(role='user', parts=[types.Part(text=text)])
            
            events = mock_runner.run_async(user_id="mock_user", session_id="mock_session", new_message=llm_input_content)
            
            async for event in events:
                if event.is_final_response() and event.content and event.content.parts and event.content.parts[0].text:
                    generated_json_str = event.content.parts[0].text.strip()
                    settings.logger.info(f"  JSON de identificação gerado:\n{generated_json_str}")
                    try:
                        parsed_identification = json.loads(generated_json_str)
                        settings.logger.info(f"  Identificação PARSEADA com sucesso: {parsed_identification}")
                    except json.JSONDecodeError as e:
                        settings.logger.error(f"  Erro ao parsear JSON de identificação: {e}. Conteúdo: {generated_json_str[:100]}...")
                elif hasattr(event, 'tool_code') and event.tool_code:
                    settings.logger.warning(f"  Agente Identificador gerou tool_code inesperado: {event.tool_code[:100]}...")

    asyncio.run(run_mock_entity_identification())
    settings.logger.info("\n--- Fim do Teste Standalone do SubAgenteIdentificadorDeEntidade_ADK ---")