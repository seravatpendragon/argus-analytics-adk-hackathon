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
from google.adk.agents import LlmAgent # Usando LlmAgent desta vez
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from . import prompt as agent_prompt

# --- Definição do Agente ---
profile = settings.AGENT_PROFILES.get("analista_rapido") 


SubAgenteResumo_ADK = LlmAgent(
    name="sub_agente_resumo",
    model=profile.get("model_name"),
    generate_content_config=profile.get("generate_content_config"),
    planner=profile.get("planner"),
    instruction=agent_prompt.PROMPT,
    description="Agente especialista que recebe um texto e cria um resumo conciso."
)

settings.logger.info(f"Agente '{SubAgenteResumo_ADK.name}' carregado.")

# --- Bloco de Teste ---
if __name__ == '__main__':
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    
    async def run_test():
        runner = Runner(agent=SubAgenteResumo_ADK, app_name="test_app_resumo", session_service=InMemorySessionService())
        user_id, session_id = "test_user_resumo", "test_session_resumo"
        
        await runner.session_service.create_session(
            app_name=runner.app_name, user_id=user_id, session_id=session_id
        )
        
        texto_exemplo = (
            "O Banco Central anunciou hoje que a taxa Selic será mantida em 10,50% ao ano. "
            "A decisão foi unânime entre os membros do Comitê de Política Monetária (Copom). "
            "Segundo o comunicado, o cenário externo de incerteza e a persistência da inflação de serviços no Brasil "
            "justificam uma postura de cautela. O mercado financeiro já esperava pela manutenção da taxa de juros."
        )
        
        message = Content(role='user', parts=[Part(text=texto_exemplo)])
        
        print(f"\n--- ENVIANDO TEXTO PARA O AGENTE RESUMIDOR ---")
        async for event in runner.run_async(new_message=message, user_id=user_id, session_id=session_id):
            if event.is_final_response():
                print("\n--- RESPOSTA FINAL (JSON de resumo) ---")
                print(event.content.parts[0].text)

    asyncio.run(run_test())