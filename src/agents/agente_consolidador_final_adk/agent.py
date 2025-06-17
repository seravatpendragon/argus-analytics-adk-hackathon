import os
import sys
from pathlib import Path
import asyncio
import json

# Bloco de import padrão...
from config import settings
from google.adk.agents import LlmAgent
# CORREÇÃO: Importando FunctionTool
from google.adk.tools import FunctionTool 
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
# CORREÇÃO: Importando a função pura
from .tools.tool_get_analyses_for_topic import fetch_topic_analysis_from_db 
from . import prompt as agent_prompt

# --- Definição do Agente ---
profile = settings.AGENT_PROFILES.get("analista_profundo")

get_analysis_tool = FunctionTool(func=fetch_topic_analysis_from_db)

AgenteConsolidadorFinal_ADK = LlmAgent(
    name="agente_consolidador_final",
    model=profile.get("model_name"),
    generate_content_config=profile.get("generate_content_config"),
    planner=profile.get("planner"),
    instruction=agent_prompt.PROMPT,
    description="Agente Chefe que sintetiza múltiplas análises de notícias em um único relatório de inteligência.",
    tools=[get_analysis_tool],
)

settings.logger.info(f"Agente '{AgenteConsolidadorFinal_ADK.name}' carregado.")


# --- Bloco de Teste ---
# O bloco de teste if __name__ == '__main__': permanece o mesmo.
if __name__ == '__main__':
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

    async def run_test():
        runner = Runner(agent=AgenteConsolidadorFinal_ADK, app_name="test_app_consolidador", session_service=InMemorySessionService())
        user_id, session_id = "test_user_consol", "test_session_consol"
        await runner.session_service.create_session(app_name=runner.app_name, user_id=user_id, session_id=session_id)
        
        prompt_text = "Por favor, gere um relatório de inteligência consolidado para o tópico 'Petrobras' nos últimos 30 dias."
        message = Content(role='user', parts=[Part(text=prompt_text)])
        
        print(f"\n--- ENVIANDO COMANDO PARA O AGENTE CONSOLIDADOR ---")
        print(f"Prompt: {prompt_text}")
        
        async for event in runner.run_async(new_message=message, user_id=user_id, session_id=session_id):
            # --- CORREÇÃO AQUI ---
            # Verificamos se a primeira parte do conteúdo é uma chamada de função
            if event.content and event.content.parts and event.content.parts[0].function_call:
                print("\n--- AGENTE DECIDIU USAR A FERRAMENTA ---")
                fc = event.content.parts[0].function_call
                # Usamos dict() para imprimir os argumentos de forma legível
                print(f"Ferramenta: {fc.name}, Argumentos: {dict(fc.args)}")

            if event.is_final_response():
                print("\n--- RELATÓRIO DE INTELIGÊNCIA FINAL ---")
                try:
                    # Limpamos a resposta antes de fazer o parse
                    response_text = event.content.parts[0].text
                    clean_json_str = response_text.strip().removeprefix("```json").removesuffix("```")
                    final_json = json.loads(clean_json_str)
                    print(json.dumps(final_json, indent=2, ensure_ascii=False))
                except (json.JSONDecodeError, IndexError) as e:
                    print(f"Erro ao fazer o parse da resposta final: {e}")
                    print(f"Resposta bruta recebida: {event.content.parts[0].text}")

    asyncio.run(run_test())
