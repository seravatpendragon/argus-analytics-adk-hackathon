# src/agents/agente_pre_processador_noticia_adk/tools/tool_preprocess_metadata.py

import logging
import re
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

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

    Esta ferramenta identifica o tipo de fonte e aplica lógicas de limpeza e extração
    específicas para padronizar os campos para uso posterior no pipeline.

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

    # Campos comuns a serem padronizados
    headline: Optional[str] = None
    article_link: Optional[str] = None
    publication_date: Optional[datetime] = None
    summary: Optional[str] = None
    source_name_raw: Optional[str] = None # Nome da fonte como veio da API/feed
    source_domain: Optional[str] = None # Domínio extraído da URL

    # --- Lógica de Mapeamento e Padronização por Tipo de Fonte ---
    if source_type == "NewsAPI":
        headline = raw_article_data.get("title")
        article_link = raw_article_data.get("url")
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

        # Extrair domínio da URL do artigo
        source_domain = get_domain_from_url(article_link)

        processed_data = {
            "source_type": source_type,
            "headline": headline,
            "article_link": article_link,
            "publication_date": publication_date.isoformat() if publication_date else None,
            "summary": summary,
            "source_name_raw": source_name_raw,
            "source_domain": source_domain,
            "company_cvm_code": raw_article_data.get("company_cvm_code"), # Passar adiante se já presente
            "full_text": raw_article_data.get("full_text"), # Passar adiante se já presente
            "status": "success"
        }

    elif source_type == "RSS":
        headline = raw_article_data.get("title")
        article_link = raw_article_data.get("link")
        summary = raw_article_data.get("summary")
        source_name_raw = raw_article_data.get("source_name") # Assumindo que o coletor RSS já extraiu isso
        
        if raw_article_data.get("published_parsed_iso"):
            try:
                pub_date_str = raw_article_data["published_parsed_iso"]
                if pub_date_str.endswith("Z"):
                    publication_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                else:
                    publication_date = datetime.fromisoformat(pub_date_str)
            except ValueError:
                logger.warning(f"Data de publicação RSS inválida: {raw_article_data.get('published_parsed_iso')}. Usando None.")
        
        # Extrair domínio da URL do artigo
        source_domain = get_domain_from_url(article_link)

        processed_data = {
            "source_type": source_type,
            "headline": headline,
            "article_link": article_link,
            "publication_date": publication_date.isoformat() if publication_date else None,
            "summary": summary,
            "source_name_raw": source_name_raw,
            "source_domain": source_domain,
            "company_cvm_code": raw_article_data.get("company_cvm_code"), # Passar adiante
            "full_text": raw_article_data.get("full_text"), # Passar adiante
            "status": "success"
        }

    elif source_type == "CVM_IPE":
        # Para CVM, muitos campos já vêm limpos do tool_process_cvm_ipe_local
        headline = raw_article_data.get("title")
        article_link = raw_article_data.get("document_url")
        summary = raw_article_data.get("summary", raw_article_data.get("title")) # Usar título como resumo se não houver
        source_name_raw = "CVM - Regulatórios" # Nome fixo para CVM
        source_domain = "cvm.gov.br" # Domínio fixo para CVM
        
        if raw_article_data.get("publication_date_iso"):
            try:
                pub_date_str = raw_article_data["publication_date_iso"]
                if pub_date_str.endswith("Z"):
                    publication_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                else:
                    publication_date = datetime.fromisoformat(pub_date_str)
            except ValueError:
                logger.warning(f"Data de publicação CVM inválida: {raw_article_data.get('publication_date_iso')}. Usando None.")
        
        processed_data = {
            "source_type": source_type,
            "headline": headline,
            "article_link": article_link,
            "publication_date": publication_date.isoformat() if publication_date else None,
            "summary": summary,
            "source_name_raw": source_name_raw,
            "source_domain": source_domain,
            "company_cvm_code": raw_article_data.get("company_cvm_code"), # Passar adiante
            "document_type": raw_article_data.get("document_type"), # Manter tipo específico de documento CVM
            "protocol_id": raw_article_data.get("protocol_id"), # Manter protocolo CVM
            "full_text": raw_article_data.get("full_text"), # Passar adiante
            "status": "success"
        }
    
    else:
        logger.warning(f"Source type desconhecido ou não suportado para pré-processamento: {source_type}. Retornando erro.")
        return processed_data # Retorna o default de erro

    # Verificações básicas de campos essenciais após o processamento
    if not processed_data.get("headline") or not processed_data.get("article_link"):
        processed_data["status"] = "error"
        processed_data["message"] = "Dados essenciais (headline ou article_link) ausentes após pré-processamento."
        logger.error(f"Pré-processamento falhou para source_type {source_type}: {processed_data['message']}")

    return processed_data