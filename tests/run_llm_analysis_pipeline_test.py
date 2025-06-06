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

    src_path = PROJECT_ROOT / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    print(f"src_path ({src_path}) foi adicionado/confirmado no sys.path.")

except Exception as e:
    import logging
    log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
    logging.basicConfig(level=logging.ERROR, format=log_format)
    logging.error(f"Erro na configuração inicial do sys.path em run_llm_analysis_pipeline_test.py: {e}")
    sys.exit(1)

# --- Importações de Módulos ---
try:
    from config import settings
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types 
    
    from agents.agente_gerenciador_analise_llm_adk.tools.tool_fetch_pending_articles import tool_fetch_pending_articles
    from agents.sub_agente_identificador_entidade_adk.tools.tool_identify_entity_ticker import tool_identify_entity_ticker
    from agents.agente_consolidador_analise_adk.tools.tool_update_article_analysis import tool_update_article_analysis

    from agents.sub_agente_identificador_entidade_adk.agent import SubAgenteIdentificadorDeEntidade_ADK
    from agents.sub_agente_sentimento_adk.agent import SubAgenteSentimento_ADK
    from agents.sub_agente_relevancia_tipo_adk.agent import SubAgenteRelevanciaTipo_ADK
    from agents.sub_agente_stakeholders_adk.agent import SubAgenteStakeholders_ADK
    from agents.sub_agente_impacto_maslow_adk.agent import SubAgenteImpactoMaslow_ADK
    from agents.sub_agente_resumo_adk.agent import SubAgenteResumo_ADK 
    from agents.sub_agente_temas_palavras_chave_adk.agent import SubAgenteTemasPalavrasChave_ADK 
    from agents.agente_consolidador_analise_adk.agent import AgenteConsolidadorDeAnalise_ADK 

    print("Módulos de agentes e ferramentas importados com sucesso.")

except ImportError as e:
    if not hasattr(settings, 'logger'): 
        import logging
        log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        settings.logger = logging.getLogger("llm_analysis_test_logger_fallback")
        settings.logger.info("Logger fallback inicializado devido a ImportError.")

    settings.logger.critical(f"Erro CRÍTICO ao importar módulos em run_llm_analysis_pipeline_test.py: {e}", exc_info=True)
    settings.logger.error(f"Verifique si as pastas dos agentes e seus arquivos existem e estão acessíveis.")
    settings.logger.error(f"sys.path atual: {sys.path}")
    sys.exit(1)
except Exception as e:
    if not hasattr(settings, 'logger'): 
        import logging
        log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        settings.logger = logging.getLogger("llm_analysis_test_logger_fallback2")
        settings.logger.info("Logger fallback inicializado devido a erro inesperado.")

    settings.logger.critical(f"Erro INESPERADO durante imports iniciais em run_llm_analysis_pipeline_test.py: {e}", exc_info=True)
    sys.exit(1)

if not hasattr(settings, 'logger'):
    settings.logger = logging.getLogger("llm_analysis_test_logger")
    settings.logger.info("Logger inicializado via getLogger em run_llm_analysis_pipeline_test.py.")


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

# --- Helper function to parse JSON from LLM responses ---
def parse_llm_json_response(raw_text_content, article_id, agent_name):
    """
    Parses a JSON string from an LLM response, handling markdown code blocks and aggressively stripping whitespace.
    Returns the parsed JSON dict or None if parsing fails.
    """
    # Remove BOM if present (common issue with some text encodings, especially in Windows)
    json_str_content = raw_text_content.replace('\ufeff', '').strip()
    
    # Tenta extrair o conteúdo do bloco de código Markdown primeiro
    # Regex mais robusta: ```(optional json) <any whitespace> <capture this content> <any whitespace> ```
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", json_str_content, re.DOTALL)
    if match:
        json_str_content = match.group(1).strip()
    
    # Remove qualquer whitespace/newline remanescente que não seja JSON válido do início/fim
    json_str_content = json_str_content.strip()

    # Tenta encontrar o conteúdo JSON procurando o primeiro '{' ou '[' e o último '}'.
    # Isso é a forma mais robusta de isolar o JSON válido, ignorando lixo antes/depois.
    first_brace = -1
    for i, char in enumerate(json_str_content):
        if char == '{' or char == '[':
            first_brace = i
            break
    
    last_brace = -1
    for i, char in enumerate(reversed(json_str_content)):
        if char == '}' or char == ']':
            last_brace = len(json_str_content) - 1 - i
            break

    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        json_str_content = json_str_content[first_brace : last_brace + 1]
    else:
        # Se não achou chaves após todas as tentativas (ou a extração foi inválida),
        # significa que a string gerada não parece conter um JSON válido.
        # Nesses casos, a string já está o mais limpa possível da tentativa do regex/strip.
        pass 
    
    # Final strip (redundante, mas seguro)
    json_str_content = json_str_content.strip()

    # settings.logger.debug(f"    DEBUG PARSER: Conteúdo FINAL a ser parseado para {agent_name} (ID {article_id}): '{json_str_content[:200]}'")
    # settings.logger.debug(f"    DEBUG PARSER: Conteúdo RAW (repr) para {agent_name} (ID {article_id}): {repr(json_str_content[:200])}")

    if not json_str_content:
        settings.logger.error(f"    Erro: Resposta vazia ou sem JSON válido do agente {agent_name} para Artigo ID {article_id}.")
        return None
        
    try:
        parsed_json = json.loads(json_str_content)
        return parsed_json
    except json.JSONDecodeError as e:
        settings.logger.error(f"    Erro ao parsear JSON de {agent_name} para Artigo ID {article_id}: {e}. Conteúdo: '{json_str_content[:100]}...'")
        return None


async def run_llm_analysis_pipeline():
    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID)
    settings.logger.info(f"ADK Session criada: App='{APP_NAME}', User='{USER_ID}', Session='{SESSION_ID}'")

    # Instanciar os Runners para cada sub-agente de análise e para o Consolidador
    entity_identifier_agent_runner = Runner(
        agent=SubAgenteIdentificadorDeEntidade_ADK,
        app_name=APP_NAME,
        session_service=session_service
    )
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
    resumo_agent_runner = Runner( 
        agent=SubAgenteResumo_ADK,
        app_name=APP_NAME,
        session_service=session_service
    )
    temas_palavras_chave_agent_runner = Runner( 
        agent=SubAgenteTemasPalavrasChave_ADK,
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
        content_for_llm_raw = article.get("full_text") or article.get("summary") or article.get("headline")

        if not content_for_llm_raw:
            settings.logger.warning(f"Artigo ID {article_id} não possui conteúdo para análise. Pulando.")
            continue

        settings.logger.info(f"  Processando Artigo ID {article_id}: '{headline[:50]}...'")
        
        consolidated_llm_results = {}
        suggested_article_type = None 
        
        # --- Chamada ao SubAgenteIdentificadorDeEntidade_ADK ---
        settings.logger.info("    Chamando SubAgenteIdentificadorDeEntidade_ADK...")
        entity_input_content = types.Content(role='user', parts=[types.Part(text=content_for_llm_raw)])
        events_entity_id = entity_identifier_agent_runner.run_async(
            user_id=USER_ID,
            session_id=SESSION_ID,
            new_message=entity_input_content
        )
        entity_identification_result = None
        async for event in events_entity_id:
            if event.is_final_response():
                if event.content and event.content.parts and event.content.parts[0].text:
                    entity_identification_result = parse_llm_json_response(
                        event.content.parts[0].text, article_id, "Identificador de Entidade"
                    )
                    if entity_identification_result: 
                        class TempToolContextForToolCall: 
                            def __init__(self):
                                self.state = {}
                        temp_tool_context_for_tool_call = TempToolContextForToolCall()

                        standardized_id_result = tool_identify_entity_ticker(
                            entity_name_raw=entity_identification_result.get('nome_entidade_foco'),
                            entity_type=entity_identification_result.get('tipo_entidade_foco'),
                            tool_context=temp_tool_context_for_tool_call 
                        )
                        if standardized_id_result.get("status") == "success":
                            entity_identification_result['ticker_padronizado'] = standardized_id_result.get('padronizado_identificador')
                            settings.logger.info(f"    Ticker/Identificador padronizado para: {entity_identification_result['ticker_padronizado']}")
                        else:
                            settings.logger.warning(f"    Falha ao padronizar ticker: {standardized_id_result.get('message')}. Usando sugerido.")
                        
                        consolidated_llm_results["entity_identification"] = entity_identification_result
                break
        if not entity_identification_result: 
            settings.logger.error(f"    Falha ao obter identificação de entidade para Artigo ID {article_id}. Pulando análises dependentes.")
            continue 

        # Preparar o prefixo de contexto para os sub-agentes
        context_prefix = ""
        if entity_identification_result.get('tipo_entidade_foco'):
            context_prefix += f"A notícia é predominantemente sobre: {entity_identification_result['tipo_entidade_foco']}. "
        if entity_identification_result.get('nome_entidade_foco'):
            context_prefix += f"A entidade/tema principal é '{entity_identification_result['nome_entidade_foco']}'. "
        if entity_identification_result.get('ticker_padronizado'):
            context_prefix += f"O identificador padronizado é '{entity_identification_result['ticker_padronizado']}'. "
        
        llm_input_text_for_sub_agents = f"Contexto da Notícia: {context_prefix}\n\nTexto Original para Análise:\n{content_for_llm_raw}"
        
        llm_input_content_for_sub_agents = types.Content(
            role='user', 
            parts=[types.Part(text=llm_input_text_for_sub_agents)]
        )

        # --- Chamada ao SubAgenteSentimento_ADK ---
        settings.logger.info("    Chamando SubAgenteSentimento_ADK...")
        events_sentiment = sentiment_agent_runner.run_async(
            user_id=USER_ID, 
            session_id=SESSION_ID, 
            new_message=llm_input_content_for_sub_agents 
        )
        sentiment_result = None
        async for event in events_sentiment:
            if event.is_final_response():
                if event.content and event.content.parts and event.content.parts[0].text:
                    sentiment_result = parse_llm_json_response(
                        event.content.parts[0].text, article_id, "Sentimento"
                    )
                    if sentiment_result: 
                        consolidated_llm_results["sentiment_analysis"] = sentiment_result
                        # Acesso seguro ao campo, em caso de `None` de `get()`
                        sentiment_status = sentiment_result.get('sentimento_central_percebido', 'N/A')
                        settings.logger.info(f"    Sentimento obtido: {sentiment_status}") 
                break
        if not sentiment_result: settings.logger.error(f"    Falha ao obter resultado de sentimento para Artigo ID {article_id}.")

        # --- Chamada ao SubAgenteRelevanciaTipo_ADK ---
        settings.logger.info("    Chamando SubAgenteRelevanciaTipo_ADK...")
        events_relevance = relevance_type_agent_runner.run_async(
            user_id=USER_ID, 
            session_id=SESSION_ID, 
            new_message=llm_input_content_for_sub_agents 
        )
        relevance_result = None
        async for event in events_relevance:
            if event.is_final_response():
                if event.content and event.content.parts and event.content.parts[0].text:
                    relevance_result = parse_llm_json_response(
                        event.content.parts[0].text, article_id, "Relevância/Tipo"
                    )
                    if relevance_result:
                        consolidated_llm_results["relevance_type_analysis"] = relevance_result
                        suggested_article_type = relevance_result.get('suggested_article_type', 'N/A')
                        relevance_score_fac_ia = relevance_result.get('score_relevancia_noticia_fac_ia', 'N/A')
                        settings.logger.info(f"    Relevância/Tipo obtido: {relevance_score_fac_ia} / {suggested_article_type}") 
                break
        if not relevance_result: settings.logger.error(f"    Falha ao obter resultado de relevância/tipo para Artigo ID {article_id}.")

        # --- Chamada ao SubAgenteStakeholders_ADK ---
        settings.logger.info("    Chamando SubAgenteStakeholders_ADK...")
        events_stakeholders = stakeholders_agent_runner.run_async(
            user_id=USER_ID, 
            session_id=SESSION_ID, 
            new_message=llm_input_content_for_sub_agents 
        )
        stakeholders_result = None
        async for event in events_stakeholders:
            if event.is_final_response():
                if event.content and event.content.parts and event.content.parts[0].text:
                    stakeholders_result = parse_llm_json_response(
                        event.content.parts[0].text, article_id, "Stakeholders"
                    )
                    if stakeholders_result:
                        consolidated_llm_results["stakeholders_analysis"] = stakeholders_result
                        stakeholder_primary = stakeholders_result.get('stakeholder_primario_afetado', 'N/A')
                        settings.logger.info(f"    Stakeholders obtidos: {stakeholder_primary}") 
                break
        if not stakeholders_result: settings.logger.error(f"    Falha ao obter resultado de stakeholders para Artigo ID {article_id}.")

        # --- Chamada ao SubAgenteImpactoMaslow_ADK ---
        settings.logger.info("    Chamando SubAgenteImpactoMaslow_ADK...")
        events_maslow = maslow_agent_runner.run_async(
            user_id=USER_ID, 
            session_id=SESSION_ID, 
            new_message=llm_input_content_for_sub_agents 
        )
        maslow_result = None
        async for event in events_maslow:
            if event.is_final_response():
                if event.content and event.content.parts and event.content.parts[0].text:
                    maslow_result = parse_llm_json_response(
                        event.content.parts[0].text, article_id, "Impacto Maslow"
                    )
                    if maslow_result:
                        consolidated_llm_results["maslow_analysis"] = maslow_result
                        maslow_scores_log = maslow_result.get('maslow_impact_scores', 'N/A')
                        settings.logger.info(f"    Impacto Maslow obtido: {maslow_scores_log}") 
                break
        if not maslow_result: settings.logger.error(f"    Falha ao obter resultado de Maslow para Artigo ID {article_id}.")

        # --- Chamada ao SubAgenteTemasPalavrasChave_ADK ---
        settings.logger.info("    Chamando SubAgenteTemasPalavrasChave_ADK...")
        events_temas_palavras_chave = temas_palavras_chave_agent_runner.run_async(
            user_id=USER_ID, 
            session_id=SESSION_ID, 
            new_message=llm_input_content_for_sub_agents 
        )
        temas_palavras_chave_result = None
        async for event in events_temas_palavras_chave:
            if event.is_final_response():
                if event.content and event.content.parts and event.content.parts[0].text:
                    temas_palavras_chave_result = parse_llm_json_response(
                        event.content.parts[0].text, article_id, "Temas/Palavras-Chave"
                    )
                    if temas_palavras_chave_result:
                        consolidated_llm_results["temas_palavras_chave"] = temas_palavras_chave_result
                        temas_list = temas_palavras_chave_result.get('principais_temas_abordados', 'N/A')
                        settings.logger.info(f"    Temas/Palavras-Chave obtidos: {temas_list}") 
                break
        if not temas_palavras_chave_result: settings.logger.error(f"    Falha ao obter resultado de Temas/Palavras-Chave para Artigo ID {article_id}.")

        # --- Chamada ao SubAgenteResumo_ADK ---
        settings.logger.info("    Chamando SubAgenteResumo_ADK...")
        events_resumo = resumo_agent_runner.run_async(
            user_id=USER_ID, 
            session_id=SESSION_ID, 
            new_message=llm_input_content_for_sub_agents 
        )
        resumo_result = None
        async for event in events_resumo:
            if event.is_final_response():
                if event.content and event.content.parts and event.content.parts[0].text:
                    resumo_result = parse_llm_json_response(
                        event.content.parts[0].text, article_id, "Resumo"
                    )
                    if resumo_result:
                        consolidated_llm_results["resumo_llm"] = resumo_result 
                        resumo_text = resumo_result.get('resumo_estruturado', 'N/A')
                        settings.logger.info(f"    Resumo LLM obtido: {resumo_text[:50]}...") 
                break
        if not resumo_result: settings.logger.error(f"    Falha ao obter resultado de Resumo para Artigo ID {article_id}.")


        # --- Chamada ao AgenteConsolidadorDeAnalise_ADK para gerar JSON de parâmetros ---
        settings.logger.info("    Chamando AgenteConsolidadorDeAnalise_ADK para gerar JSON de parâmetros...")
        
        if not consolidated_llm_results: 
            settings.logger.warning(f"    consolidated_llm_results vazio para Artigo ID {article_id}. Consolidador pode não ter dados para processar.")
            consolidated_llm_results = {} 

        consolidator_payload = {
            "news_article_id": article_id,
            "llm_analysis_json": consolidated_llm_results,
            "suggested_article_type": suggested_article_type # Use o que foi definido ou None
        }
        consolidator_input_content = types.Content(role='user', parts=[types.Part(text=json.dumps(consolidator_payload))])

        events_consoli = consolidator_agent_runner.run_async(
            user_id=USER_ID,
            session_id=SESSION_ID,
            new_message=consolidator_input_content
        )
        
        consolidator_params_json = None
        async for event in events_consoli:
            if event.is_final_response():
                if event.content and event.content.parts and event.content.parts[0].text:
                    consolidator_params_json = parse_llm_json_response(
                        event.content.parts[0].text, article_id, "Consolidador"
                    )
                break
        
        consolidator_final_status = {"status": "error", "message": "Consolidador não gerou JSON de parâmetros válido."}

        # Só tenta atualizar o banco de dados se houver resultados de análise E parâmetros válidos do consolidador
        # E se o llm_analysis_json dentro do consolidador_params_json não for None/vazio
        if consolidated_llm_results and consolidator_params_json and consolidator_params_json.get('llm_analysis_json'): 
            try:
                class TempToolContextForManualCall:
                    def __init__(self):
                        self.state = {}
                temp_tool_context = TempToolContextForManualCall()

                manual_tool_call_result = tool_update_article_analysis(
                    news_article_id=consolidator_params_json.get('news_article_id'),
                    llm_analysis_json=consolidator_params_json.get('llm_analysis_json'),
                    suggested_article_type=consolidator_params_json.get('suggested_article_type'),
                    tool_context=temp_tool_context 
                )
                consolidator_final_status = manual_tool_call_result 
                settings.logger.info(f"    Chamada manual da ferramenta de persistência: {consolidator_final_status.get('message')}")

            except Exception as e:
                settings.logger.error(f"    Erro na chamada manual da ferramenta de persistência para Artigo ID {article_id}: {e}", exc_info=True)
                consolidator_final_status = {"status": "error", "message": f"Erro na chamada manual da ferramenta: {e}"}

        
        if not consolidator_final_status or consolidator_final_status.get("status") != "success":
            settings.logger.error(f"  Falha na consolidação/persistência para Artigo ID {article_id}. Resultado: {consolidator_final_status}")
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
