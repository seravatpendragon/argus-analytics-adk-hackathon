import json
from typing import Optional, Dict, Any

def parse_llm_json_response(response_text: str) -> Optional[Dict[Any, Any]]:
    """
    Extrai uma string JSON de dentro de um bloco de código markdown (```json ... ```)
    e faz o parse para um dicionário Python.
    
    Returns:
        Um dicionário Python se o parse for bem-sucedido, senão None.
    """
    if not isinstance(response_text, str):
        return None

    try:
        # Tenta encontrar o início do bloco de código JSON
        if "```json" in response_text:
            json_str = response_text.split("```json", 1)[1].split("```", 1)[0].strip()
        # Fallback para o caso de o LLM retornar o JSON puro
        elif response_text.strip().startswith("{"):
            json_str = response_text.strip()
        else:
            return None # Não encontrou um formato JSON reconhecível
            
        return json.loads(json_str)

    except (json.JSONDecodeError, IndexError):
        # IndexError pode ocorrer se os splits não encontrarem os delimitadores
        return None