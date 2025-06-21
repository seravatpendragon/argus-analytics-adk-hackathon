import os
import sys
import json
from pathlib import Path
import asyncio

# Bloco de import padrão
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent
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

AgenteAuditorQualidade_ADK = LlmAgent(
    name="agente_auditor_qualidade",
    model=profile.get("model_name"),
    generate_content_config=profile.get("generate_content_config"),
    planner=profile.get("planner"),
    instruction=agent_prompt.PROMPT,
    description="Agente especialista que revisa e corrige análises de IA com base em uma lista de conflitos detectados."
)

settings.logger.info(f"Agente '{AgenteAuditorQualidade_ADK.name}' carregado.")

# --- Bloco de Teste Standalone ---
if __name__ == '__main__':
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    
    async def run_test():
        runner = Runner(agent=AgenteAuditorQualidade_ADK, app_name="test_app_auditor", session_service=InMemorySessionService())
        user_id, session_id = "test_user_auditor", "test_session_auditor"
        await runner.session_service.create_session(app_name=runner.app_name, user_id=user_id, session_id=session_id)

        # Simulação de um JSON de análise com um conflito
        analise_com_conflito = {
          "analise_sentimento": {
            "sentiment_score": 0.8,
            "sentiment_label": "Positivo",
            "intensity": "Leve", # <-- Conflito: Score alto, intensidade baixa
            "justification": "O resultado foi muito bom."
          },
          "analise_entidades": {"foco_principal_sugerido": "Empresa X"}
        }

        # Simulação da lista de conflitos detectados
        conflitos_detectados = [
            "Conflito Lógico: Sentimento forte com intensidade fraca."
        ]

        # Monta o prompt de entrada para o agente auditor
        prompt_para_auditor = (
            f"--- CONFLITOS DETECTADOS ---\n"
            f"{json.dumps(conflitos_detectados, indent=2, ensure_ascii=False)}\n\n"
            f"--- JSON ORIGINAL PARA REVISÃO ---\n"
            f"{json.dumps(analise_com_conflito, indent=2, ensure_ascii=False)}"
        )
        
        message = Content(role='user', parts=[Part(text=prompt_para_auditor)])
        
        print(f"\n--- ENVIANDO ANÁLISE COM CONFLITO PARA O AGENTE AUDITOR ---")
        async for event in runner.run_async(new_message=message, user_id=user_id, session_id=session_id):
            if event.is_final_response():
                print("\n--- RESPOSTA FINAL DO AUDITOR (JSON Corrigido) ---")
                try:
                    final_json = json.loads(event.content.parts[0].text.strip().removeprefix("```json").removesuffix("```"))
                    print(json.dumps(final_json, indent=2, ensure_ascii=False))
                except json.JSONDecodeError:
                    print(event.content.parts[0].text)

    asyncio.run(run_test())