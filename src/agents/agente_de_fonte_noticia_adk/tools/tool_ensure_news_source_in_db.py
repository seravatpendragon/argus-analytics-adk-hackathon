# src/agents/agente_de_fonte_noticia_adk/tools/tool_ensure_news_source_in_db.py

import logging
from typing import Dict, Any, Optional

# --- IMPORTAÇÕES REAIS ---
try:
    from src.database.db_utils import (
        get_db_session,
        get_or_create_news_source, # Esta função retorna o OBJETO NewsSource
    )
    _USING_MOCK_DB = False
except ImportError as e_real_db:
    logging.error(f"Não foi possível importar utilidades reais do banco de dados: {e_real_db}. O teste usará mocks.")
    _USING_MOCK_DB = True

# --- IMPORTAÇÕES MOCK PARA TESTE STANDALONE (CORRIGIDO O CAMINHO) ---
if _USING_MOCK_DB:
    try:
        # CORREÇÃO AQUI: Importa de src.database
        from src.database._mock_db_setup import mock_get_db_session as get_db_session
        from src.database._mock_db_setup import mock_get_or_create_news_source as get_or_create_news_source
        from src.database._mock_db_setup import MockNewsSource as NewsSource # Necessário para type hinting
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

def tool_ensure_news_source_in_db(
    source_name_curated: str,
    source_domain: str,
    base_credibility_score: float,
    loaded_credibility_data: Dict[str, Any], # Dicionário de dados de credibilidade carregados
    tool_context: ToolContext
) -> Dict[str, Any]:
    """
    Garante que uma NewsSource exista no banco de dados e retorna seu ID.

    Args:
        source_name_curated (str): O nome curado da fonte (ex: 'InfoMoney', 'Comissão de Valores Mobiliários').
        source_domain (str): O domínio da fonte (ex: 'infomoney.com.br', 'cvm.gov.br').
        base_credibility_score (float): O score de credibilidade da fonte.
        loaded_credibility_data (Dict[str, Any]): O dicionário completo de dados de credibilidade carregados do JSON.
        tool_context (ToolContext): O contexto da ferramenta, injetado pelo ADK.

    Returns:
        Dict[str, Any]: Um dicionário com 'status' ('success' ou 'error') e, em caso de sucesso,
                        o 'news_source_id' do registro da fonte. Em caso de erro, uma 'message'.
    """
    session = get_db_session()
    
    try:
        # Sua função get_or_create_news_source espera: session, source_domain, source_api_name, loaded_credibility_data, default_unverified_score
        news_source_obj: NewsSource = get_or_create_news_source( # Adicionado type hint para NewsSource
            session=session,
            source_domain=source_domain, # O domínio é a chave para a URL base
            source_api_name=source_name_curated, # O nome curado é usado para buscar no JSON
            loaded_credibility_data=loaded_credibility_data,
            default_unverified_score=base_credibility_score # Passa o score já determinado pelo AgenteDeCredibilidade
        )
        
        if news_source_obj: # Se o objeto NewsSource foi retornado (não None)
            session.commit() # Commita a criação ou atualização da fonte
            logger.info(f"NewsSource '{source_name_curated}' (ID: {news_source_obj.news_source_id}) garantida no DB.")
            return {
                "status": "success",
                "news_source_id": news_source_obj.news_source_id,
                "source_name_curated": source_name_curated,
                "source_domain": source_domain,
                "base_credibility_score": news_source_obj.base_credibility_score # Retorna o score final do DB
            }
        else:
            session.rollback()
            logger.error(f"Falha ao obter ou criar NewsSource para '{source_name_curated}' (Domínio: {source_domain}). get_or_create_news_source retornou None.")
            return {"status": "error", "message": f"Falha ao obter ou criar NewsSource para '{source_name_curated}'."}

    except Exception as e:
        session.rollback()
        logger.error(f"Erro ao garantir NewsSource no DB: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

    finally:
        session.close()