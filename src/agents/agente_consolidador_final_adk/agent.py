# src/agents/agente_consolidador_final_adk/agent.py
# -*- coding: utf-8 -*-
import asyncio
import os
import sys
import json
import re # Importar a biblioteca 're' para expressões regulares
from pathlib import Path

# Bloco de import padrão
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent # Ajuste se o root for diferente
    if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())

from config import settings
from google.adk.agents import LlmAgent
from google.adk.events import Event
from google.genai.types import Content, Part
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner

# Importar o prompt e a ferramenta instanciada
from . import prompt as agent_prompt
# Importe a ferramenta instanciada (fetch_topic_analysis_from_db_tool)
from .tools.tool_get_analyses_for_topic import fetch_topic_analysis_from_db_tool
from .tools.tool_get_quantitative_market_data import get_quantitative_market_data_tool
from .tools.tool_calculate_financial_metrics import calculate_gordon_growth_fair_price_tool, calculate_capm_tool

# --- Definição do Agente Consolidador ---
profile = settings.AGENT_PROFILES.get("analista_profundo") 

class AgenteConsolidadorAnalise(LlmAgent):
    def __init__(self):
        super().__init__(
            name="agente_consolidador_analise",
            model=profile.get("model_name"),
            generate_content_config=profile.get("generate_content_config"),
            planner=profile.get("planner"),
            instruction=agent_prompt.PROMPT,
            description="Analista Estratégico Chefe que sintetiza múltiplas análises de notícias em um Relatório de Inteligência de alto nível.",
            tools=[
                fetch_topic_analysis_from_db_tool, 
                get_quantitative_market_data_tool,
                calculate_gordon_growth_fair_price_tool,
                calculate_capm_tool
            ]
        )
        settings.logger.info(f"Agente '{self.name}' carregado.")

    # <<< REMOVIDO: O MÉTODO _run_async_impl NÃO É MAIS SOBRESCRITO >>>
    # O LlmAgent base já lida com a execução do LLM e das ferramentas com base no prompt.

# Instancia o agente para exportação
AgenteConsolidadorAnalise_ADK = AgenteConsolidadorAnalise()

# --- Bloco de Teste Standalone (Ajustado) ---
if __name__ == '__main__':
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    # Defina PROJECT_ID e LOCATION em settings.py, ou aqui para o teste.
    # Ex: os.environ["GOOGLE_CLOUD_PROJECT"] = "seu-projeto-id"
    # os.environ["GOOGLE_CLOUD_LOCATION"] = "us-central1"

    settings.logger.info(f"--- Executando teste standalone para: {AgenteConsolidadorAnalise_ADK.name} ---")

    async def run_test():
        runner = Runner(agent=AgenteConsolidadorAnalise_ADK, app_name="test_app_consol", session_service=InMemorySessionService())
        user_id, session_id = "test_user_consol", "test_session_consol"
        await runner.session_service.create_session(app_name=runner.app_name, user_id=user_id, session_id=session_id)
        
        test_message = Content(role='user', parts=[Part(text="Gere um relatório estratégico para 'Petrobras' dos últimos 7 dias.")])
        
        print(f"\n--- ENVIANDO PROMPT PARA O CONSOLIDADOR: '{test_message.parts[0].text}' ---")
        
        final_response_event_content_text = None # Para armazenar o texto da resposta final, se houver

        async for event in runner.run_async(new_message=test_message, user_id=user_id, session_id=session_id):
            # Check if event has content and if it's not a function_call part before printing as text.
            # The LLM's raw response shows that function_call parts don't have 'text'.
            # So we check if event.content and event.content.parts exist,
            # and then check if parts[0] is a function_call (it will have 'function_call' attribute)
            # or if it has text.
            
            # Check for content first
            if event.content and event.content.parts and event.content.parts[0]:
                part_0 = event.content.parts[0]
                
                # Check if it's a function call part
                if hasattr(part_0, 'function_call') and part_0.function_call:
                    # This is a function call, let the runner handle it.
                    # We don't need to log its text here in the 'text' branch.
                    pass 
                elif part_0.text: # This is a text part
                    # Imprime o texto de eventos intermediários/final, se não for uma chamada de função
                    print(f"  [Log Interno - Texto]: {part_0.text[:500]}...") # Limita o log
                    
                    if event.is_final_response():
                        final_response_event_content_text = part_0.text
                        # Break here, so we process the final response once outside the loop
                        break 
            
            # If it's the final response and no text content was found/set
            if event.is_final_response() and not final_response_event_content_text:
                 print("\n--- RESPOSTA FINAL DO CONSOLIDADOR: Agente finalizou sem conteúdo de texto. ---")
                 settings.logger.error("Agente Consolidador finalizou sem conteúdo de texto na resposta final.")
                 break # Exit test loop if final response has no text


        # Processa a resposta final após o loop
        if final_response_event_content_text:
            print("\n--- RESPOSTA FINAL DO CONSOLIDADOR (JSON do Relatório Estratégico) ---")
            try:
                # Tentar extrair o JSON usando regex mais robusta
                # Este regex busca o primeiro bloco de código JSON em um texto.
                # Ele captura qualquer coisa que esteja entre ```json e ```
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', final_response_event_content_text, re.DOTALL)
                if json_match:
                    json_string = json_match.group(1) # Captura o conteúdo do JSON
                    final_json = json.loads(json_string)
                    print(json.dumps(final_json, indent=2, ensure_ascii=False))
                else:
                    # Se não encontrar o bloco ```json, tentar carregar o texto inteiro como JSON
                    # Este path ainda é um fallback, o ideal é que o regex acima funcione.
                    final_json = json.loads(final_response_event_content_text)
                    print(json.dumps(final_json, indent=2, ensure_ascii=False))
                    
            except json.JSONDecodeError as e:
                print("Resposta final não é um JSON válido:")
                print(f"Erro: {e}")
                print(f"Texto bruto que causou o erro (primeiros 500 chars): {final_response_event_content_text[:500]}...")
        else:
            print("\n--- RESPOSTA FINAL DO CONSOLIDADOR: Não foi possível obter conteúdo final. ---")

    try:
        asyncio.run(run_test())
    except Exception as e:
        settings.logger.critical(f"FALHA NO TESTE: {e}", exc_info=True)
    settings.logger.info(f"--- Fim do teste standalone ---")