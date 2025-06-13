# src/agents/agente_coletor_regulatorios_adk/agent.py
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

try:
    from config import settings
    from google.adk.agents import BaseAgent
    from google.adk.events import Event
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai.types import Content, Part
    
    # Importando as funções diretamente
    from .tools.ferramenta_downloader_cvm import tool_download_cvm_data
    from .tools.ferramenta_processador_ipe import tool_process_cvm_ipe_local
except ImportError as e:
    import logging
    _logger = logging.getLogger(__name__)
    _logger.critical(f"Erro CRÍTICO ao importar módulos para AgenteColetorRegulatorios_ADK: {e}", exc_info=True)
    sys.exit(1)


# --- Definição do Agente com BaseAgent ---
class AgenteColetorRegulatorios(BaseAgent):
    """
    Um agente procedural que orquestra o download e processamento de dados da CVM.
    """
    def __init__(self, name: str = "agente_coletor_regulatorios", description: str = "Agente que baixa e processa documentos regulatórios IPE da CVM."):
        super().__init__(name=name, description=description)

    async def _run_async_impl(self, context):
        """
        Executa a lógica procedural de coleta de dados da CVM em duas etapas.
        """
        settings.logger.info(f"Agente {self.name} iniciado.")
        yield Event(
            author=self.name,
            content=Content(parts=[Part(text="Iniciando coleta de dados regulatórios da CVM...")])
        )

        try:
            # ETAPA 1: Download
            download_result = tool_download_cvm_data()
            yield Event(
                author=self.name,
                content=Content(parts=[Part(text=f"Download CVM: {download_result.get('message')}")])
            )
            
            # ETAPA 2: Processamento em Lote
            downloaded_files = download_result.get("downloaded_files", [])
            if download_result.get("status") == "success" and downloaded_files:
                yield Event(
                    author=self.name,
                    content=Content(parts=[Part(text=f"Encontrados {len(downloaded_files)} arquivos para processar. Iniciando...")])
                )
                
                for file_path in downloaded_files:
                    process_result = tool_process_cvm_ipe_local(caminho_zip_local=file_path)
                    yield Event(
                        author=self.name,
                        content=Content(parts=[Part(text=f"Processado '{Path(file_path).name}': {process_result.get('message')}")])
                    )
            
            final_message = "Coleta e processamento de dados regulatórios da CVM finalizados."
            yield Event(
                author=self.name,
                content=Content(parts=[Part(text=final_message)])
            )

        except Exception as e:
            error_message = f"FALHA GERAL no {self.name}: {e}"
            settings.logger.critical(error_message, exc_info=True)
            yield Event(
                author=self.name,
                content=Content(parts=[Part(text=error_message)])
            )

# Instancia o agente
AgenteColetorRegulatorios_ADK = AgenteColetorRegulatorios()

# --- Bloco de Teste ---
if __name__ == '__main__':
    settings.logger.info(f"--- Executando teste standalone para: {AgenteColetorRegulatorios_ADK.name} ---")

    async def run_test():
        runner = Runner(agent=AgenteColetorRegulatorios_ADK, app_name="test_app_cvm", session_service=InMemorySessionService())
        user_id, session_id = "test_user_cvm", "test_session_cvm"
        
        await runner.session_service.create_session(
            app_name=runner.app_name, user_id=user_id, session_id=session_id
        )
        
        message = Content(role='user', parts=[Part(text="Execute a coleta de dados da CVM.")])
        
        print(f"\n--- ACIONANDO O AGENTE: '{AgenteColetorRegulatorios_ADK.name}' ---")
        async for event in runner.run_async(new_message=message, user_id=user_id, session_id=session_id):
            if event.author == AgenteColetorRegulatorios_ADK.name and event.content:
                print(f"[{event.author}]: {event.content.parts[0].text}")

    try:
        asyncio.run(run_test())
    except Exception as e:
        settings.logger.critical(f"FALHA NO TESTE: {e}", exc_info=True)

    settings.logger.info(f"--- Fim do teste standalone ---")