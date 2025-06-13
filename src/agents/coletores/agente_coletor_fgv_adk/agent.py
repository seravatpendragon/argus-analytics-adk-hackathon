# /src/agents/coletores/agente_coletor_fgv_adk/agent.py

import os
import sys
from pathlib import Path
import asyncio

# --- Bloco Padrão de Configuração e Imports ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())

try:
    from config import settings
    # 1. Importando as classes corretas do ADK
    from google.adk.agents import BaseAgent
    from google.adk.events import Event
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai.types import Content, Part
    
    # 2. Importando a função da ferramenta diretamente
    from .tools.tool_collect_fgv_indicators import collect_and_store_fgv_indicators
except ImportError as e:
    import logging
    logging.basicConfig(level=logging.INFO)
    _logger = logging.getLogger(__name__)
    _logger.critical(f"Erro CRÍTICO ao importar módulos para AgenteColetorFGV_ADK: {e}")
    sys.exit(1)


# --- Definição do Agente com BaseAgent ---
class AgenteColetorFGV(BaseAgent):
    """
    Um agente procedural que encapsula a lógica de coleta de dados da FGV.
    """
    def __init__(self, name: str = "agente_coletor_fgv", description: str = "Agente para coletar indicadores econômicos da Fundação Getúlio Vargas (FGV)."):
        super().__init__(name=name, description=description)

    async def _run_async_impl(self, context):
        """
        Executa a lógica procedural de coleta de dados da FGV.
        """
        settings.logger.info(f"Agente {self.name} iniciado.")
        yield Event(
            author=self.name,
            content=Content(parts=[Part(text="Iniciando coleta de dados da FGV...")])
        )

        try:
            # Chama a função Python diretamente
            result = collect_and_store_fgv_indicators()
            
            if isinstance(result, dict) and 'message' in result:
                message = result.get('message')
            else:
                message = str(result)

            settings.logger.info(message)
            yield Event(
                author=self.name,
                content=Content(parts=[Part(text=message)])
            )

        except Exception as e:
            error_message = f"FALHA GERAL no {self.name}: {e}"
            settings.logger.critical(error_message, exc_info=True)
            yield Event(
                author=self.name,
                content=Content(parts=[Part(text=error_message)])
            )

# Instancia o agente para ser importado por outros módulos
AgenteColetorFGV_ADK = AgenteColetorFGV()

# --- Bloco de Teste ---
if __name__ == '__main__':
    settings.logger.info(f"--- Executando teste standalone para: {AgenteColetorFGV_ADK.name} ---")

    async def run_test():
        runner = Runner(agent=AgenteColetorFGV_ADK, app_name="test_app_fgv", session_service=InMemorySessionService())
        user_id, session_id = "test_user_fgv", "test_session_fgv"
        
        await runner.session_service.create_session(
            app_name=runner.app_name, user_id=user_id, session_id=session_id
        )
        
        message = Content(role='user', parts=[Part(text="Execute a coleta da FGV.")])
        
        print(f"\n--- ACIONANDO O AGENTE: '{AgenteColetorFGV_ADK.name}' ---")
        async for event in runner.run_async(new_message=message, user_id=user_id, session_id=session_id):
            if event.author == AgenteColetorFGV_ADK.name and event.content:
                print(f"[{event.author}]: {event.content.parts[0].text}")

    try:
        asyncio.run(run_test())
    except Exception as e:
        settings.logger.critical(f"FALHA NO TESTE: {e}", exc_info=True)

    settings.logger.info(f"--- Fim do teste standalone ---")