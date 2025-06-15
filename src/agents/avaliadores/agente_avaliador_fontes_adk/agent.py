import os
import sys
import json
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any

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
    from google.adk.agents import LlmAgent
    from google.adk.tools import google_search
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai.types import Content, Part
    from src.database.db_utils import get_db_session, get_sources_pending_craap_analysis, update_source_craap_analysis
    from src.database.create_db_tables import NewsSource
    from . import prompt as agent_prompt
except ImportError as e:
    import logging
    _logger = logging.getLogger(__name__)
    _logger.critical(f"Erro CRÍTICO de importação: {e}", exc_info=True)
    sys.exit(1)

# --- Definições dos Agentes ---

# Agente Principal (Avaliador)
profile = settings.AGENT_PROFILES.get("avaliador")
AgenteAvaliadorDeFontes_ADK = LlmAgent(
    name="agente_avaliador_fontes",
    model=profile.get("model_name"),
    generate_content_config=profile.get("generate_content_config"),
    instruction=agent_prompt.PROMPT,
    description="Agente especialista que usa o Grounding do Vertex AI para avaliar a credibilidade.",
    tools=[google_search],
)

# Agente Secundário (Corretor de JSON)
JSON_REPAIR_PROMPT = """
Sua única e exclusiva tarefa é corrigir a sintaxe do texto a seguir para que se torne um objeto JSON válido.
Retorne APENAS o JSON corrigido. Não adicione comentários, explicações, ou a palavra "json".

JSON com erro:
{text_with_error}
"""
corrector_config = settings.AGENT_CONFIGS.get("coletor", {}) 
JSONCorrectorAgent = LlmAgent(
    name="json_corrector_agent",
    model=corrector_config.get("model_name"),
    # A instrução agora será formatada dinamicamente, então o padrão pode ser simples.
    instruction="Você é um especialista em corrigir sintaxe JSON." 
)


async def analyze_one_source(main_runner: Runner, source: NewsSource) -> tuple[int, Optional[Dict[str, Any]]]:
    """ Função assíncrona que executa a análise e tenta corrigir falhas de JSON. """
    session_id = f"craap_session_{source.news_source_id}"
    await main_runner.session_service.create_session(
        app_name=main_runner.app_name, user_id="system_user", session_id=session_id
    )
    
    prompt_text = f"Analise o domínio: {source.url_base}"
    message = Content(role='user', parts=[Part(text=prompt_text)])
    
    final_agent_response = None
    try:
        async for event in main_runner.run_async(user_id="system_user", session_id=session_id, new_message=message):
            if event.is_final_response() and event.content and event.content.parts:
                final_agent_response = event.content.parts[0].text
        
        if not final_agent_response:
            settings.logger.error(f"Agente principal não retornou resposta para '{source.name}'.")
            return source.news_source_id, None

        try:
            json_str = final_agent_response.strip().removeprefix("```json").removesuffix("```")
            return source.news_source_id, json.loads(json_str)
        except json.JSONDecodeError as e:
            settings.logger.warning(f"Falha no parsing de JSON para '{source.name}'. Acionando agente corretor. Erro: {e}")

            # --- CORREÇÃO DA CORREÇÃO ---
            corrector_instruction = JSON_REPAIR_PROMPT.format(text_with_error=final_agent_response)
            
            corrector_config = settings.AGENT_CONFIGS.get("coletor", {}) 
            temp_corrector_agent = LlmAgent(
                name="json_corrector_agent_temp",
                model=corrector_config.get("model_name"),
                instruction=corrector_instruction
            )
            temp_corrector_runner = Runner(agent=temp_corrector_agent, app_name="corrector_app", session_service=InMemorySessionService())
            
            # 1. É necessário criar uma sessão para o runner temporário
            corrector_session_id = f"corrector_session_{source.news_source_id}"
            await temp_corrector_runner.session_service.create_session(
                app_name=temp_corrector_runner.app_name, user_id="system_user", session_id=corrector_session_id
            )

            correction_message = Content(role='user', parts=[Part(text="Corrija.")])
            
            corrected_response_text = None
            
            # 2. AQUI ESTÁ A LINHA CORRIGIDA: Passar o session_id para a chamada do run_async
            async for event in temp_corrector_runner.run_async(
                user_id="system_user", 
                session_id=corrector_session_id, 
                new_message=correction_message
            ):
                if event.is_final_response() and event.content and event.content.parts:
                    corrected_response_text = event.content.parts[0].text
                    break # Apenas a resposta final é necessária
            
            if not corrected_response_text:
                settings.logger.error(f"Agente corretor não retornou resposta para '{source.name}'.")
                return source.news_source_id, None

            try:
                json_str = corrected_response_text.strip().removeprefix("```json").removesuffix("```")
                settings.logger.info(f"SUCESSO: JSON para '{source.name}' foi corrigido pelo agente corretor.")
                return source.news_source_id, json.loads(json_str)
            except json.JSONDecodeError as final_e:
                settings.logger.error(f"FALHA FINAL: Parsing do JSON falhou mesmo após correção para '{source.name}'. Erro: {final_e}")

    except Exception as e:
        settings.logger.error(f"Erro crítico na execução do runner para a fonte '{source.name}': {e}", exc_info=True)

    return source.news_source_id, None

async def run_craap_analysis_pipeline():
    """ Orquestra o processo completo, de forma concorrente. """
    settings.logger.info("--- Iniciando Pipeline de Análise de Credibilidade (v4 - Resiliente) ---")
    
    with get_db_session() as db_session:
        sources = get_sources_pending_craap_analysis(db_session, limit=settings.QUANTIDADE_AVALIACAO)
        if not sources:
            print("Nenhuma fonte nova para analisar.")
            return

        print(f"Encontradas {len(sources)} fontes. Criando tarefas de análise...")
        
        main_runner = Runner(agent=AgenteAvaliadorDeFontes_ADK, app_name="craap_app", session_service=InMemorySessionService())
        
        # Não precisamos mais do corrector_runner aqui, pois ele é criado sob demanda.
        tasks = [analyze_one_source(main_runner, source) for source in sources]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        updates_succeeded = 0
        for result in results:
            if isinstance(result, Exception):
                settings.logger.error(f"Uma tarefa de análise falhou com uma exceção: {result}")
                continue

            source_id, analysis_json = result
            if analysis_json:
                score = analysis_json.get("overall_credibility_score")
                if score is not None:
                    print(f"-> Análise para source_id {source_id} concluída. Score: {score}")
                    update_source_craap_analysis(db_session, source_id, float(score), analysis_json)
                    updates_succeeded += 1
                else:
                    settings.logger.warning(f"Análise para source_id {source_id} não continha score.")
            else:
                settings.logger.error(f"Análise para source_id {source_id} retornou nula.")
        
        if updates_succeeded > 0:
            db_session.commit()
            print(f"\n{updates_succeeded} análises salvas no banco com sucesso.")
        else:
            print("\nNenhuma análise bem-sucedida para salvar.")

if __name__ == '__main__':
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        if hasattr(settings, 'PROJECT_ID') and settings.PROJECT_ID:
            os.environ["GOOGLE_CLOUD_PROJECT"] = settings.PROJECT_ID
        else:
            print("ERRO: GOOGLE_CLOUD_PROJECT não definida no ambiente ou em settings.py.")
            sys.exit(1)
            
    if not os.getenv("GOOGLE_CLOUD_LOCATION"):
        if hasattr(settings, 'LOCATION') and settings.LOCATION:
            os.environ["GOOGLE_CLOUD_LOCATION"] = settings.LOCATION
        else:
            print("AVISO: GOOGLE_CLOUD_LOCATION não definida. Usando 'global' como padrão.")
            os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
            
    try:
        asyncio.run(run_craap_analysis_pipeline())
    except Exception as e:
        settings.logger.critical(f"❌ FALHA GERAL NO PIPELINE: {e}", exc_info=True)