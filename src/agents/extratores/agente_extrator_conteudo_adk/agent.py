import os
import sys
from pathlib import Path
import asyncio

# --- Bloco Padrão de Configuração e Imports ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())

from config import settings
# Importa o BaseAgent e o Event
from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part, FinishReason

# Importa as funções Python diretamente
from .tools.tool_fetch_articles_pending_extraction import tool_fetch_articles_pending_extraction
from .tools.tool_extract_and_save_content import tool_extract_and_save_content

# --- Definição do Agente Extrator ---
class AgenteExtratorConteudo(BaseAgent):
    """
    Um agente procedural que encapsula a lógica de extração de conteúdo.
    """
    def __init__(self, name: str = "agente_extrator_conteudo_v1", description: str = "Agente especialista para buscar e extrair o conteúdo completo de artigos a partir de URLs."):
        super().__init__(name=name, description=description)

    async def _run_async_impl(self, context):
        """
        Executa a lógica procedural de busca e extração.
        """
        settings.logger.info(f"Agente {self.name} iniciado.")
        # CORREÇÃO: Construindo o objeto Event manualmente
        yield Event(
            author=self.name,
            content=Content(parts=[Part(text="Iniciando pipeline de extração de conteúdo...")])
        )
        
        erros = 0
        sucessos = 0
        
        try:
            fetch_result = tool_fetch_articles_pending_extraction()
            articles_to_process = fetch_result.get("articles_to_process", [])
            
            if not articles_to_process:
                yield Event(
                    author=self.name,
                    content=Content(parts=[Part(text="Nenhum artigo novo para processar.")])
                )
            else:
                msg = f"Encontrados {len(articles_to_process)} artigos. Iniciando extração em lote..."
                settings.logger.info(msg)
                yield Event(
                    author=self.name,
                    content=Content(parts=[Part(text=msg)])
                )
                
                for article in articles_to_process:
                    article_id = article.get("article_id")
                    url = article.get("url")
                    if not article_id or not url: continue
                    
                    result = tool_extract_and_save_content(article_id=article_id, url=url)
                    
                    if result.get("status") in ["success", "success_skipped"]:
                        sucessos += 1
                    else:
                        erros += 1
                
                final_summary = f"Processo de extração concluído. Sucessos: {sucessos}, Falhas: {erros}."
                settings.logger.info(final_summary)
                yield Event(
                    author=self.name,
                    content=Content(parts=[Part(text=final_summary)])
                )

        except Exception as e:
            error_message = f"FALHA GERAL NO PIPELINE DE EXTRAÇÃO: {e}"
            settings.logger.critical(error_message, exc_info=True)
            yield Event(
                author=self.name,
                content=Content(parts=[Part(text=error_message)]),
                finish_reason=FinishReason.ERROR
            )

# Instancia o agente
AgenteExtratorConteudo_ADK = AgenteExtratorConteudo()

# --- Bloco de Teste Corrigido ---
if __name__ == '__main__':
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"    
    settings.logger.info(f"--- Executando teste standalone para: {AgenteExtratorConteudo_ADK.name} ---")
    
    async def run_test():
        runner = Runner(agent=AgenteExtratorConteudo_ADK, app_name="test_app_extractor", session_service=InMemorySessionService())
        user_id, session_id = "test_user_extr", "test_session_extr"
        
        await runner.session_service.create_session(
            app_name=runner.app_name, user_id=user_id, session_id=session_id
        )
        
        message = Content(role='user', parts=[Part(text="Inicie a extração.")])
        
        print(f"\n--- ENVIANDO PROMPT PARA O EXTRATOR: '{message.parts[0].text}' ---")
        
        async for event in runner.run_async(new_message=message, user_id=user_id, session_id=session_id):
            
            # --- AQUI ESTÁ A LINHA CORRIGIDA ---
            # Em vez de um método, comparamos o atributo 'author' do evento.
            if event.author != AgenteExtratorConteudo_ADK.name:
                continue # Pula eventos que não são do nosso agente (ex: eventos do sistema)
            
            if event.content and event.content.parts:
                # Usamos o event.author para uma impressão mais robusta
                print(f"[{event.author}]: {event.content.parts[0].text}")

    try:
        asyncio.run(run_test())
        print("\n--- Resumo do Teste ---")
        print(f"SUCESSO: O pipeline do Agente Extrator foi executado sem erros de programação.")
    except Exception as e:
        settings.logger.critical(f"FALHA: Ocorreu um erro inesperado: {e}", exc_info=True)

    settings.logger.info(f"--- Fim do Teste do Agente Extrator ---")