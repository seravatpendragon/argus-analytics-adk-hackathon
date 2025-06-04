# src/agents/agente_armazenador_artigo_adk/tools/tool_persist_data.py

import logging
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import json
import re # Para extrair domínio da URL

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    # CORREÇÃO CRÍTICA AQUI: Subir 4 níveis para chegar à raiz do projeto
    # tools/ (1) -> agente_armazenador_artigo_adk/ (2) -> agents/ (3) -> src/ (4) -> PROJECT_ROOT
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent.parent
    # Adiciona PROJECT_ROOT ao sys.path se ainda não estiver para imports como config.settings
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except Exception as e:
    logging.error(f"Erro ao configurar PROJECT_ROOT em tool_persist_data.py: {e}")
    PROJECT_ROOT = Path(os.getcwd()) # Fallback

# --- IMPORTAÇÕES REAIS (MANTENHA ESTAS DESCOMENTADAS PARA USO COM DB REAL) ---
# Se você for usar o banco de dados real, DESCOMENTE estas linhas e COMENTE as MOCKS.
try:
    from src.database.db_utils import (
        get_db_session,
        get_or_create_news_source, # Esta função retorna o OBJETO NewsSource
        get_company_by_cvm_code,
        NewsArticle,
        NewsSource, # Importa o modelo NewsSource
        NewsArticleCompanyLink,
        Company
    )
    _USING_MOCK_DB = False
except ImportError as e:
    logging.error(f"Não foi possível importar modelos e utilidades reais do banco de dados: {e}. O teste usará mocks.")
    # Fallback para MOCKS se as importações reais falharem
    # Se você for usar o banco de dados real, COMENTE as linhas abaixo.
    try:
        from ._mock_db_setup import mock_get_db_session as get_db_session
        from ._mock_db_setup import mock_get_or_create_news_source as get_or_create_news_source
        from ._mock_db_setup import mock_get_company_by_cvm_code as get_company_by_cvm_code
        from ._mock_db_setup import MockNewsArticle as NewsArticle
        from ._mock_db_setup import MockNewsSource as NewsSource
        from ._mock_db_setup import MockNewsArticleCompanyLink as NewsArticleCompanyLink
        from ._mock_db_setup import MockCompany as Company
        _USING_MOCK_DB = True
    except ImportError:
        logging.critical("Não foi possível importar mocks de banco de dados. O script não pode continuar sem uma configuração de DB.")
        raise # Levanta erro fatal se nem o real nem o mock funcionarem

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
        return match.group(1)
    return None

def tool_persist_news_or_cvm_document(article_data: Dict[str, Any], tool_context: ToolContext) -> Dict[str, Any]:
    """
    Persiste metadados de artigos de notícias ou documentos CVM na tabela NewsArticles.

    Esta ferramenta é flexível para lidar com diferentes estruturas de dados
    (notícias de NewsAPI/RSS ou metadados de documentos CVM) e mapeá-los
    para o esquema unificado de NewsArticles.

    Args:
        article_data (Dict[str, Any]): Um dicionário contendo os metadados do artigo/documento.
                                       Deve conter um campo 'source_type' (ex: 'NewsAPI', 'RSS', 'CVM_IPE')
                                       para determinar o tipo de mapeamento.
        tool_context (ToolContext): O contexto da ferramenta, injetado pelo ADK,
                                    permitindo acesso ao estado da sessão.

    Returns:
        Dict[str, Any]: Um dicionário com 'status' ('success' ou 'error') e, em caso de sucesso,
                        o 'news_article_id' do registro salvo. Em caso de erro, uma 'message'.
    """
    session = get_db_session()
    
    loaded_credibility_data = _load_news_source_credibility_data()

    try:
        source_type = article_data.get("source_type", "UNKNOWN")
        logger.info(f"Ferramenta persist_data: Recebendo dados de fonte: {source_type}")

        headline: str
        article_link: str
        publication_date: Optional[datetime] = None
        article_type: Optional[str] = None
        summary: Optional[str] = None
        source_feed_name: Optional[str] = None
        source_feed_url: Optional[str] = None
        news_source_obj: NewsSource # Objeto NewsSource retornado por get_or_create_news_source
        company_cvm_code: Optional[str] = None 

        # --- Lógica de Mapeamento Condicional ---
        if source_type == "CVM_IPE":
            headline = article_data.get("title", "Documento CVM sem Título")
            article_link = article_data.get("document_url", "N/A")
            try:
                pub_date_str = article_data.get("publication_date_iso")
                if pub_date_str:
                    if pub_date_str.endswith("Z"):
                        publication_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                    else:
                        publication_date = datetime.fromisoformat(pub_date_str)
            except ValueError:
                logger.warning(f"Data de publicação CVM inválida: {article_data.get('publication_date_iso')}. Usando None.")
                publication_date = None
            
            article_type = article_data.get("document_type", "Documento Regulatório CVM")
            summary = article_data.get("summary", article_data.get("title", "Documento CVM"))
            source_feed_name = article_data.get("source_main_file", "CVM_IPE_Doc")
            source_feed_url = article_data.get("source_main_file_url")
            company_cvm_code = article_data.get("company_cvm_code")

            # CORREÇÃO AQUI: get_or_create_news_source retorna o OBJETO NewsSource
            news_source_obj = get_or_create_news_source(session, "CVM - Regulatórios", 1.0, loaded_credibility_data) 
            
        elif source_type == "NewsAPI":
            headline = article_data.get("title", "Notícia NewsAPI sem Título")
            article_link = article_data.get("url", "N/A")
            try:
                pub_date_str = article_data.get("publishedAt")
                if pub_date_str:
                    if pub_date_str.endswith("Z"):
                        publication_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                    else:
                        publication_date = datetime.fromisoformat(pub_date_str)
            except ValueError:
                logger.warning(f"Data de publicação NewsAPI inválida: {article_data.get('publishedAt')}. Usando None.")
                publication_date = None

            article_type = "Notícia de Mídia" 
            summary = article_data.get("description")
            source_name_curated = article_data.get("source", {}).get("name", "NewsAPI Source") 
            source_feed_name = source_name_curated
            source_feed_url = article_data.get("url") 
            company_cvm_code = article_data.get("company_cvm_code") 

            # CORREÇÃO AQUI: get_or_create_news_source retorna o OBJETO NewsSource
            # Usar o domínio da URL como source_domain para get_or_create_news_source
            source_domain_for_db = get_domain_from_url(article_link) or source_name_curated # Prioriza domínio
            news_source_obj = get_or_create_news_source(session, source_domain_for_db, 0.6, loaded_credibility_data) 
            
        elif source_type == "RSS":
            headline = article_data.get("title", "Notícia RSS sem Título")
            article_link = article_data.get("link", "N/A")
            try:
                pub_date_str = article_data.get("published_parsed_iso") 
                if pub_date_str:
                    if pub_date_str.endswith("Z"):
                        publication_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                    else:
                        publication_date = datetime.fromisoformat(pub_date_str)
            except ValueError:
                logger.warning(f"Data de publicação RSS inválida: {article_data.get('published_parsed_iso')}. Usando None.")
                publication_date = None

            article_type = "Notícia de Mídia"
            summary = article_data.get("summary")
            source_name_curated = article_data.get("source_name", "RSS Feed") 
            source_feed_name = source_name_curated
            source_feed_url = article_data.get("feed_url") 
            company_cvm_code = article_data.get("company_cvm_code") 

            # CORREÇÃO AQUI: get_or_create_news_source retorna o OBJETO NewsSource
            # Usar o domínio da URL como source_domain para get_or_create_news_source
            source_domain_for_db = get_domain_from_url(article_link) or source_name_curated # Prioriza domínio
            news_source_obj = get_or_create_news_source(session, source_domain_for_db, 0.6, loaded_credibility_data) 
            
        else:
            logger.warning(f"Fonte de artigo desconhecida: {source_type}. Não será persistido.")
            return {"status": "error", "message": f"Fonte de artigo desconhecida: {source_type}"}

        # VERIFICAÇÃO CRÍTICA: Se news_source_obj não foi encontrado/criado, não prossiga.
        if news_source_obj is None:
            logger.error(f"Não foi possível obter/criar NewsSource para '{source_feed_name}' (Tipo: {source_type}). Abortando persistência.")
            return {"status": "error", "message": f"Falha ao obter/criar NewsSource para {source_feed_name}."}

        # Cria o objeto NewsArticle
        new_article = NewsArticle(
            headline=headline,
            article_link=article_link,
            publication_date=publication_date,
            news_source_id=news_source_obj.news_source_id, # <--- CORREÇÃO AQUI: Pega o ID do objeto NewsSource
            article_text_content=article_data.get("full_text"), 
            article_type=article_type,
            summary=summary,
            processing_status='pending_llm_analysis', 
            source_feed_name=source_feed_name,
            source_feed_url=source_feed_url
        )

        session.add(new_article)
        session.flush() 

        # Vinculação com a empresa (PETR4)
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