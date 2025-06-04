# run_processing_pipeline_test.py

import os
import sys
from pathlib import Path
import json
from datetime import datetime
from typing import Any, Dict

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent 
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    print(f"PROJECT_ROOT ({PROJECT_ROOT}) foi adicionado/confirmado no sys.path para run_processing_pipeline_test.py.")
except NameError:
    PROJECT_ROOT = Path(os.getcwd())
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    print(f"AVISO (run_processing_pipeline_test.py): __file__ não definido. Usando PROJECT_ROOT como: {PROJECT_ROOT}")

src_path = PROJECT_ROOT / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
    print(f"src_path ({src_path}) foi adicionado/confirmado no sys.path.")

try:
    from config import settings
    
    from agents.agente_pre_processador_noticia_adk.tools.tool_preprocess_metadata import tool_preprocess_article_metadata
    from agents.agente_de_credibilidade_adk.tools.tool_get_source_credibility import tool_get_source_credibility
    from agents.agente_de_fonte_noticia_adk.tools.tool_ensure_news_source_in_db import tool_ensure_news_source_in_db
    from agents.agente_armazenador_artigo_adk.tools.tool_persist_data import tool_persist_news_or_cvm_document

    try:
        from google.adk.tools.tool_context import ToolContext
    except ImportError:
        class ToolContext:
            def __init__(self):
                self.state = {}
            pass

    print("Módulos de agentes de processamento e ferramentas importados com sucesso.")

except ImportError as e:
    if 'settings' not in locals() and 'settings' not in globals():
        import logging
        log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        _fb_logger = logging.getLogger("processing_pipeline_test_logger_fallback")
        settings = type('SettingsFallback', (), {'logger': _fb_logger})()
    settings.logger.error(f"Erro CRÍTICO ao importar módulos em run_processing_pipeline_test.py: {e}")
    settings.logger.error(f"Verifique se as pastas dos agentes e seus arquivos existem e estão acessíveis.")
    settings.logger.error(f"sys.path atual: {sys.path}")
    sys.exit(1)
except Exception as e:
    if 'settings' not in locals() and 'settings' not in globals():
        import logging
        log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        _fb_logger = logging.getLogger("processing_pipeline_test_logger_fallback2")
        settings = type('SettingsFallback', (), {'logger': _fb_logger})()

    settings.logger.error(f"Erro INESPERADO durante imports iniciais em run_processing_pipeline_test.py: {e}")
    sys.exit(1)

if not hasattr(settings, 'logger'):
    import logging
    log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_format)
    settings.logger = logging.getLogger("processing_pipeline_test_logger")
    settings.logger.info("Logger fallback inicializado em run_processing_pipeline_test.py.")


settings.logger.info("--- INICIANDO TESTE DE INTEGRAÇÃO SIMULADO: Pipeline de Processamento ---")

class SimpleTestToolContext:
    def __init__(self):
        self.state = {} 

mock_session_state_context = SimpleTestToolContext()
settings.logger.info(f"MockToolContext para estado da sessão inicializado. Estado: {mock_session_state_context.state}")


# --- Dados de Teste 1: Notícia NewsAPI Bruta ---
raw_newsapi_data = {
    "source_type": "NewsAPI",
    "title": "Petrobras avalia nova rota de escoamento para gás natural do pré-sal, diz fonte - Teste API",
    "url": "https://www.infomoney.com.br/mercados/petrobras-avalia-nova-rota-de-escoamento-para-gas-natural-do-pre-sal-diz-fonte-api-test-001/", # URL ÚNICA
    "author": "Reuters",
    "publishedAt": "2025-06-03T10:30:00Z",
    "description": "A Petrobras está estudando alternativas para escoar a produção de gás natural...",
    "content": "Conteúdo completo do artigo da InfoMoney...",
    "source": {"id": "info-money", "name": "InfoMoney"},
    "company_cvm_code": "9512", # Adicionado para teste
    "full_text": "Texto completo da notícia sobre o novo projeto de exploração da PETR4 no pré-sal. Detalhes sobre o investimento e o cronograma previsto para as operações."
}

# --- Dados de Teste 2: Documento CVM Bruto ---
raw_cvm_data = {
    "source_type": "CVM_IPE",
    "title": "COMUNICADO AO MERCADO: Detalhes sobre a recompra de ações da PETR4 - Teste CVM",
    "document_url": "https://www.rad.cvm.gov.br/ENET/frmDownloadDocumento.aspx?cod=12345_cvm_test_001", # URL ÚNICA
    "publication_date_iso": "2025-05-28T14:00:00+00:00",
    "document_type": "Comunicado ao Mercado",
    "protocol_id": "009512CVM20250528RECOMPRA_TEST",
    "company_cvm_code": "9512",
    "company_name": "PETRÓLEO BRASILEIRO S.A. - PETROBRAS",
    "source_main_file": "ipe_cia_aberta_2025.zip",
    "full_text": "Este é o texto integral do comunicado ao mercado sobre a recompra de ações da Petrobras."
}

# --- Dados de Teste 3: Notícia RSS Bruta ---
raw_rss_data = {
    "source_type": "RSS",
    "title": "Analistas veem oportunidade em PETR4 após balanço do 1T - Teste RSS",
    "link": "https://www.seudinheiro.com/noticias/analistas-petr4-balanco-1t-rss-test-001/", # URL ÚNICA
    "summary": "Sumário da notícia do Seu Dinheiro sobre o balanço da Petrobras no primeiro trimestre.",
    "published_parsed_iso": "2025-06-02T09:00:00Z",
    "source_name": "Seu Dinheiro",
    "feed_url": "https://www.seudinheiro.com/feed/"
}


# --- FUNÇÃO AUXILIAR PARA EXECUTAR O PIPELINE PARA UM ÚNICO ITEM ---
def run_single_item_pipeline(item_data: Dict[str, Any], item_type: str):
    settings.logger.info(f"\n--- Processando {item_type}: {item_data.get('title', item_data.get('headline', 'Sem Título'))[:70]}... ---")

    # 1. AgentePreProcessadorNoticia_ADK
    settings.logger.info("  Chamando tool_preprocess_article_metadata...")
    processed_data_result = tool_preprocess_article_metadata(raw_article_data=item_data)
    if processed_data_result.get("status") == "error":
        settings.logger.error(f"  Pré-processamento falhou: {processed_data_result.get('message')}")
        return

    # 2. AgenteDeCredibilidade_ADK
    settings.logger.info("  Chamando tool_get_source_credibility...")
    credibility_data_result = tool_get_source_credibility(
        source_domain=processed_data_result.get("source_domain"),
        source_name_raw=processed_data_result.get("source_name_raw")
    )
    if not credibility_data_result.get("source_name_curated") or not credibility_data_result.get("base_credibility_score"):
        settings.logger.error(f"  Obtenção de credibilidade falhou ou retornou dados incompletos.")
        return
    
    # 3. AgenteDeFonteNoticia_ADK
    settings.logger.info("  Chamando tool_ensure_news_source_in_db...")
    source_db_data_result = tool_ensure_news_source_in_db(
        source_name_curated=credibility_data_result.get("source_name_curated"),
        source_domain=credibility_data_result.get("source_domain"),
        base_credibility_score=credibility_data_result.get("base_credibility_score"),
        loaded_credibility_data=credibility_data_result.get("loaded_credibility_data"), # Passa os dados carregados
        tool_context=mock_session_state_context
    )
    if source_db_data_result.get("status") == "error":
        settings.logger.error(f"  Garantia de NewsSource no DB falhou: {source_db_data_result.get('message')}")
        return

    # 4. AgenteArmazenadorArtigo_ADK
    settings.logger.info("  Chamando tool_persist_news_or_cvm_document...")
    final_article_data = processed_data_result.copy()
    final_article_data["news_source_id"] = source_db_data_result.get("news_source_id")
    final_article_data.pop("status", None) 
    final_article_data.pop("message", None)

    persist_result = tool_persist_news_or_cvm_document(
        article_data=final_article_data,
        tool_context=mock_session_state_context
    )

    if persist_result.get("status") == "success":
        settings.logger.info(f"  Item persistido com sucesso! ID: {persist_result.get('news_article_id')}")
    else:
        settings.logger.error(f"  Persistência falhou: {persist_result.get('message')}")


# --- EXECUTAR O PIPELINE PARA CADA TIPO DE DADO DE TESTE ---
run_single_item_pipeline(raw_newsapi_data, "Notícia NewsAPI")
run_single_item_pipeline(raw_cvm_data, "Documento CVM")
run_single_item_pipeline(raw_rss_data, "Notícia RSS")


settings.logger.info("\n--- TESTE DE INTEGRAÇÃO SIMULADO: Pipeline de Processamento CONCLUÍDO ---")