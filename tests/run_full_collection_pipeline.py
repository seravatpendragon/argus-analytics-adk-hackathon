# run_full_collection_pipeline.py

import os
import sys
from pathlib import Path
import json
from datetime import datetime, timedelta
import math 
import asyncio 
import re 
import hashlib 
from typing import Dict, Any, Optional, List # Import para typing

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent 
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    print(f"PROJECT_ROOT ({PROJECT_ROOT}) foi adicionado/confirmado no sys.path para run_full_collection_pipeline.py.")
except NameError:
    PROJECT_ROOT = Path(os.getcwd())
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    print(f"AVISO (run_full_collection_pipeline.py): __file__ não definido. Usando PROJECT_ROOT como: {PROJECT_ROOT}")

src_path = PROJECT_ROOT / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
    print(f"src_path ({src_path}) foi adicionado/confirmado no sys.path.")

# --- Importações de Módulos ---
try:
    from config import settings
    
    # Importar o Agente Coletor de Dados (Agente LLM)
    from agents.agente_orquestrador_coleta_adk.agent import AgenteColetorDados_ADK
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types 

    # IMPORTAÇÕES DAS FERRAMENTAS REAIS DE COLETA (Para serem usadas no TOOL_FUNCTION_MAP)
    from agents.agente_coletor_newsapi_adk.tools.tool_collect_newsapi_articles import tool_collect_newsapi_articles
    from agents.agente_coletor_rss_adk.tools.tool_collect_rss_articles import tool_collect_rss_articles
    from agents.agente_coletor_regulatorios_adk.tools.ferramenta_downloader_cvm import tool_download_cvm_data
    from agents.agente_coletor_regulatorios_adk.tools.ferramenta_processador_ipe import tool_process_cvm_ipe_local

    # Ferramentas de pré-processamento e persistência (Python)
    from agents.agente_pre_processador_noticia_adk.tools.tool_preprocess_metadata import tool_preprocess_article_metadata
    from agents.agente_de_credibilidade_adk.tools.tool_get_source_credibility import tool_get_source_credibility
    from agents.agente_de_fonte_noticia_adk.tools.tool_ensure_news_source_in_db import tool_ensure_news_source_in_db
    from agents.agente_armazenador_artigo_adk.tools.tool_persist_data import tool_persist_news_or_cvm_document

    print("Módulos de todos os agentes e ferramentas importados com sucesso.")

except ImportError as e:
    if not hasattr(settings, 'logger'): 
        import logging
        log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        _fb_logger = logging.getLogger("full_pipeline_test_logger_fallback")
        settings = type('SettingsFallback', (), {'logger': _fb_logger})()

    settings.logger.critical(f"Erro CRÍTICO ao importar módulos em run_full_collection_pipeline.py: {e}", exc_info=True)
    settings.logger.error(f"Verifique se as pastas dos agentes e seus arquivos existem e estão acessíveis.")
    settings.logger.error(f"sys.path atual: {sys.path}")
    sys.exit(1)
except Exception as e:
    if not hasattr(settings, 'logger'): 
        import logging
        log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        _fb_logger = logging.getLogger("full_pipeline_test_logger_fallback2")
        settings = type('SettingsFallback', (), {'logger': _fb_logger})()

    settings.logger.critical(f"Erro INESPERADO durante imports iniciais em run_full_collection_pipeline.py: {e}", exc_info=True)
    sys.exit(1)

if not hasattr(settings, 'logger'):
    settings.logger = logging.getLogger("full_pipeline_test_logger")
    settings.logger.info("Logger fallback inicializado em run_full_collection_pipeline.py.")


settings.logger.info("--- INICIANDO TESTE DE INTEGRAÇÃO SIMULADO: Pipeline COMPLETO de Coleta e Processamento ---")

# --- Mapeamento GLOBAL de nomes de ferramentas para funções (para execução manual pelo orquestrador) ---
# Este mapa contém as *referências* às funções Python que o Agente Coletor *pode* pedir para executar.
# A chave é o nome que o LLM usará no tool_code, o valor é a função Python real.
TOOL_FUNCTION_MAP = {
    "tool_collect_newsapi_articles": tool_collect_newsapi_articles,
    "tool_collect_rss_articles": tool_collect_rss_articles,
    "tool_download_cvm_data": tool_download_cvm_data,
    "tool_process_cvm_ipe_local": tool_process_cvm_ipe_local,
}

# --- Mock ToolContext para simular o estado da sessão (para ferramentas Python) ---
class SimpleTestToolContext:
    """A simple mock class for tool_context to simulate session state."""
    def __init__(self):
        self.state = {} # Simulates the session state dictionary

mock_session_state_context = SimpleTestToolContext() 
settings.logger.info(f"MockToolContext para estado da sessão inicializado. Estado: {mock_session_state_context.state}")


# --- FUNÇÃO AUXILIAR PARA EXECUTAR O PIPELINE DE PROCESSAMENTO PARA UM ÚNICO ITEM ---
def run_processing_pipeline_for_item(item_data: Dict[str, Any], item_type: str):
    """
    Executa o pipeline de pré-processamento e persistência para um único item coletado.
    """
    item_title = item_data.get('title')
    item_headline = item_data.get('headline')

    if isinstance(item_title, float) and math.isnan(item_title):
        item_title = None
    if isinstance(item_headline, float) and math.isnan(item_headline):
        item_headline = None

    display_title = item_title or item_headline or 'Sem Título'
    settings.logger.info(f"\n--- Processando {item_type}: {str(display_title)[:70]}... ---")

    # 1. Pré-processamento de metadados
    settings.logger.info("  Chamando tool_preprocess_article_metadata...")
    processed_data_result = tool_preprocess_article_metadata(raw_article_data=item_data)
    if processed_data_result.get("status") == "error":
        settings.logger.error(f"  Pré-processamento falhou: {processed_data_result.get('message')}")
        return

    # 2. Obtenção de Credibilidade da Fonte
    settings.logger.info("  Chamando tool_get_source_credibility...")
    credibility_data_result = tool_get_source_credibility(
        source_domain=processed_data_result.get("source_domain"),
        source_name_raw=processed_data_result.get("source_name_raw")
    )
    if not credibility_data_result or not credibility_data_result.get("source_name_curated") or credibility_data_result.get("base_credibility_score") is None: 
        settings.logger.error(f"  Obtenção de credibilidade falhou ou retornou dados incompletos para {processed_data_result.get('source_name_raw')}.")
        return
    
    # 3. Garantir NewsSource no DB
    settings.logger.info("  Chamando tool_ensure_news_source_in_db...")
    source_db_data_result = tool_ensure_news_source_in_db(
        source_name_curated=credibility_data_result.get("source_name_curated"),
        source_domain=credibility_data_result.get("source_domain"),
        base_credibility_score=credibility_data_result.get("base_credibility_score"),
        loaded_credibility_data=credibility_data_result.get("loaded_credibility_data"), 
        tool_context=mock_session_state_context
    )
    if source_db_data_result.get("status") == "error":
        settings.logger.error(f"  Garantia de NewsSource no DB falhou: {source_db_data_result.get('message')}")
        return

    # 4. Persistência Final do Artigo/Documento no DB
    settings.logger.info("  Chamando tool_persist_news_or_cvm_document...")
    final_article_data = processed_data_result.copy()
    final_article_data["news_source_id"] = source_db_data_result.get("news_source_id")
    final_article_data.pop("status", None) 
    final_article_data.pop("message", None)
    
    final_article_data['processing_status'] = 'pending_llm_analysis'

    persist_result = tool_persist_news_or_cvm_document(
        article_data=final_article_data,
        tool_context=mock_session_state_context 
    )

    if persist_result.get("status") == "success":
        settings.logger.info(f"  Item persistido com sucesso! ID: {persist_result.get('news_article_id')}")
    else:
        settings.logger.error(f"  Persistência falhou: {persist_result.get('message')}")


# --- FUNÇÃO PRINCIPAL PARA EXECUTAR O PIPELINE COMPLETO ---
async def run_full_collection_pipeline_async():
    settings.logger.info("\n--- FASE 1: Coletando Dados Brutos de Múltiplas Fontes (via Agente Coletor) ---")
    
    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name="argus_collector", user_id="collector_user", session_id="collector_session_001")
    
    collector_agent_runner = Runner(
        agent=AgenteColetorDados_ADK,
        app_name="argus_collector",
        session_service=session_service
    )

    initial_collection_prompt = types.Content(role='user', parts=[types.Part(text="Inicie a coleta de todos os dados financeiros recentes.")])
    
    settings.logger.info("  Invocando AgenteColetorDados_ADK para coletar dados...")
    all_raw_articles = []
    
    events = collector_agent_runner.run_async(
        user_id="collector_user",
        session_id="collector_session_001",
        new_message=initial_collection_prompt
    )

    async for event in events:
        # Primeiro, trate as tool_responses que já vêm executadas (se o Runner funcionar assim)
        if hasattr(event, 'tool_response') and event.tool_response:
            tool_result = event.tool_response.response
            if tool_result.get("status") == "success":
                if "articles_data" in tool_result:
                    all_raw_articles.extend(tool_result["articles_data"])
                    settings.logger.info(f"  Adicionados {len(tool_result['articles_data'])} artigos via {event.tool_response.name}.")
                elif "novos_documentos" in tool_result:
                    all_raw_articles.extend(tool_result["novos_documentos"]) 
                    settings.logger.info(f"  Adicionados {len(tool_result['novos_documentos'])} documentos via {event.tool_response.name}.")
            else:
                settings.logger.error(f"  Ferramenta de coleta {event.tool_response.name} falhou: {tool_result.get('message')}")
        
        # Em seguida, se o Runner retornou tool_code (e não executou), execute manualmente
        elif hasattr(event, 'tool_code') and event.tool_code:
            settings.logger.warning(f"  Agente Coletor gerou tool_code: {event.tool_code[:100]}... Executando manualmente.")
            
            tool_call_str = event.tool_code
            match = re.match(r"(\w+)\((.*)\)", tool_call_str)
            if match:
                tool_name = match.group(1)
                tool_args_str = match.group(2)
                
                tool_kwargs = {}
                # Parse the arguments string using eval (with caution)
                if tool_args_str.strip(): 
                    try:
                        tool_kwargs = eval(f"dict({tool_args_str})", {}, {}) 
                    except Exception as e_eval:
                        settings.logger.error(f"    Erro eval() ao parsear args de '{tool_name}': {e_eval}. Args string: '{tool_args_str[:100]}'")
                        tool_kwargs = {} 
                
                if tool_name in TOOL_FUNCTION_MAP:
                    try:
                        mock_context = SimpleTestToolContext() 
                        executed_tool_result = TOOL_FUNCTION_MAP[tool_name](**tool_kwargs, tool_context=mock_context)
                        
                        if executed_tool_result.get("status") == "success":
                            if "articles_data" in executed_tool_result:
                                all_raw_articles.extend(executed_tool_result["articles_data"])
                                settings.logger.info(f"  Adicionados {len(executed_tool_result['articles_data'])} artigos via {tool_name} (execução manual).")
                            elif "novos_documentos" in executed_tool_result:
                                all_raw_articles.extend(executed_tool_result["novos_documentos"])
                                settings.logger.info(f"  Adicionados {len(executed_tool_result['novos_documentos'])} documentos via {tool_name} (execução manual).")
                        else:
                            settings.logger.error(f"  Ferramenta {tool_name} (execução manual) falhou: {executed_tool_result.get('message')}")

                    except Exception as e_execute:
                        settings.logger.error(f"    Erro ao executar ferramenta {tool_name} manualmente: {e_execute}", exc_info=True)
                else:
                    settings.logger.error(f"    Ferramenta '{tool_name}' não mapeada para execução manual.")
            else:
                settings.logger.error(f"  Não foi possível parsear tool_code: '{tool_call_str[:100]}'")

        elif event.is_final_response():
            settings.logger.info(f"  Agente Coletor finalizou com resposta: {event.content.parts[0].text[:100]}...")
        
    settings.logger.info(f"\nTotal de itens coletados pelo Agente Coletor no teste: {len(all_raw_articles)}")


    settings.logger.info("\n--- FASE 2: Iniciando Processamento e Persistência dos Dados Coletados ---")

    if not all_raw_articles:
        settings.logger.warning("Nenhum artigo/documento bruto coletado para processar. Encerrando pipeline.")
    else:
        # ATENÇÃO: test_run_identifier é usado para MOCKS.
        # Para garantir que os links mockados sejam determinísticos entre execuções,
        # e assim o UPSERT funcione para mocks, use um hash do conteúdo.
        # A lógica de geração de URL determinística já está no ferramenta_processador_ipe.py
        # e no run_full_collection_pipeline (para mocks NewsAPI/RSS).
        
        # Este loop é essencial para garantir que cada item_data passado para o
        # run_processing_pipeline_for_item tenha uma chave de link determinística.
        
        for idx, item in enumerate(all_raw_articles):
            # A lógica para gerar URLs determinísticas para MOCKS já está
            # no run_full_collection_pipeline (no loop async for event in events:).
            # No entanto, se o item já vem com uma URL determinística (CVM com protocolo_id),
            # não precisamos modificar aqui.
            
            # Garante que o item_data que será passado para run_processing_pipeline_for_item
            # tenha a chave 'article_link' preenchida com a URL a ser usada no UPSERT.
            if item.get("source_type") == "NewsAPI":
                # Prefere 'url' se disponível, senão tenta criar uma hash
                if item.get("url"):
                    item["article_link"] = item["url"]
                else:
                    content_hash = hashlib.md5(item.get("title", "").encode('utf-8') + item.get("description", "").encode('utf-8')).hexdigest()
                    item["article_link"] = f"http://mock.com/newsapi/article_{content_hash}"
                    settings.logger.warning(f"  NewsAPI mock sem URL, gerado link determinístico: {item['article_link']}")
            elif item.get("source_type") == "RSS":
                if item.get("link"):
                    item["article_link"] = item["link"]
                else:
                    content_hash = hashlib.md5(item.get("title", "").encode('utf-8') + item.get("summary", "").encode('utf-8')).hexdigest()
                    item["article_link"] = f"http://mock.com/rss_feed/article_{content_hash}"
                    settings.logger.warning(f"  RSS mock sem Link, gerado link determinístico: {item['article_link']}")
            elif item.get("source_type") == "CVM_IPE":
                # Para CVM, a ferramenta processadora_ipe já deveria ter preenchido 'document_url'
                # e 'protocol_id'. A 'article_link' aqui vai ser o 'document_url' da ferramenta processadora.
                item["article_link"] = item.get("document_url")
                # Se ainda estiver None, isso é um erro na ferramenta processadora_ipe
                if not item["article_link"]:
                     settings.logger.error(f"  CVM_IPE mock sem document_url válido. Persistência pode falhar para: {item.get('title')}")
                     # Fallback de último recurso (pode causar duplicação se o hash do item for igual)
                     item["article_link"] = f"urn:cvm:doc_hash_fallback:{hashlib.md5(str(item.get('title', '')).encode('utf-8') + str(item.get('protocol_id', '')).encode('utf-8')).hexdigest()}"


        for idx, item_data in enumerate(all_raw_articles):
            run_processing_pipeline_for_item(item_data, f"Item {idx+1}/{len(all_raw_articles)}")

    settings.logger.info("\n--- TESTE DE INTEGRAÇÃO SIMULADO: Pipeline COMPLETO de Coleta e Processamento CONCLUÍDO ---")


# --- Executar a função assíncrona ---
if __name__ == "__main__":
    try:
        asyncio.run(run_full_collection_pipeline_async())
    except RuntimeError as e:
        if "cannot run an event loop while another event loop is running" in str(e):
            settings.logger.warning("Detectado ambiente com loop de eventos já em execução (ex: Jupyter/Colab). Tentando executar com await.")
        else:
            raise e
    except Exception as e:
        settings.logger.critical(f"Erro fatal durante a execução do pipeline de coleta: {e}", exc_info=True)

