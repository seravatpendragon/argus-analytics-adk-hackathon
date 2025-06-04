# run_llm_analysis_pipeline_test.py

import os
import sys
from pathlib import Path
import json
from datetime import datetime
import asyncio # Necessário para rodar funções assíncronas do ADK

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent # Sobe 1 nível do diretório 'tests'
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
    from google.genai import types # Para criar Content para o LLM
    
    # Importa a ferramenta de busca de artigos pendentes
    from agents.agente_gerenciador_analise_llm_adk.tools.tool_fetch_pending_articles import tool_fetch_pending_articles

    # Importa os agentes (o gerenciador e o sub-agente)
    from agents.agente_gerenciador_analise_llm_adk.agent import AgenteGerenciadorDeAnaliseLLM_ADK
    from agents.sub_agente_sentimento_adk.agent import SubAgenteSentimento_ADK

    print("Módulos de agentes e ferramentas importados com sucesso.")

except ImportError as e:
    if 'settings' not in locals() and 'settings' not in globals():
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
    if 'settings' not in locals() and 'settings' not in globals():
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

    sentiment_agent_runner = Runner(
        agent=SubAgenteSentimento_ADK,
        app_name=APP_NAME,
        session_service=session_service
    )
    settings.logger.info(f"Runner para SubAgenteSentimento_ADK criado.")


    settings.logger.info("\n--- FASE 1: Buscar Artigos Pendentes ---")
    fetch_result = tool_fetch_pending_articles(limit=3)
    if fetch_result.get("status") == "error":
        settings.logger.error(f"Falha ao buscar artigos pendentes: {fetch_result.get('message')}")
        return

    articles_to_analyze = fetch_result.get("articles_data", [])
    if not articles_to_analyze:
        settings.logger.warning("Nenhum artigo pendente encontrado para análise LLM. Encerrando.")
        return

    settings.logger.info(f"Encontrados {len(articles_to_analyze)} artigos pendentes para análise LLM.")

    settings.logger.info("\n--- FASE 2: Delegar Análise de Sentimento ---")
    for article in articles_to_analyze:
        article_id = article.get("news_article_id")
        headline = article.get("headline", "Sem Título")
        content_for_llm = article.get("full_text") or article.get("summary") or article.get("headline")

        if not content_for_llm:
            settings.logger.warning(f"Artigo ID {article_id} não possui conteúdo para análise. Pulando.")
            continue

        settings.logger.info(f"  Analisando sentimento para Artigo ID {article_id}: '{headline[:50]}...'")
        
        llm_input_content = types.Content(role='user', parts=[types.Part(text=content_for_llm)])

        events = sentiment_agent_runner.run_async(
            user_id=USER_ID, 
            session_id=SESSION_ID, 
            new_message=llm_input_content
        )

        final_sentiment_result = None
        async for event in events:
            if event.is_final_response():
                # CORREÇÃO CRÍTICA AQUI: Capturar o texto da resposta e parsear como JSON
                if event.content and event.content.parts and event.content.parts[0].text:
                    try:
                        final_sentiment_result = json.loads(event.content.parts[0].text)
                    except json.JSONDecodeError as e:
                        settings.logger.error(f"  Erro ao parsear JSON do LLM para Artigo ID {article_id}: {e}. Conteúdo: {event.content.parts[0].text[:100]}...")
                        final_sentiment_result = None # Garante que o resultado seja None em caso de erro de parsing
                break # Sai do loop de eventos após a resposta final
        
        if final_sentiment_result:
            settings.logger.info(f"  Resultado Sentimento para Artigo ID {article_id}: {json.dumps(final_sentiment_result, indent=2, ensure_ascii=False)}")
            # Em um cenário real, aqui você chamaria o AgenteConsolidadorDeAnalise_ADK
            # para salvar este resultado no DB.
        else:
            settings.logger.error(f"  Falha ao obter resultado de sentimento para Artigo ID {article_id}.")

    settings.logger.info("\n--- FASE 2 CONCLUÍDA: Análise de Sentimento simulada para artigos. ---")

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