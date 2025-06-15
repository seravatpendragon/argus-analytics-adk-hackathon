import os
import sys
from pathlib import Path
import asyncio
import json

# Bloco de import padrão...
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())

from config import settings
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from . import prompt as agent_prompt

# --- Definição do Agente ---
profile = settings.AGENT_PROFILES.get("analista_profundo") 


SubAgenteSentimento_ADK = LlmAgent(
    name="sub_agente_sentimento",
    model=profile.get("model_name"),
    generate_content_config=profile.get("generate_content_config"),
    planner=profile.get("planner"),
    instruction=agent_prompt.PROMPT,
    description="Agente especialista que analisa o sentimento de um texto e retorna um score e um rótulo."
)

settings.logger.info(f"Agente '{SubAgenteSentimento_ADK.name}' carregado.")

# --- Bloco de Teste Standalone ---
if __name__ == '__main__':
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    
    async def run_test():
        runner = Runner(agent=SubAgenteSentimento_ADK, app_name="test_app_sentimento", session_service=InMemorySessionService())
        user_id, session_id = "test_user_sentim", "test_session_sentim"
        
        await runner.session_service.create_session(
            app_name=runner.app_name, user_id=user_id, session_id=session_id
        )
        
        texto_exemplo = (
            "Mais uma vez, a diretoria da VarejoTotal demonstrou sua 'brilhante' capacidade de gestão ao anunciar perdas de R$ 500 milhões, o terceiro prejuízo consecutivo. "
            "A estratégia 'inovadora' de fechar suas lojas mais lucrativas certamente é um movimento de mestre para 'consolidar' a marca no mercado. "
            "O mercado, em seu claro sinal de entusiasmo, respondeu com uma desvalorização de 15% das ações."
        )
                
        message = Content(role='user', parts=[Part(text=texto_exemplo)])
        
        print(f"\n--- ENVIANDO TEXTO PARA O AGENTE DE SENTIMENTO ---")
        async for event in runner.run_async(new_message=message, user_id=user_id, session_id=session_id):
            if event.is_final_response():
                print("\n--- RESPOSTA FINAL (JSON de sentimento) ---")
                try:
                    final_json = json.loads(event.content.parts[0].text)
                    print(json.dumps(final_json, indent=2, ensure_ascii=False))
                except json.JSONDecodeError:
                    print(event.content.parts[0].text)

    asyncio.run(run_test())