# src/agents/agente_pre_processador_noticia_adk/tools/tool_preprocess_metadata.py

import logging
import os
import re
from datetime import datetime
from typing import Dict, Any, Optional
import uuid 
from pathlib import Path 
import sys 
import math # Para math.isnan

logger = logging.getLogger(__name__)

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except Exception as e:
    logging.error(f"Erro ao configurar PROJECT_ROOT em tool_preprocess_metadata.py: {e}")
    PROJECT_ROOT = Path(os.getcwd())

def get_domain_from_url(url: str) -> Optional[str]:
    """Extrai o domínio base de uma URL (ex: 'example.com' de 'http://www.example.com/path')."""
    if not url:
        return None
    match = re.search(r'https?://(?:www\.)?([^/]+)', url)
    if match:
        return match.group(1).lower()
    return None

def tool_preprocess_article_metadata(raw_article_data: Dict[str, Any]) -> Dict[str, Any]:
    processed_data: Dict[str, Any] = {
        "source_type": raw_article_data.get("source_type", "UNKNOWN"),
        "headline": None,
        "article_link": None,
        "publication_date": None,
        "summary": None,
        "source_name_raw": None, 
        "source_domain": None, 
        "company_cvm_code": raw_article_data.get("company_cvm_code"),
        "full_text": raw_article_data.get("full_text"),
        "document_type": raw_article_data.get("document_type"),
        "protocol_id": raw_article_data.get("protocol_id"),
        "status": "error", 
        "message": "Pré-processamento não concluído. Verifique o tipo de fonte ou dados essenciais."
    }

    source_type = raw_article_data.get("source_type", "UNKNOWN")
    logger.info(f"Ferramenta preprocess_metadata: Recebendo dados de fonte: {source_type}")

    article_link_raw: Optional[str] = None 
    
    if source_type == "NewsAPI":
        headline_raw = raw_article_data.get("title")
        article_link_raw = raw_article_data.get("url")
        processed_data["summary"] = raw_article_data.get("description")
        processed_data["source_name_raw"] = raw_article_data.get("source", {}).get("name")
        
        if raw_article_data.get("publishedAt"):
            try:
                pub_date_str = raw_article_data["publishedAt"]
                if pub_date_str.endswith("Z"):
                    processed_data["publication_date"] = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                else:
                    processed_data["publication_date"] = datetime.fromisoformat(pub_date_str)
            except ValueError:
                logger.warning(f"Data de publicação NewsAPI inválida: {raw_article_data.get('publishedAt')}. Usando None.")

        processed_data["source_domain"] = get_domain_from_url(article_link_raw)

    elif source_type == "RSS":
        headline_raw = raw_article_data.get("title")
        article_link_raw = raw_article_data.get("link")
        processed_data["summary"] = raw_article_data.get("summary")
        processed_data["source_name_raw"] = raw_article_data.get("source_name")
        
        if raw_article_data.get("published_parsed_iso"):
            try:
                pub_date_str = raw_article_data["published_parsed_iso"]
                if pub_date_str.endswith("Z"):
                    processed_data["publication_date"] = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                else:
                    processed_data["publication_date"] = datetime.fromisoformat(pub_date_str)
            except ValueError:
                logger.warning(f"Data de publicação RSS inválida: {raw_article_data.get('published_parsed_iso')}. Usando None.")
        
        publisher_override = raw_article_data.get("publisher_domain_override")
        if publisher_override:
            processed_data["source_domain"] = publisher_override
        else:
            processed_data["source_domain"] = get_domain_from_url(article_link_raw)

    elif source_type == "CVM_IPE":
        headline_raw = raw_article_data.get("title") # Vem do 'Assunto' do CSV
        article_link_raw = raw_article_data.get("document_url")
        processed_data["summary"] = raw_article_data.get("summary", raw_article_data.get("title"))
        processed_data["source_name_raw"] = "Comissão de Valores Mobiliários"
        processed_data["source_domain"] = "CVM - Regulatórios"
        
        if raw_article_data.get("publication_date_iso"):
            try:
                pub_date_str = raw_article_data["publication_date_iso"]
                if pub_date_str.endswith("Z"):
                    processed_data["publication_date"] = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                else:
                    processed_data["publication_date"] = datetime.fromisoformat(pub_date_str)
            except ValueError:
                logger.warning(f"Data de publicação CVM inválida: {raw_article_data.get('publication_date_iso')}. Usando None.")
        
    else:
        logger.warning(f"Source type desconhecido ou não suportado para pré-processamento: {source_type}. Retornando erro inicial.")
        return processed_data

    # --- Lógica para GARANTIR UM HEADLINE VÁLIDO ---
    # Se o headline original é None, vazio ou NaN, gera um título de fallback.
    if not headline_raw or (isinstance(headline_raw, float) and math.isnan(headline_raw)):
        doc_type = raw_article_data.get("document_type", "Documento")
        protocol_id = raw_article_data.get("protocol_id", "Sem Protocolo")
        processed_data["headline"] = f"{doc_type} CVM (Assunto Não Especificado) - Protocolo: {protocol_id}"
        logger.warning(f"Headline ausente/inválido para source_type {source_type}. Gerando título: {processed_data['headline']}")
    else:
        processed_data["headline"] = str(headline_raw).strip() # Garante que seja string

    # --- Lógica para GARANTIR UM article_link VÁLIDO E ÚNICO ---
    if processed_data.get("publication_date"):
        processed_data["publication_date"] = processed_data["publication_date"].isoformat()

    if not article_link_raw or str(article_link_raw).strip().upper() == "N/A":
        generated_uuid = str(uuid.uuid4())
        current_time_str = datetime.now().strftime("%Y%m%d%H%M%S%f")
        article_link = f"urn:uuid:{generated_uuid}-{source_type}-{current_time_str}" 
        logger.warning(f"article_link ausente/inválido para source_type {source_type}. Gerando link único: {article_link}")
    else:
        article_link = str(article_link_raw).strip()
        if not article_link:
            generated_uuid = str(uuid.uuid4())
            current_time_str = datetime.now().strftime("%Y%m%d%H%M%S%f")
            article_link = f"urn:uuid:{generated_uuid}_empty_fallback-{source_type}-{current_time_str}"
            logger.warning(f"article_link original era string vazia. Gerando link único: {article_link}")

    processed_data["article_link"] = article_link 

    if processed_data["source_domain"] is None: 
        processed_data["source_domain"] = get_domain_from_url(article_link)

    # Verificações finais de campos essenciais
    if not processed_data.get("headline") or not processed_data.get("article_link"):
        processed_data["status"] = "error"
        processed_data["message"] = "Dados essenciais (headline ou article_link) ausentes após pré-processamento final."
        logger.error(f"Pré-processamento falhou para source_type {source_type}: {processed_data['message']}")
    else:
        processed_data["status"] = "success"

    logger.info(f"DEBUG_PREPROCESS: article_link final: {processed_data.get('article_link')}") 
    logger.info(f"DEBUG_PREPROCESS: source_domain final: {processed_data.get('source_domain')}") 

    return processed_data