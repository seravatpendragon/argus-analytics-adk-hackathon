# src/utils/parser_utils.py (CONTEÚDO CORRIGIDO E COMPLETO DA FUNÇÃO)

import json
from typing import Optional, Dict, Any
from config import settings # <<< GARANTA QUE settings ESTÁ IMPORTADO AQUI PARA O LOGGER

def parse_llm_json_response(response_text: str) -> Optional[Dict[Any, Any]]:
    """
    Extrai uma string JSON de dentro de um bloco de código markdown (```json ... ```)
    e faz o parse para um dicionário Python.
    
    Args:
        response_text: A string de texto que pode conter um JSON.
    
    Returns:
        Um dicionário Python se o parse for bem-sucedido, senão None.
    """
    if not isinstance(response_text, str):
        settings.logger.error(f"Entrada para parse_llm_json_response n├úo ├® string: {type(response_text)}")
        return None

    json_str = None # Inicializa json_str para garantir que ele exista no log de erro
    try:
        # Tenta encontrar o início do bloco de código JSON
        if "```json" in response_text:
            json_str = response_text.split("```json", 1)[1].split("```", 1)[0].strip()
        # Fallback para o caso de o LLM retornar o JSON puro
        elif response_text.strip().startswith("{"):
            json_str = response_text.strip()
        else:
            settings.logger.warning(f"Nenhum formato JSON reconhec├¡vel na resposta do LLM (primeiros 100 chars): {response_text[:100].replace('\n', ' ')}...")
            return None
            
        return json.loads(json_str)

    except (json.JSONDecodeError, IndexError) as e:
        # <<< ESTE É O LOG DETALHADO QUE PRECISAMOS VER >>>
        settings.logger.error(f"Erro ao decodificar JSON do LLM (Tipo: {type(e).__name__}). Detalhes: {e}. String problem├ítica (primeiros 500 chars): {json_str[:500].replace('\n', ' ')}...")
        return None