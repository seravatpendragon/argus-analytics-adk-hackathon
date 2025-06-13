# src/agents/agente_coletor_rss_adk/agent.py

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
    # Importando as classes corretas do ADK
    from google.adk.agents import BaseAgent
    from google.adk.events import Event
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai.types import Content, Part
    
    # Importando a função da ferramenta diretamente
    from .tools.tool_collect_rss_articles import tool_collect_rss_articles
except ImportError as e:
    import logging
    logging.basicConfig(level=logging.INFO)
    _logger = logging.getLogger(__name__)
    _logger.critical(f"Erro CRÍTICO ao importar módulos para AgenteColetorRSS_ADK: {e}")
    sys.exit(1)


# --- Definição do Agente com BaseAgent ---
class AgenteColetorRSS(BaseAgent):
    """
    Um agente procedural que encapsula a lógica de coleta de notícias de feeds RSS.
    """
    def __init__(self, name: str = "agente_coletor_rss", description: str = "Agente especialista para coletar notícias e artigos de feeds RSS pré-configurados."):
        super().__init__(name=name, description=description)

    async def _run_async_impl(self, context):
        """
        Executa a lógica procedural de coleta de RSS.
        """
        settings.logger.info(f"Agente {self.name} iniciado.")
        yield Event(
            author=self.name,
            content=Content(parts=[Part(text="Iniciando coleta de feeds RSS...")])
        )

        try:
            # Chama a função Python diretamente
            result = tool_collect_rss_articles()
            
            # Trata a resposta, que deve ser um dicionário
            if isinstance(result, dict):
                message = result.get('message', "Processo de coleta RSS concluído sem mensagem específica.")
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
AgenteColetorRSS_ADK = AgenteColetorRSS()

# --- Bloco de Teste ---
if __name__ == '__main__':
    settings.logger.info(f"--- Executando teste standalone para: {AgenteColetorRSS_ADK.name} ---")

    async def run_test():
        runner = Runner(agent=AgenteColetorRSS_ADK, app_name="test_app_rss", session_service=InMemorySessionService())
        user_id, session_id = "test_user_rss", "test_session_rss"
        
        await runner.session_service.create_session(
            app_name=runner.app_name, user_id=user_id, session_id=session_id
        )
        
        message = Content(role='user', parts=[Part(text="Execute a coleta de RSS.")])
        
        print(f"\n--- ACIONANDO O AGENTE: '{AgenteColetorRSS_ADK.name}' ---")
        async for event in runner.run_async(new_message=message, user_id=user_id, session_id=session_id):
            if event.author == AgenteColetorRSS_ADK.name and event.content:
                print(f"[{event.author}]: {event.content.parts[0].text}")

    try:
        asyncio.run(run_test())
    except Exception as e:
        settings.logger.critical(f"FALHA NO TESTE: {e}", exc_info=True)

    settings.logger.info(f"--- Fim do teste standalone ---")