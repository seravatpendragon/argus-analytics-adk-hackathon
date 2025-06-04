# src/agents/agente_armazenador_artigo_adk/tools/tool_persist_data.py

import logging
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import json
import re

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    # Sobe 3 níveis (tools/ -> agente_armazenador_artigo_adk/ -> agents/ -> src/ -> PROJECT_ROOT)
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except Exception as e:
    logging.error(f"Erro ao configurar PROJECT_ROOT em tool_persist_data.py: {e}")
    PROJECT_ROOT = Path(os.getcwd())

# --- IMPORTAÇÕES REAIS (MANTENHA ESTAS DESCOMENTADAS PARA USO COM DB REAL) ---
try:
    from src.database.db_utils import (
        get_db_session,
        get_or_create_news_source,
        get_company_by_cvm_code,
        NewsArticle,
        NewsSource,
        NewsArticleCompanyLink,
        Company
    )
    _USING_MOCK_DB = False
except ImportError as e:
    logging.error(f"Não foi possível importar modelos e utilidades reais do banco de dados: {e}. O teste usará mocks.")
    _USING_MOCK_DB = True

# --- IMPORTAÇÕES MOCK PARA TESTE STANDALONE (CORRIGIDO O CAMINHO) ---
if _USING_MOCK_DB:
    try:
        from src.database._mock_db_setup import mock_get_db_session as get_db_session
        from src.database._mock_db_setup import mock_get_or_create_news_source as get_or_create_news_source
        from src.database._mock_db_setup import mock_get_company_by_cvm_code as get_company_by_cvm_code
        from src.database._mock_db_setup import MockNewsArticle as NewsArticle
        from src.database._mock_db_setup import MockNewsSource as NewsSource
        from src.database._mock_db_setup import MockNewsArticleCompanyLink as NewsArticleCompanyLink
        from src.database._mock_db_setup import MockCompany as Company
    except ImportError as e_mock_db:
        logging.critical(f"Não foi possível importar mocks de banco de dados do caminho centralizado: {e_mock_db}. O script não pode continuar.")
        raise

# Importa ToolContext do ADK (real ou mock)
try:
    from google.adk.tools.tool_context import ToolContext
except ImportError:
    class ToolContext:
        def __init__(self):
            self.state = {}
        pass

logger = logging.getLogger(__name__)

# --- CARREGAR DADOS DE CREDIBILIDADE DA FONTE (UMA VEZ) ---
_NEWS_SOURCE_CREDIBILITY_DATA: Optional[Dict[str, Dict[str, Any]]] = None 

def _load_news_source_credibility_data():
    global _NEWS_SOURCE_CREDIBILITY_DATA
    if _NEWS_SOURCE_CREDIBILITY_DATA is None:
        try:
            file_path = PROJECT_ROOT / "config" / "news_source_domain.json"
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f) 
                transformed_data = {}
                for domain_key, details in raw_data.items():
                    source_name = details.get("source_name") or domain_key 
                    transformed_data[source_name] = details
                    if 'domain' not in details: 
                        details['domain'] = domain_key
                _NEWS_SOURCE_CREDIBILITY_DATA = transformed_data

            logger.info(f"Dados de credibilidade de fontes carregados de: {file_path}")
        except FileNotFoundError:
            logger.error(f"Arquivo news_source_domain.json não encontrado em: {file_path}. A credibilidade será padrão.")
            _NEWS_SOURCE_CREDIBILITY_DATA = {} 
        except json.JSONDecodeError:
            logger.error(f"Erro ao decodificar JSON em news_source_domain.json: {file_path}. A credibilidade será padrão.")
            _NEWS_SOURCE_CREDIBILITY_DATA = {}
        except Exception as e:
            logger.error(f"Erro inesperado ao carregar news_source_domain.json: {e}")
            _NEWS_SOURCE_CREDIBILITY_DATA = {}
    return _NEWS_SOURCE_CREDIBILITY_DATA

def get_domain_from_url(url: str) -> Optional[str]:
    """Extrai o domínio base de uma URL."""
    if not url:
        return None
    match = re.search(r'https?://(?:www\.)?([^/]+)', url)
    if match:
        return match.group(1).lower()
    return None

def tool_persist_news_or_cvm_document(article_data: Dict[str, Any], tool_context: ToolContext) -> Dict[str, Any]:
    """
    Persiste metadados de artigos de notícias ou documentos CVM na tabela NewsArticles.

    Args:
        article_data (Dict[str, Any]): Um dicionário contendo os metadados do artigo/documento.
                                       Deve conter um campo 'source_type' (ex: 'NewsAPI', 'RSS', 'CVM_IPE')
                                       para determinar o tipo de mapeamento.
        tool_context (ToolContext): O contexto da ferramenta, injetado pelo ADK.

    Returns:
        Dict[str, Any]: Um dicionário com 'status' ('success' ou 'error') e, em caso de sucesso,
                        o 'news_article_id' do registro salvo. Em caso de erro, uma 'message'.
    """
    session = get_db_session()
    
    loaded_credibility_data = _load_news_source_credibility_data()

    try:
        source_type = article_data.get("source_type", "UNKNOWN")
        logger.info(f"Ferramenta persist_data: Recebendo dados de fonte: {source_type}")
        logger.info(f"DEBUG_PERSIST: article_link recebido: {article_data.get('article_link')}") # <-- ADICIONADO DEBUG AQUI

        headline: str
        article_link: str = article_data.get("article_link") # Pegar o link já processado
        publication_date: Optional[datetime] = None
        summary: Optional[str] = None
        source_feed_name: Optional[str] = None
        source_feed_url: Optional[str] = None
        news_source_obj: NewsSource 
        company_cvm_code: Optional[str] = None 

        # --- Lógica de Mapeamento Condicional ---
        if source_type == "CVM_IPE":
            headline = article_data.get("headline", "Documento CVM sem Título") # Usar headline já processado
            # article_link já vem do pré-processador
            publication_date = datetime.fromisoformat(article_data["publication_date"]) if article_data.get("publication_date") else None
            summary = article_data.get("summary", article_data.get("headline"))
            source_feed_name = article_data.get("source_main_file", "CVM_IPE_Doc")
            source_feed_url = article_data.get("source_main_file_url")
            company_cvm_code = article_data.get("company_cvm_code")

            news_source_obj = get_or_create_news_source(session, "CVM - Regulatórios", "Comissão de Valores Mobiliários", loaded_credibility_data, 1.0) 
            
        elif source_type == "NewsAPI":
            headline = article_data.get("headline", "Notícia NewsAPI sem Título")
            # article_link já vem do pré-processador
            publication_date = datetime.fromisoformat(article_data["publication_date"]) if article_data.get("publication_date") else None
            summary = article_data.get("summary")
            source_name_curated = article_data.get("source_name_raw", "NewsAPI Source") # Usar o nome bruto já processado
            source_feed_name = source_name_curated
            source_feed_url = article_link # Usar o link do artigo como URL do feed para NewsAPI
            company_cvm_code = article_data.get("company_cvm_code") 

            source_domain_for_db = article_data.get("source_domain") # Usar domínio já processado
            news_source_obj = get_or_create_news_source(session, source_domain_for_db, source_name_curated, loaded_credibility_data, 0.6) 
            
        elif source_type == "RSS":
            headline = article_data.get("headline", "Notícia RSS sem Título")
            # article_link já vem do pré-processador
            publication_date = datetime.fromisoformat(article_data["publication_date"]) if article_data.get("publication_date") else None
            summary = article_data.get("summary")
            source_name_curated = article_data.get("source_name_raw", "RSS Feed") 
            source_feed_name = source_name_curated
            source_feed_url = article_data.get("feed_url") 
            company_cvm_code = article_data.get("company_cvm_code") 

            source_domain_for_db = article_data.get("source_domain") # Usar domínio já processado
            news_source_obj = get_or_create_news_source(session, source_domain_for_db, source_name_curated, loaded_credibility_data, 0.6) 
            
        else:
            logger.warning(f"Fonte de artigo desconhecida: {source_type}. Não será persistido.")
            return {"status": "error", "message": f"Fonte de artigo desconhecida: {source_type}"}

        if news_source_obj is None:
            logger.error(f"Não foi possível obter/criar NewsSource para '{source_feed_name}' (Tipo: {source_type}). Abortando persistência.")
            return {"status": "error", "message": f"Falha ao obter/criar NewsSource para {source_feed_name}."}

        new_article = NewsArticle(
            headline=headline,
            article_link=article_link, # <-- Usa o link garantido pelo pré-processador
            publication_date=publication_date,
            news_source_id=news_source_obj.news_source_id, 
            article_text_content=article_data.get("full_text"), 
            article_type=article_data.get("document_type") if source_type == "CVM_IPE" else "Notícia de Mídia", # Usar document_type para CVM
            summary=summary,
            processing_status='pending_llm_analysis', 
            source_feed_name=source_feed_name,
            source_feed_url=source_feed_url
        )

        session.add(new_article)
        session.flush() 

        if company_cvm_code: 
            company_id = get_company_by_cvm_code(session, company_cvm_code, "PETRÓLEO BRASILEIRO S.A. - PETROBRAS")
            if company_id:
                new_link = NewsArticleCompanyLink(
                    news_article_id=new_article.news_article_id,
                    company_id=company_id
                )
                session.add(new_link)
            else:
                logger.warning(f"Empresa com CVM Code {company_cvm_code} não encontrada no banco. Não foi possível criar NewsArticleCompanyLink.")
        else:
            logger.warning("Nenhum CVM Code fornecido para vincular o artigo à empresa.")


        session.commit()
        logger.info(f"Artigo/Documento persistido com sucesso. ID: {new_article.news_article_id}")
        return {"status": "success", "news_article_id": new_article.news_article_id, "type": source_type}

    except Exception as e:
        session.rollback()
        logger.error(f"Erro ao persistir artigo/documento: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

    finally:
        session.close()