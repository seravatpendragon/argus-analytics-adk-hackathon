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
        sys.path.insert(0, str(PROJECT_ROOT))
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
_B3_SEGMENTS: Dict[str, str] = {} # Simples mapeamento para MVP

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
            # Supondo que o CSV tenha colunas como 'Nome_Empresa', 'Ticker_Padronizado'
            # E para segmentos, talvez uma coluna 'Segmento_Oficial'
            
            # Mapeamento de empresas
            if 'EMPRESA' in df_ativos.columns and 'TICKER' in df_ativos.columns:
                 # Criar um mapeamento flexível para nomes (case-insensitive, sem espaços extras)
                for index, row in df_ativos.iterrows():
                    company_name_raw = str(row['EMPRESA']).upper().strip()
                    ticker = str(row['TICKER']).upper().strip()
                    _COMPANY_TICKER_MAP[company_name_raw] = ticker
                    # Adicionar variações se necessário (ex: "PETROBRAS" -> "PETR4-SA")
            
            # Exemplo de mapeamento de segmentos (se o CSV tiver dados de segmento)
            # Para o MVP, você pode querer hardcode uma pequena lista de segmentos relevantes
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

_load_entity_data() # Carrega os dados na inicialização do módulo

def tool_identify_entity_ticker(
    entity_name_raw: str,
    entity_type: str,
    tool_context: Any # Opcional, injetado pelo ADK
) -> Dict[str, Any]:
    """
    Padroniza o nome de uma entidade (empresa, segmento, macroindicador) e retorna seu identificador oficial.
    Usado para garantir consistência dos tickers/nomes no banco de dados.

    Args:
        entity_name_raw (str): O nome da entidade ou tema identificado pelo LLM (bruto).
        entity_type (str): O tipo de entidade ('EMPRESA', 'SEGMENTO_B3', 'MACROECONOMICO', 'OUTROS').
        tool_context (Any): O contexto da ferramenta (opcional, injetado pelo ADK).

    Returns:
        Dict[str, Any]: Um dicionário com 'status', 'padronizado_identificador', 'justificativa'.
    """
    padronizado_identificador: Optional[str] = None
    justificativa = ""
    entity_name_upper = entity_name_raw.upper().strip()

    try:
        if entity_type == 'EMPRESA':
            # Tenta encontrar o ticker padronizado. Mais lógica pode ser adicionada aqui
            # para lidar com variações do nome da empresa.
            padronizado_identificador = _COMPANY_TICKER_MAP.get(entity_name_upper)
            if padronizado_identificador:
                justificativa = f"Nome da empresa '{entity_name_raw}' padronizado para ticker '{padronizado_identificador}'."
            else:
                # Fallback se não encontrar, usa o nome bruto
                padronizado_identificador = entity_name_raw
                justificativa = f"Ticker não encontrado para '{entity_name_raw}'. Usando nome bruto."
        
        elif entity_type == 'SEGMENTO_B3':
            # Tenta padronizar o nome do segmento.
            padronizado_identificador = _B3_SEGMENTS.get(entity_name_upper)
            if padronizado_identificador:
                 justificativa = f"Nome do segmento '{entity_name_raw}' padronizado para '{padronizado_identificador}'."
            else:
                padronizado_identificador = entity_name_raw # Usa o nome bruto como fallback
                justificativa = f"Segmento não encontrado para '{entity_name_raw}'. Usando nome bruto."
        
        elif entity_type == 'MACROECONOMICO':
            # Para macroeconômico, pode-se ter um mapeamento de nomes/indicadores
            # Para o MVP, pode-se usar o nome bruto como padronizado ou ter um mapeamento simples
            if entity_name_upper == "INFLACAO NO BRASIL":
                padronizado_identificador = "IPCA"
            elif entity_name_upper == "PIB BRASIL":
                padronizado_identificador = "PIB_Brasil"
            else:
                padronizado_identificador = entity_name_raw # Usa o nome bruto como fallback
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
            "padronizado_identificador": entity_name_raw, # Retorna o original em caso de erro
            "justificativa": f"Erro na padronização: {str(e)}"
        }

if __name__ == '__main__':
    # Teste standalone da ferramenta (executar via python tool_identify_entity_ticker.py)
    # Certifique-se de ter um arquivo `ativos_mvp.csv` em `data/config_input` ou que o mock funcione.
    test_cases = [
        {"name": "Petrobras", "type": "EMPRESA"},
        {"name": "Vale", "type": "EMPRESA"},
        {"name": "Empresa Inexistente SA", "type": "EMPRESA"},
        {"name": "Petróleo e Gás", "type": "SEGMENTO_B3"},
        {"name": "Energia Elétrica", "type": "SEGMENTO_B3"},
        {"name": "Comércio Varejista", "type": "SEGMENTO_B3"},
        {"name": "inflação no Brasil", "type": "MACROECONOMICO"},
        {"name": "Taxa de juros dos EUA", "type": "MACROECONOMICO"},
        {"name": "Política Externa", "type": "OUTROS"}
    ]

    for case in test_cases:
        result = tool_identify_entity_ticker(case['name'], case['type'], None) # None para tool_context em teste
        print(f"\nTeste '{case['name']}' ({case['type']}):")
        print(f"  Padronizado: {result.get('padronizado_identificador')}")
        print(f"  Status: {result.get('status')}")
        print(f"  Justificativa: {result.get('justificativa')}")