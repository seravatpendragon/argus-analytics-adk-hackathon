import os
import sys
from pathlib import Path
import asyncio
import json

# Bloco de import padrão
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())

from config import settings
from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from .tools.tool_calculate_text_metrics import analyze_text_metrics

class SubAgenteQuantitativo(BaseAgent):
    """
    Um agente procedural que usa a ferramenta de análise de texto para
    calcular métricas quantitativas de um artigo.
    """
    def __init__(self, name: str = "sub_agente_quantitativo", description: str = "Agente que recebe um texto e retorna métricas quantitativas como Entropia, contagem de palavras-chave e legibilidade."):
        super().__init__(name=name, description=description)

    async def _run_async_impl(self, context):
        """
        Recebe o texto do usuário e passa para a ferramenta de análise.
        """

        settings.logger.info(f"Agente {self.name} iniciado.")
        
       # --- INÍCIO DA CORREÇÃO ---
        text_to_analyze = ""
        # Acessa diretamente o conteúdo do usuário para a invocação atual
        if context.user_content and context.user_content.parts:
            text_to_analyze = context.user_content.parts[0].text
        # --- FIM DA CORREÇÃO ---

        if not text_to_analyze:
            error_msg = json.dumps({"status": "error", "message": "Nenhum texto fornecido para análise no 'user_content'."})
            yield Event(author=self.name, content=Content(parts=[Part(text=error_msg)]))
            return
        yield Event(
            author=self.name,
            content=Content(parts=[Part(text="Analisando métricas quantitativas do texto...")])
        )
        
        metrics = analyze_text_metrics(text_to_analyze)
        
        # Garante que a resposta final seja sempre um JSON string
        yield Event(
            author=self.name,
            content=Content(parts=[Part(text=json.dumps(metrics, ensure_ascii=False))])
        )

SubAgenteQuantitativo_ADK = SubAgenteQuantitativo()

# --- Bloco de Teste ---
if __name__ == '__main__':
    # Configuração de ambiente para execução standalone
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        if hasattr(settings, 'PROJECT_ID') and settings.PROJECT_ID:
            os.environ["GOOGLE_CLOUD_PROJECT"] = settings.PROJECT_ID
    if not os.getenv("GOOGLE_CLOUD_LOCATION"):
        if hasattr(settings, 'LOCATION') and settings.LOCATION:
            os.environ["GOOGLE_CLOUD_LOCATION"] = settings.LOCATION

    settings.logger.info(f"--- Executando teste standalone para: {SubAgenteQuantitativo_ADK.name} ---")

    async def run_test():
        runner = Runner(agent=SubAgenteQuantitativo_ADK, app_name="test_app_quant", session_service=InMemorySessionService())
        user_id, session_id = "test_user_quant", "test_session_quant"
        
        # --- AQUI ESTÁ A CORREÇÃO ---
        # 1. Criamos a sessão antes de usá-la.
        await runner.session_service.create_session(
            app_name=runner.app_name, user_id=user_id, session_id=session_id
        )
        
        texto_exemplo = (
            "Este é um teste. Um teste. Este é um teste. Teste, teste, teste. Este é um teste. Um teste. Este é um teste. Teste, teste, teste. Este é um teste. Um teste. Este é um teste. Teste, teste, teste. Este é um teste. Um teste. Este é um teste. Teste, teste, teste. Este é um teste. Um teste. Este é um teste. O teste. O teste é o teste. O teste é o teste do teste. O teste. O teste é o teste. O teste é o teste do teste. O teste. O teste é o teste. O teste é o teste do teste. O teste. O teste é o teste. O teste é o teste do teste. Teste. Teste, teste. Teste, teste, teste. Teste. Teste, teste. Teste, teste, teste. Teste. Teste, teste. Teste, teste, teste. Teste. Teste, teste. Teste, teste, teste. Teste. Teste, teste. Teste, teste, teste. Um teste é um teste. Este teste é um teste. Um teste é um teste. Este teste é um teste. Um teste é um teste. Este teste é um teste. Um teste é um teste. Este teste é um teste."
        )
        
        message = Content(role='user', parts=[Part(text=texto_exemplo)])
        
        print(f"\n--- ENVIANDO TEXTO PARA O AGENTE QUANTITATIVO ---")
        
        # 2. Passamos o `session_id` correto para a chamada do `run_async`.
        async for event in runner.run_async(new_message=message, user_id=user_id, session_id=session_id):
            if event.is_final_response():
                print("\n--- RESPOSTA FINAL (JSON de métricas) ---")
                try:
                    final_json = json.loads(event.content.parts[0].text)
                    print(json.dumps(final_json, indent=2, ensure_ascii=False))
                except json.JSONDecodeError:
                    print(event.content.parts[0].text)
    try:
        asyncio.run(run_test())
    except Exception as e:
        settings.logger.critical(f"FALHA NO TESTE: {e}", exc_info=True)

    settings.logger.info(f"--- Fim do teste standalone ---")