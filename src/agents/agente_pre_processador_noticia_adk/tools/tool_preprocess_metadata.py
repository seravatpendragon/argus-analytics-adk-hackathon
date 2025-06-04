# src/agents/agente_pre_processador_noticia_adk/tools/tool_preprocess_metadata.py

import logging
import os
import re
from datetime import datetime
from typing import Dict, Any, Optional
import uuid # Para gerar IDs únicos
from pathlib import Path
import sys # <-- GARANTIDO AQUI

logger = logging.getLogger(__name__)

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    # CORREÇÃO AQUI: Subir 4 níveis para chegar à raiz do projeto
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except Exception as e:
    logger.error(f"Erro ao configurar PROJECT_ROOT em tool_preprocess_metadata.py: {e}")
    PROJECT_ROOT = Path(os.getcwd()) # Fallback

def get_domain_from_url(url: str) -> Optional[str]:
    """Extrai o domínio base de uma URL (ex: 'example.com' de 'http://www.example.com/path')."""
    if not url:
        return None
    match = re.search(r'https?://(?:www\.)?([^/]+)', url)
    if match:
        return match.group(1).lower() # Retorna em minúsculas
    return None

def tool_preprocess_article_metadata(raw_article_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pré-processa e padroniza metadados brutos de artigos de notícias ou documentos.

    Args:
        raw_article_data (Dict[str, Any]): Um dicionário contendo os metadados brutos
                                            do artigo/documento, conforme coletado.
                                            Deve conter um campo 'source_type' (ex: 'NewsAPI', 'RSS', 'CVM_IPE').

    Returns:
        Dict[str, Any]: Um dicionário de metadados padronizados.
                        Retorna 'status': 'error' se o source_type for desconhecido ou dados essenciais estiverem faltando.
    """
    processed_data: Dict[str, Any] = {
        "status": "error", # Default para erro
        "message": "Source type desconhecido ou dados essenciais faltando."
    }

    source_type = raw_article_data.get("source_type", "UNKNOWN")
    logger.info(f"Ferramenta preprocess_metadata: Recebendo dados de fonte: {source_type}")

    headline: Optional[str] = None
    article_link_raw: Optional[str] = None # Link bruto original
    publication_date: Optional[datetime] = None
    summary: Optional[str] = None
    source_name_raw: Optional[str] = None 
    source_domain: Optional[str] = None 

    # --- Lógica de Mapeamento e Padronização por Tipo de Fonte ---
    if source_type == "NewsAPI":
        headline = raw_article_data.get("title")
        article_link_raw = raw_article_data.get("url") # Usar a URL real
        summary = raw_article_data.get("description")
        source_name_raw = raw_article_data.get("source", {}).get("name")
        
        if raw_article_data.get("publishedAt"):
            try:
                pub_date_str = raw_article_data["publishedAt"]
                if pub_date_str.endswith("Z"):
                    publication_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                else:
                    publication_date = datetime.fromisoformat(pub_date_str)
            except ValueError:
                logger.warning(f"Data de publicação NewsAPI inválida: {raw_article_data.get('publishedAt')}. Usando None.")

    elif source_type == "RSS":
        headline = raw_article_data.get("title")
        article_link_raw = raw_article_data.get("link") # Usar a URL real
        summary = raw_article_data.get("summary")
        source_name_raw = raw_article_data.get("source_name")
        
        if raw_article_data.get("published_parsed_iso"):
            try:
                pub_date_str = raw_article_data["published_parsed_iso"]
                if pub_date_str.endswith("Z"):
                    publication_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                else:
                    publication_date = datetime.fromisoformat(pub_date_str)
            except ValueError:
                logger.warning(f"Data de publicação RSS inválida: {raw_article_data.get('published_parsed_iso')}. Usando None.")
        
    elif source_type == "CVM_IPE":
        headline = raw_article_data.get("title")
        article_link_raw = raw_article_data.get("document_url")
        summary = raw_article_data.get("summary", raw_article_data.get("title"))
        source_name_raw = "Comissão de Valores Mobiliários"
        source_domain = "CVM - Regulatórios" # Identificador fixo para CVM
        
        if raw_article_data.get("publication_date_iso"):
            try:
                pub_date_str = raw_article_data["publication_date_iso"]
                if pub_date_str.endswith("Z"):
                    publication_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                else:
                    publication_date = datetime.fromisoformat(pub_date_str)
            except ValueError:
                logger.warning(f"Data de publicação CVM inválida: {raw_article_data.get('publication_date_iso')}. Usando None.")
        
    else:
        logger.warning(f"Source type desconhecido ou não suportado para pré-processamento: {source_type}. Retornando erro.")
        return processed_data

    # --- Lógica para GARANTIR UM article_link VÁLIDO E ÚNICO ---
    # Se o link original for None, vazio, ou "N/A" (case-insensitive), gera um UUID único como fallback.
    if not article_link_raw or str(article_link_raw).strip().upper() == "N/A":
        generated_uuid = str(uuid.uuid4())
        article_link = f"urn:uuid:{generated_uuid}" # Formato URN para indicar que é um ID gerado
        logger.warning(f"article_link ausente/inválido para source_type {source_type}. Gerando link único: {article_link}")
    else:
        article_link = str(article_link_raw).strip() # Usa o link original limpo e garante que seja string

    # Extrair domínio da URL do artigo (agora que article_link é garantido)
    if source_domain is None: # Só calcula se não foi definido para CVM_IPE
        source_domain = get_domain_from_url(article_link)

    # Preenche processed_data com os valores padronizados
    processed_data = {
        "source_type": source_type,
        "headline": headline,
        "article_link": article_link, # <-- Usa o link GARANTIDO AQUI
        "publication_date": publication_date.isoformat() if publication_date else None,
        "summary": summary,
        "source_name_raw": source_name_raw,
        "source_domain": source_domain,
        "company_cvm_code": raw_article_data.get("company_cvm_code"),
        "full_text": raw_article_data.get("full_text"),
        "document_type": raw_article_data.get("document_type"), # CVM
        "protocol_id": raw_article_data.get("protocol_id"),     # CVM
        "status": "success"
    }

    # Verificações básicas de campos essenciais após o processamento
    if not processed_data.get("headline"): # article_link já é garantido acima
        processed_data["status"] = "error"
        processed_data["message"] = "Dados essenciais (headline) ausentes após pré-processamento."
        logger.error(f"Pré-processamento falhou para source_type {source_type}: {processed_data['message']}")
    
    logger.info(f"DEBUG_PREPROCESS: article_link final: {processed_data.get('article_link')}") # <-- ADICIONADO DEBUG AQUI

    return processed_data