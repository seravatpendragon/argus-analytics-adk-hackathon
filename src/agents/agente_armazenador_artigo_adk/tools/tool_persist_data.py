# src/agents/agente_armazenador_artigo_adk/tools/tool_persist_data.py

import logging
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import json
import re
import uuid # Para gerar UUIDs

# Importar a função insert do dialeto postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert 

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    # Sobe 4 níveis (tools/ -> agente_armazenador_artigo_adk/ -> agents/ -> src/ -> PROJECT_ROOT)
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
        NewsArticle, # Importa o modelo NewsArticle para usar no UPSERT
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
    Persiste (UPSERT) metadados de artigos de notícias ou documentos CVM na tabela NewsArticles.

    Args:
        article_data (Dict[str, Any]): Um dicionário contendo os metadados do artigo/documento.
                                       Deve conter um campo 'source_type' (ex: 'NewsAPI', 'RSS', 'CVM_IPE')
                                       para determinar o tipo de mapeamento.
        tool_context (ToolContext): O contexto da ferramenta, injetado pelo ADK.

    Returns:
        Dict[str, Any]: Um dicionário com 'status' ('success' ou 'error') e, em caso de sucesso,
                        o 'news_article_id' do registro salvo.
    """
    session = get_db_session()
    loaded_credibility_data = _load_news_source_credibility_data()

    try:
        source_type = article_data.get("source_type", "UNKNOWN")
        logger.info(f"Ferramenta persist_data: Recebendo dados de fonte: {source_type}")
        logger.info(f"DEBUG_PERSIST: article_link recebido: {article_data.get('article_link')}") 

        headline: str = article_data.get("headline", "Título Desconhecido")
        article_link: str = str(article_data.get("article_link") or f"urn:uuid:{uuid.uuid4()}").strip()
        if not article_link: 
            article_link = f"urn:uuid:{uuid.uuid4()}_fallback"
            logger.warning(f"article_link se tornou vazio inesperadamente. Gerando fallback: {article_link}")

        publication_date: Optional[datetime] = None
        if article_data.get("publication_date"):
            try:
                publication_date = datetime.fromisoformat(article_data["publication_date"])
            except ValueError:
                logger.warning(f"Data de publicação inválida: {article_data.get('publication_date')}. Usando None.")

        summary: Optional[str] = article_data.get("summary")
        source_feed_name: Optional[str] = article_data.get("source_name_raw") # Nome bruto da fonte
        source_feed_url: Optional[str] = article_data.get("feed_url") or article_data.get("url") or article_data.get("document_url")
        news_source_obj: NewsSource 
        company_cvm_code: Optional[str] = article_data.get("company_cvm_code")
        article_type: Optional[str] = article_data.get("document_type") if source_type == "CVM_IPE" else article_data.get("suggested_article_type", "Notícia de Mídia") # Prioriza document_type para CVM, senão suggested_article_type, senão default

        # --- Obter/Criar NewsSource ---
        source_domain_for_db = article_data.get("source_domain")
        if source_type == "CVM_IPE":
            news_source_obj = get_or_create_news_source(session, "CVM - Regulatórios", "Comissão de Valores Mobiliários", loaded_credibility_data, 1.0) 
        elif source_type == "NewsAPI":
            news_source_obj = get_or_create_news_source(session, source_domain_for_db, source_feed_name, loaded_credibility_data, 0.6) 
        elif source_type == "RSS":
            news_source_obj = get_or_create_news_source(session, source_domain_for_db, source_feed_name, loaded_credibility_data, 0.6) 
        else:
            logger.error(f"Source type desconhecido '{source_type}'. Não foi possível obter NewsSource.")
            return {"status": "error", "message": f"Source type desconhecido para persistência: {source_type}"}

        if news_source_obj is None:
            logger.error(f"Não foi possível obter/criar NewsSource para '{source_feed_name}' (Domínio: {source_domain_for_db}). Abortando persistência.")
            return {"status": "error", "message": f"Falha ao obter/criar NewsSource para {source_feed_name}."}

        # --- Preparar dados para UPSERT ---
        values_to_insert = {
            "headline": headline,
            "article_link": article_link,
            "publication_date": publication_date,
            "news_source_id": news_source_obj.news_source_id,
            "article_text_content": article_data.get("full_text"),
            "article_type": article_type,
            "summary": summary,
            "processing_status": 'pending_llm_analysis', # Sempre inicia como pendente para análise LLM
            "source_feed_name": source_feed_name,
            "source_feed_url": source_feed_url,
            "llm_analysis_json": None # Garante que seja Nulo na inserção inicial
        }

        # Constrói o statement UPSERT
        insert_stmt = pg_insert(NewsArticle.__table__).values(values_to_insert)
        
        # Define o que fazer em caso de conflito (pelo article_link, que é UNIQUE)
        on_conflict_stmt = insert_stmt.on_conflict_do_update(
            index_elements=[NewsArticle.article_link], # A coluna com a restrição UNIQUE
            set_={
                # Atualiza campos que podem ter sido refinados ou que queremos manter atualizados
                "headline": insert_stmt.excluded.headline,
                "publication_date": insert_stmt.excluded.publication_date,
                "summary": insert_stmt.excluded.summary,
                "article_text_content": insert_stmt.excluded.article_text_content,
                "article_type": insert_stmt.excluded.article_type,
                "news_source_id": insert_stmt.excluded.news_source_id,
                "source_feed_name": insert_stmt.excluded.source_feed_name,
                "source_feed_url": insert_stmt.excluded.source_feed_url,
                # IMPORTANTE: Se o artigo já existe, queremos manter o status e a análise LLM existente,
                # a menos que haja uma lógica específica para reprocessar.
                # Para o MVP, vamos manter o status existente se já foi analisado, senão, pending.
                "processing_status": NewsArticle.processing_status # Mantém o status existente
            }
        ).returning(NewsArticle.news_article_id) # Retorna o ID do artigo inserido ou atualizado

        result = session.execute(on_conflict_stmt)
        # Para UPSERT, o news_article_id é retornado
        news_article_id_persisted = result.scalar_one_or_none()
        session.commit()

        # Se for uma atualização, o status pode não ser 'pending_llm_analysis'.
        # O AgenteGerenciadorDeAnaliseLLM_ADK buscará apenas 'pending_llm_analysis'.
        # Se um artigo for atualizado aqui, ele manterá seu status anterior.
        # Isso é um comportamento desejável para não re-analisar artigos já completos.

        logger.info(f"Artigo/Documento UPSERT com sucesso. ID: {news_article_id_persisted}")
        return {"status": "success", "news_article_id": news_article_id_persisted, "type": source_type}

    except Exception as e:
        session.rollback()
        logger.error(f"Erro ao persistir artigo/documento: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

    finally:
        session.close()