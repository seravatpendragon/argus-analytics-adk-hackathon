# src/agents/agente_de_credibilidade_adk/tools/tool_get_source_credibility.py

import logging
import os
import re
from datetime import datetime
from typing import Dict, Any, Optional
import json
from pathlib import Path
import sys

logger = logging.getLogger(__name__)

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    # Sobe 4 níveis (tools/ -> agente_de_credibilidade_adk/ -> agents/ -> src/ -> PROJECT_ROOT)
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent.parent
    # Adiciona PROJECT_ROOT ao sys.path se ainda não estiver
    if str(PROJECT_ROOT) not in sys.path:
        import sys
        sys.path.insert(0, str(PROJECT_ROOT))
except Exception as e:
    logger.error(f"Erro ao configurar PROJECT_ROOT em tool_get_source_credibility.py: {e}")
    PROJECT_ROOT = Path(os.getcwd()) # Fallback

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
                    # Usar o source_name como chave principal para busca, ou o domain_key se source_name não existir
                    source_name = details.get("source_name") or domain_key
                    transformed_data[source_name] = details
                    # Adicionar o domain_key dentro dos detalhes, se necessário para a lógica posterior
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

def tool_get_source_credibility(source_domain: str, source_name_raw: Optional[str] = None) -> Dict[str, Any]:
    """
    Busca a credibilidade de uma fonte de notícia baseada no seu domínio ou nome.

    Prioriza a busca pelo source_name_raw, depois pelo source_domain.
    Se a fonte não for encontrada no JSON, atribui um score de credibilidade padrão (0.6).

    Args:
        source_domain (str): O domínio da URL da fonte (ex: 'infomoney.com.br', 'cvm.gov.br').
        source_name_raw (Optional[str]): O nome bruto da fonte, como veio da API/feed (ex: 'InfoMoney', 'Comissão de Valores Mobiliários').

    Returns:
        Dict[str, Any]: Um dicionário contendo:
                        - 'source_name_curated' (str): O nome curado da fonte (do JSON ou o nome bruto/domínio).
                        - 'source_domain' (str): O domínio da fonte.
                        - 'base_credibility_score' (float): O score de credibilidade (do JSON ou padrão).
                        - 'loaded_credibility_data' (Dict[str, Any]): Os dados de credibilidade carregados.
                        - 'message' (str): Mensagem informativa.
    """
    loaded_data = _load_news_source_credibility_data()
    
    # Normaliza o domínio para busca
    normalized_domain = source_domain.lower() if source_domain else None
    if normalized_domain and normalized_domain.startswith("www."):
        normalized_domain = normalized_domain[4:]

    credibility_info = None
    
    # 1. Tenta encontrar pelo source_name_raw (se fornecido e for chave no JSON)
    if source_name_raw and source_name_raw in loaded_data:
        credibility_info = loaded_data.get(source_name_raw)
    
    # 2. Se não encontrou, tenta encontrar pelo normalized_domain (se for chave no JSON)
    if not credibility_info and normalized_domain and normalized_domain in loaded_data:
        credibility_info = loaded_data.get(normalized_domain)

    # 3. Se ainda não encontrou, tenta encontrar pelo campo 'domain' dentro dos detalhes
    # Isso é para casos onde a chave do JSON é o source_name, mas o 'domain' está dentro
    if not credibility_info and normalized_domain:
        for key, details in loaded_data.items():
            if details.get('domain') == normalized_domain:
                credibility_info = details
                break
    
    default_score = 0.6
    curated_name = source_name_raw or source_domain or "Unknown Source"
    score = default_score
    message = f"Credibilidade padrão ({default_score}) atribuída. Fonte '{curated_name}' não encontrada no JSON."

    if credibility_info:
        curated_name = credibility_info.get("source_name", curated_name)
        score = credibility_info.get("overall_credibility_score", default_score)
        message = f"Credibilidade encontrada no JSON para '{curated_name}' (Score: {score})."
    
    logger.info(f"Credibilidade para '{source_domain}' (raw: '{source_name_raw}'): {message}")

    return {
        "source_name_curated": curated_name,
        "source_domain": source_domain, # Retorna o domínio original para consistência
        "base_credibility_score": float(score), # Garante que o score seja float
        "loaded_credibility_data": loaded_data, # Passa os dados carregados para o próximo agente/ferramenta
        "message": message
    }