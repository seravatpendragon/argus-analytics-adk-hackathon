# src/agents/sub_agente_identificador_entidade_adk/tools/tool_identify_entity_ticker.py

import logging
import pandas as pd
from typing import Dict, Any, Optional
from pathlib import Path
import os
import sys

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent.parent # Sobe 4 níveis
    if str(PROJECT_ROOT) not in sys.path:
        sys.sys.path.insert(0, str(PROJECT_ROOT))
except Exception as e:
    logging.error(f"Erro ao configurar PROJECT_ROOT em tool_identify_entity_ticker.py: {e}")
    PROJECT_ROOT = Path(os.getcwd())

try:
    from config import settings
    # Supondo que ativos_mvp.csv esteja em data/config_input
    ATIVOS_MVP_CSV_PATH = settings.BASE_DIR / "data" / "config_input" / "ativos_mvp.csv"
    _USING_MOCK_DATA = False
except ImportError as e:
    logging.error(f"Não foi possível importar settings ou BASE_DIR: {e}. Usando dados mock para tickers.")
    _USING_MOCK_DATA = True

logger = logging.getLogger(__name__)

_COMPANY_TICKER_MAP: Dict[str, str] = {}
_B3_SEGMENTS: Dict[str, str] = {} 

def _load_entity_data():
    global _COMPANY_TICKER_MAP, _B3_SEGMENTS
    if _USING_MOCK_DATA:
        _COMPANY_TICKER_MAP = {
            "PETROBRAS": "PETR4-SA",
            "VALE": "VALE3-SA",
            "ITAU UNIBANCO": "ITUB4-SA",
            "BANCO DO BRASIL": "BBAS3-SA"
        }
        _B3_SEGMENTS = {
            "ENERGIA": "Energia Elétrica",
            "MINERACAO": "Mineração",
            "PETROLEO E GAS": "Petróleo, Gás e Biocombustíveis",
            "SERVICOS FINANCEIROS": "Serviços Financeiros"
        }
        logger.warning("Usando dados mock para mapeamento de entidades/tickers.")
        return

    try:
        if ATIVOS_MVP_CSV_PATH.exists():
            df_ativos = pd.read_csv(str(ATIVOS_MVP_CSV_PATH), sep=';', encoding='utf-8')
            
            if 'EMPRESA' in df_ativos.columns and 'TICKER' in df_ativos.columns:
                 for index, row in df_ativos.iterrows():
                    company_name_raw = str(row['EMPRESA']).upper().strip()
                    ticker = str(row['TICKER']).upper().strip()
                    _COMPANY_TICKER_MAP[company_name_raw] = ticker
            
            _B3_SEGMENTS = {
                "PETROLEO, GAS E BIOCOMBUSTIVEIS": "Petróleo, Gás e Biocombustíveis",
                "ENERGIA ELETRICA": "Energia Elétrica",
                "MINERACAO": "Mineração",
                "BANCOS": "Bancos"
            }

            logger.info(f"Dados de entidades carregados de: {ATIVOS_MVP_CSV_PATH}")
        else:
            logger.warning(f"Arquivo de ativos MVP não encontrado em: {ATIVOS_MVP_CSV_PATH}. Usando mapeamento vazio.")
    except Exception as e:
        logger.error(f"Erro ao carregar dados de entidades de {ATIVOS_MVP_CSV_PATH}: {e}")

_load_entity_data() 

def tool_identify_entity_ticker(
    entity_name_raw: Optional[str], # Mudado para Optional[str]
    entity_type: str,
    tool_context: Any 
) -> Dict[str, Any]:
    """
    Padroniza o nome de uma entidade (empresa, segmento, macroindicador) e retorna seu identificador oficial.
    Usado para garantir consistência dos tickers/nomes no banco de dados.

    Args:
        entity_name_raw (Optional[str]): O nome da entidade ou tema identificado pelo LLM (bruto). Pode ser None.
        entity_type (str): O tipo de entidade ('EMPRESA', 'SEGMENTO_B3', 'MACROECONOMICO', 'OUTROS').
        tool_context (Any): O contexto da ferramenta (opcional, injetado pelo ADK).

    Returns:
        Dict[str, Any]: Um dicionário com 'status', 'padronizado_identificador', 'justificativa'.
    """
    padronizado_identificador: Optional[str] = None
    justificativa = ""

    # CORREÇÃO AQUI: Verifique se entity_name_raw não é None antes de usar .upper()
    if entity_name_raw is None or not entity_name_raw.strip():
        padronizado_identificador = "N/A" # Ou algum outro placeholder para "não identificado"
        justificativa = "Nome da entidade não fornecido ou vazio. Identificador não aplicável."
        logger.warning(f"Nome da entidade bruto era vazio ou None para tipo '{entity_type}'.")
        return {
            "status": "success", # Retorna sucesso, mas com identificador N/A
            "padronizado_identificador": padronizado_identificador,
            "justificativa": justificativa
        }

    entity_name_upper = entity_name_raw.upper().strip()

    try:
        if entity_type == 'EMPRESA':
            padronizado_identificador = _COMPANY_TICKER_MAP.get(entity_name_upper)
            if padronizado_identificador:
                justificativa = f"Nome da empresa '{entity_name_raw}' padronizado para ticker '{padronizado_identificador}'."
            else:
                padronizado_identificador = entity_name_raw # Fallback: usa o nome bruto
                justificativa = f"Ticker não encontrado para '{entity_name_raw}'. Usando nome bruto como identificador."
        
        elif entity_type == 'SEGMENTO_B3':
            padronizado_identificador = _B3_SEGMENTS.get(entity_name_upper)
            if padronizado_identificador:
                 justificativa = f"Nome do segmento '{entity_name_raw}' padronizado para '{padronizado_identificador}'."
            else:
                padronizado_identificador = entity_name_raw 
                justificativa = f"Segmento não encontrado para '{entity_name_raw}'. Usando nome bruto como identificador."
        
        elif entity_type == 'MACROECONOMICO':
            if entity_name_upper == "INFLACAO NO BRASIL" or entity_name_upper == "INFLAÇÃO":
                padronizado_identificador = "IPCA"
            elif entity_name_upper == "PIB BRASIL" or entity_name_upper == "PIB":
                padronizado_identificador = "PIB_Brasil"
            elif entity_name_upper == "TAXA DE JUROS" or entity_name_upper == "SELIC":
                padronizado_identificador = "SELIC"
            elif entity_name_upper == "CÂMBIO BRL" or entity_name_upper == "CAMBIO BRL" or entity_name_upper == "DOLAR":
                padronizado_identificador = "CÂMBIO_BRL"
            else:
                padronizado_identificador = entity_name_raw 
            justificativa = f"Nome do indicador macroeconômico '{entity_name_raw}' padronizado para '{padronizado_identificador}'."
            
        else: # OUTROS
            padronizado_identificador = entity_name_raw
            justificativa = f"Tipo de entidade 'OUTROS' identificado. Usando nome bruto '{entity_name_raw}'."

        logger.info(f"Identificação de Entidade: '{entity_name_raw}' ({entity_type}) -> '{padronizado_identificador}'. {justificativa}")
        return {
            "status": "success",
            "padronizado_identificador": padronizado_identificador,
            "justificativa": justificativa
        }

    except Exception as e:
        logger.error(f"Erro ao padronizar entidade '{entity_name_raw}' ({entity_type}): {e}", exc_info=True)
        return {
            "status": "error",
            "padronizado_identificador": entity_name_raw, 
            "justificativa": f"Erro na padronização: {str(e)}"
        }

if __name__ == '__main__':
    # Teste standalone da ferramenta (executar via python tool_identify_entity_ticker.py)
    # Certifique-se de ter um arquivo `ativos_mvp.csv` em `data/config_input` ou que o mock funcione.
    print("--- Teste Standalone da tool_identify_entity_ticker ---")
    
    class MockToolContext: # Simples mock para ToolContext
        def __init__(self):
            self.state = {}

    test_cases = [
        {"name": "Petrobras", "type": "EMPRESA"},
        {"name": "Vale", "type": "EMPRESA"},
        {"name": "Empresa Inexistente SA", "type": "EMPRESA"},
        {"name": "Petróleo e Gás", "type": "SEGMENTO_B3"},
        {"name": "Energia Elétrica", "type": "SEGMENTO_B3"},
        {"name": "Inflação", "type": "MACROECONOMICO"},
        {"name": "PIB Brasil", "type": "MACROECONOMICO"},
        {"name": "Taxa de Juros", "type": "MACROECONOMICO"},
        {"name": "Câmbio BRL", "type": "MACROECONOMICO"},
        {"name": None, "type": "EMPRESA"}, # Teste de None
        {"name": "", "type": "SEGMENTO_B3"}, # Teste de string vazia
        {"name": "Política Externa", "type": "OUTROS"}
    ]

    for case in test_cases:
        result = tool_identify_entity_ticker(case['name'], case['type'], MockToolContext()) 
        print(f"\nTeste '{case['name']}' ({case['type']}):")
        print(f"  Padronizado: {result.get('padronizado_identificador')}")
        print(f"  Status: {result.get('status')}")
        print(f"  Justificativa: {result.get('justificativa')}")

