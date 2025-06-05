# run_llm_analysis_pipeline_test.py

import os
import sys
from pathlib import Path
import json
from datetime import datetime
import asyncio 
import re 

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent 
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    print(f"PROJECT_ROOT ({PROJECT_ROOT}) foi adicionado/confirmado no sys.path para run_llm_analysis_pipeline_test.py.")
except NameError:
    PROJECT_ROOT = Path(os.getcwd())
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    print(f"AVISO (run_llm_analysis_pipeline_test.py): __file__ não definido. Usando PROJECT_ROOT como: {PROJECT_ROOT}")

src_path = PROJECT_ROOT / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
    print(f"src_path ({src_path}) foi adicionado/confirmado no sys.path.")

try:
    from config import settings
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types 
    
    # Importa a ferramenta de busca de artigos pendentes
    from agents.agente_gerenciador_analise_llm_adk.tools.tool_fetch_pending_articles import tool_fetch_pending_articles

    # Importa os agentes (o gerenciador e os sub-agentes de análise)
    from agents.agente_gerenciador_analise_llm_adk.agent import AgenteGerenciadorDeAnaliseLLM_ADK
    from agents.sub_agente_sentimento_adk.agent import SubAgenteSentimento_ADK
    from agents.sub_agente_relevancia_tipo_adk.agent import SubAgenteRelevanciaTipo_ADK
    from agents.sub_agente_stakeholders_adk.agent import SubAgenteStakeholders_ADK
    from agents.sub_agente_impacto_maslow_adk.agent import SubAgenteImpactoMaslow_ADK
    from agents.agente_consolidador_analise_adk.agent import AgenteConsolidadorDeAnalise_ADK # O Consolidador
    
    # Importa a ferramenta de persistência para chamá-la manualmente
    from agents.agente_consolidador_analise_adk.tools.tool_update_article_analysis import tool_update_article_analysis

    print("Módulos de agentes e ferramentas importados com sucesso.")

except ImportError as e:
    if 'settings' not in locals() and 'settings' in globals():
        import logging
        log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        _fb_logger = logging.getLogger("llm_analysis_test_logger_fallback")
        settings = type('SettingsFallback', (), {'logger': _fb_logger})()

    settings.logger.error(f"Erro CRÍTICO ao importar módulos em run_llm_analysis_pipeline_test.py: {e}")
    settings.logger.error(f"Verifique se as pastas dos agentes e seus arquivos existem e estão acessíveis.")
    settings.logger.error(f"sys.path atual: {sys.path}")
    sys.exit(1)
except Exception as e:
    if 'settings' not in locals() and 'settings' in globals():
        import logging
        log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        _fb_logger = logging.getLogger("llm_analysis_test_logger_fallback2")
        settings = type('SettingsFallback', (), {'logger': _fb_logger})()

    settings.logger.error(f"Erro INESPERADO durante imports iniciais em run_llm_analysis_pipeline_test.py: {e}")
    sys.exit(1)

if not hasattr(settings, 'logger'):
    import logging
    log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_format)
    settings.logger = logging.getLogger("llm_analysis_test_logger")
    settings.logger.info("Logger fallback inicializado em run_llm_analysis_pipeline_test.py.")


settings.logger.info("--- INICIANDO TESTE DE INTEGRAÇÃO SIMULADO: Pipeline de Análise LLM ---")

# --- Configuração da API Key do Google AI Studio ---
gemini_api_key = getattr(settings, "GEMINI_API_KEY", None)

if not gemini_api_key:
    settings.logger.critical("ERRO: GEMINI_API_KEY não definida em config/settings.py! A análise LLM falhará. Por favor, defina-a.")
    sys.exit(1)

os.environ["GOOGLE_API_KEY"] = gemini_api_key
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False" # Garante que use a API pública, não o Vertex AI

settings.logger.info("GEMINI_API_KEY carregada de settings.py. Usando Google AI API (não Vertex AI).")


# --- Setup do Runner e Session Service do ADK ---
APP_NAME = "argus_llm_analysis"
USER_ID = "test_user_llm"
SESSION_ID = "test_session_llm_001"


async def run_llm_analysis_pipeline():
    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID)
    settings.logger.info(f"ADK Session criada: App='{APP_NAME}', User='{USER_ID}', Session='{SESSION_ID}'")

    # Instanciar os Runners para cada sub-agente de análise e para o Consolidador
    sentiment_agent_runner = Runner(
        agent=SubAgenteSentimento_ADK,
        app_name=APP_NAME,
        session_service=session_service
    )
    relevance_type_agent_runner = Runner(
        agent=SubAgenteRelevanciaTipo_ADK,
        app_name=APP_NAME,
        session_service=session_service
    )
    stakeholders_agent_runner = Runner(
        agent=SubAgenteStakeholders_ADK,
        app_name=APP_NAME,
        session_service=session_service
    )
    maslow_agent_runner = Runner(
        agent=SubAgenteImpactoMaslow_ADK,
        app_name=APP_NAME,
        session_service=session_service
    )
    consolidator_agent_runner = Runner(
        agent=AgenteConsolidadorDeAnalise_ADK,
        app_name=APP_NAME,
        session_service=session_service
    )
    settings.logger.info(f"Runners para sub-agentes de análise e consolidador criados.")


    settings.logger.info("\n--- FASE 1: Buscar Artigos Pendentes ---")
    fetch_result = tool_fetch_pending_articles(limit=3) 
    if fetch_result.get("status") == "error":
        settings.logger.error(f"Falha ao buscar artigos pendentes: {fetch_result.get('message')}")
        return

    articles_to_analyze = fetch_result.get("articles_data", [])
    settings.logger.info(f"DEBUG_PIPELINE: tool_fetch_pending_articles retornou {len(articles_to_analyze)} artigos para processar.")

    if not articles_to_analyze:
        settings.logger.warning("Nenhum artigo pendente encontrado para análise LLM. Encerrando.")
        return

    settings.logger.info(f"Encontrados {len(articles_to_analyze)} artigos pendentes para análise LLM.")

    settings.logger.info("\n--- FASE 2: Delegar Análise LLM e Consolidar Resultados ---")
    
    analyzed_articles_count = 0 

    for article in articles_to_analyze:
        article_id = article.get("news_article_id")
        headline = article.get("headline", "Sem Título")
        content_for_llm = article.get("full_text") or article.get("summary") or article.get("headline")

        if not content_for_llm:
            settings.logger.warning(f"Artigo ID {article_id} não possui conteúdo para análise. Pulando.")
            continue

        settings.logger.info(f"  Processando Artigo ID {article_id}: '{headline[:50]}...'")
        
        consolidated_llm_results = {}
        suggested_article_type = None 

        llm_input_content = types.Content(role='user', parts=[types.Part(text=json.dumps({
            "news_article_id": article_id,
            "llm_analysis_json": consolidated_llm_results, # Será preenchido abaixo
            "suggested_article_type": suggested_article_type # Será preenchido abaixo
        }))])

        # --- Chamada ao SubAgenteSentimento_ADK ---
        settings.logger.info("    Chamando SubAgenteSentimento_ADK...")
        events_sentiment = sentiment_agent_runner.run_async(
            user_id=USER_ID, 
            session_id=SESSION_ID, 
            new_message=llm_input_content
        )
        sentiment_result = None
        async for event in events_sentiment:
            if event.is_final_response():
                if event.content and event.content.parts and event.content.parts[0].text:
                    try:
                        sentiment_result = json.loads(event.content.parts[0].text)
                        consolidated_llm_results["sentiment_analysis"] = sentiment_result
                        settings.logger.info(f"    Sentimento obtido: {sentiment_result.get('sentiment_petr4')}")
                    except json.JSONDecodeError as e:
                        settings.logger.error(f"    Erro ao parsear JSON de Sentimento para Artigo ID {article_id}: {e}. Conteúdo: {event.content.parts[0].text[:100]}...")
                break
        if not sentiment_result: settings.logger.error(f"    Falha ao obter resultado de sentimento para Artigo ID {article_id}.")

        # --- Chamada ao SubAgenteRelevanciaTipo_ADK ---
        settings.logger.info("    Chamando SubAgenteRelevanciaTipo_ADK...")
        events_relevance = relevance_type_agent_runner.run_async(
            user_id=USER_ID, 
            session_id=SESSION_ID, 
            new_message=llm_input_content
        )
        relevance_result = None
        async for event in events_relevance:
            if event.is_final_response():
                if event.content and event.content.parts and event.content.parts[0].text:
                    try:
                        relevance_result = json.loads(event.content.parts[0].text)
                        consolidated_llm_results["relevance_type_analysis"] = relevance_result
                        suggested_article_type = relevance_result.get("suggested_article_type")
                        settings.logger.info(f"    Relevância/Tipo obtido: {relevance_result.get('relevance_petr4')} / {suggested_article_type}")
                    except json.JSONDecodeError as e:
                        settings.logger.error(f"    Erro ao parsear JSON de Relevância/Tipo para Artigo ID {article_id}: {e}. Conteúdo: {event.content.parts[0].text[:100]}...")
                break
        if not relevance_result: settings.logger.error(f"    Falha ao obter resultado de relevância/tipo para Artigo ID {article_id}.")

        # --- Chamada ao SubAgenteStakeholders_ADK ---
        settings.logger.info("    Chamando SubAgenteStakeholders_ADK...")
        events_stakeholders = stakeholders_agent_runner.run_async(
            user_id=USER_ID, 
            session_id=SESSION_ID, 
            new_message=llm_input_content
        )
        stakeholders_result = None
        async for event in events_stakeholders:
            if event.is_final_response():
                if event.content and event.content.parts and event.content.parts[0].text:
                    try:
                        stakeholders_result = json.loads(event.content.parts[0].text)
                        consolidated_llm_results["stakeholders_analysis"] = stakeholders_result
                        settings.logger.info(f"    Stakeholders obtidos: {stakeholders_result.get('stakeholders')}")
                    except json.JSONDecodeError as e:
                        settings.logger.error(f"    Erro ao parsear JSON de Stakeholders para Artigo ID {article_id}: {e}. Conteúdo: {event.content.parts[0].text[:100]}...")
                break
        if not stakeholders_result: settings.logger.error(f"    Falha ao obter resultado de stakeholders para Artigo ID {article_id}.")

        # --- Chamada ao SubAgenteImpactoMaslow_ADK ---
        settings.logger.info("    Chamando SubAgenteImpactoMaslow_ADK...")
        events_maslow = maslow_agent_runner.run_async(
            user_id=USER_ID, 
            session_id=SESSION_ID, 
            new_message=llm_input_content
        )
        maslow_result = None
        async for event in events_maslow:
            if event.is_final_response():
                if event.content and event.content.parts and event.content.parts[0].text:
                    try:
                        maslow_result = json.loads(event.content.parts[0].text)
                        consolidated_llm_results["maslow_analysis"] = maslow_result
                        settings.logger.info(f"    Impacto Maslow obtido: {maslow_result.get('maslow_impact_primary')}")
                    except json.JSONDecodeError as e:
                        settings.logger.error(f"    Erro ao parsear JSON de Maslow para Artigo ID {article_id}: {e}. Conteúdo: {event.content.parts[0].text[:100]}...")
                break
        if not maslow_result: settings.logger.error(f"    Falha ao obter resultado de Maslow para Artigo ID {article_id}.")

        # --- Chamada ao AgenteConsolidadorDeAnalise_ADK para gerar JSON de parâmetros ---
        settings.logger.info("    Chamando AgenteConsolidadorDeAnalise_ADK para gerar JSON de parâmetros...")
        
        # Cria o payload de entrada para o consolidador com os resultados já obtidos
        consolidator_payload = {
            "news_article_id": article_id,
            "llm_analysis_json": consolidated_llm_results,
            "suggested_article_type": suggested_article_type
        }
        consolidator_input_content = types.Content(role='user', parts=[types.Part(text=json.dumps(consolidator_payload))])

        events_consolidator = consolidator_agent_runner.run_async(
            user_id=USER_ID,
            session_id=SESSION_ID,
            new_message=consolidator_input_content
        )
        
        consolidator_response_json = None
        async for event in events_consolidator:
            # O consolidador agora DEVE retornar APENAS um JSON na sua resposta final
            if event.is_final_response() and event.content and event.content.parts and event.content.parts[0].text:
                raw_json_text = event.content.parts[0].text.strip()
                # Tenta remover o bloco de código Markdown se presente
                match = re.search(r"```(?:json)?\s*\n(.*)\n```", raw_json_text, re.DOTALL)
                if match:
                    raw_json_text = match.group(1).strip()
                
                try:
                    consolidator_response_json = json.loads(raw_json_text)
                    settings.logger.info(f"    Consolidador gerou JSON de parâmetros: {consolidator_response_json}")
                except json.JSONDecodeError as e:
                    settings.logger.error(f"    Erro ao parsear JSON de parâmetros do Consolidador para Artigo ID {article_id}: {e}. Conteúdo: {raw_json_text[:100]}...")
                break # Sai do loop de eventos após obter a resposta final
        
        consolidator_result = {"status": "error", "message": "Consolidador não gerou JSON de parâmetros válido."}

        if consolidator_response_json:
            # Agora, CHAMA A FERRAMENTA REAL DE ATUALIZAÇÃO com os parâmetros obtidos do LLM
            try:
                # mock_tool_context para a chamada manual (pois não é chamada via runner)
                class TempToolContextForManualCall:
                    def __init__(self):
                        self.state = {}
                temp_tool_context = TempToolContextForManualCall()

                # A ferramenta tool_update_article_analysis espera news_article_id, llm_analysis_json, suggested_article_type
                # Estes já estão no consolidator_response_json
                manual_tool_call_result = tool_update_article_analysis(
                    news_article_id=consolidator_response_json.get('news_article_id'),
                    llm_analysis_json=consolidator_response_json.get('llm_analysis_json'),
                    suggested_article_type=consolidator_response_json.get('suggested_article_type'),
                    tool_context=temp_tool_context # Passa o contexto temporário
                )
                consolidator_result = manual_tool_call_result # Atribui o RESULTADO REAL da ferramenta
                settings.logger.info(f"    Chamada manual da ferramenta de persistência: {consolidator_result.get('message')}")

            except Exception as e:
                settings.logger.error(f"    Erro na chamada manual da ferramenta de persistência para Artigo ID {article_id}: {e}", exc_info=True)
                consolidator_result = {"status": "error", "message": f"Erro na chamada manual da ferramenta: {e}"}

        
        if not consolidator_result or consolidator_result.get("status") != "success":
            settings.logger.error(f"  Falha na consolidação/persistência para Artigo ID {article_id}. Resultado: {consolidator_result}")
        else:
            settings.logger.info(f"  Análise LLM COMPLETA e persistida para Artigo ID {article_id}!")
            analyzed_articles_count += 1 

    settings.logger.info(f"\n--- FASE 2 CONCLUÍDA: {analyzed_articles_count} artigos analisados e persistidos. ---") 
    settings.logger.info("\n--- TESTE DE INTEGRAÇÃO SIMULADO: Pipeline de Análise LLM CONCLUÍDO ---")


# --- Executar a função assíncrona ---
if __name__ == "__main__":
    try:
        asyncio.run(run_llm_analysis_pipeline())
    except RuntimeError as e:
        if "cannot run an event loop while another event loop is running" in str(e):
            settings.logger.warning("Detectado ambiente com loop de eventos já em execução (ex: Jupyter/Colab). Tentando executar com await.")
        else:
            raise e
    except Exception as e:
        settings.logger.critical(f"Erro fatal durante a execução do pipeline de análise LLM: {e}", exc_info=True)