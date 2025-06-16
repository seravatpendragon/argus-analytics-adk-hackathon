# src/agents/analistas/sub_agentes_analise/sub_agente_impacto_maslow_adk/agent.py

import os, sys, asyncio, json
from pathlib import Path

# Bloco de import padrão
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

SubAgenteImpactoMaslow_ADK = LlmAgent(
    name="sub_agente_impacto_maslow",
    model=profile.get("model_name"),
    generate_content_config=profile.get("generate_content_config"),
    planner=profile.get("planner"),
    instruction=agent_prompt.PROMPT,
    description="Agente que classifica uma notícia segundo a Hierarquia de Necessidades Corporativas de Maslow."
)

# --- Bloco de Teste ---
if __name__ == '__main__':
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

    async def run_test():
        runner = Runner(agent=SubAgenteImpactoMaslow_ADK, app_name="test_app_maslow", session_service=InMemorySessionService())
        user_id, session_id = "test_user_maslow", "test_session_maslow"
        await runner.session_service.create_session(app_name=runner.app_name, user_id=user_id, session_id=session_id)
        
        texto_exemplo = (
            "O governo anunciou medidas para arrecadar R$ 30 bi, mas fontes oficiais negam qualquer proposta. Analistas divergem sobre os impactos."
            )
        
        message = Content(role='user', parts=[Part(text=texto_exemplo)])
        
        print(f"\n--- ENVIANDO TEXTO PARA O AGENTE MASLOW ---")
        async for event in runner.run_async(new_message=message, user_id=user_id, session_id=session_id):
            if event.is_final_response():
                print("\n--- RESPOSTA FINAL (JSON de Maslow) ---")
                try:
                    final_json = json.loads(event.content.parts[0].text)
                    print(json.dumps(final_json, indent=2, ensure_ascii=False))
                except json.JSONDecodeError:
                    print(event.content.parts[0].text)
    
    asyncio.run(run_test())