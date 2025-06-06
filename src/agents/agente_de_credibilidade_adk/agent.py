# src/agents/agente_de_credibilidade_adk/agent.py

import os
import sys
from pathlib import Path
import json
from datetime import datetime
import logging

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent # Sobe 3 níveis (agente_de_credibilidade_adk -> agents -> src -> PROJECT_ROOT)
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

try:
    from config import settings
    from google.adk.agents import Agent
    from google.adk.tools import FunctionTool
    
    # Importa a ferramenta de credibilidade
    from .tools.tool_get_source_credibility import tool_get_source_credibility

    # Importa o prompt local
    from . import prompt as agente_prompt

    # Fallback do logger se settings.logger não estiver disponível
    if not hasattr(settings, 'logger'):
        import logging
        log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        settings.logger = logging.getLogger("agente_de_credibilidade_adk_fb_logger")
        settings.logger.info("Logger fallback inicializado em agent.py.")
    settings.logger.info("Módulos do projeto e ADK importados com sucesso para AgenteDeCredibilidade_ADK.")
except ImportError as e:
    settings.logger.error(f"Erro CRÍTICO em agent.py (AgenteDeCredibilidade_ADK) ao importar módulos: {e}")
    settings.logger.error(f"PROJECT_ROOT calculado: {PROJECT_ROOT}")
    settings.logger.error(f"sys.path atual: {sys.path}")
    sys.exit(1)
except Exception as e:
    settings.logger.error(f"Erro INESPERADO durante imports iniciais em agent.py (AgenteDeCredibilidade_ADK): {e}")
    sys.exit(1)

# --- Definição do Modelo LLM a ser usado por este agente ---
MODELO_LLM_AGENTE = "gemini-2.0-flash-001" 
settings.logger.info(f"Modelo LLM para AgenteDeCredibilidade_ADK: {MODELO_LLM_AGENTE}")

# --- Envolver a função de credibilidade com FunctionTool ---
get_credibility_tool_adk_instance = FunctionTool(func=tool_get_source_credibility)

# --- Definição do Agente ---
AgenteDeCredibilidade_ADK = Agent(
    name="agente_de_credibilidade_adk_v1",
    model=MODELO_LLM_AGENTE,
    description=(
        "Agente responsável por avaliar a credibilidade de fontes de notícias e documentos "
        "com base em um conjunto de dados predefinido."
    ),
    instruction=agente_prompt.PROMPT,
    tools=[
        get_credibility_tool_adk_instance, # A ferramenta que busca a credibilidade
    ],
)

if __name__ == '__main__':
    # Este bloco é para um teste muito básico da definição do agente e uma simulação
    # de como o agente usaria sua ferramenta, sem usar o ADK Runner.
    
    settings.logger.info(f"--- Teste Standalone da Definição e Fluxo Simulado do Agente: {AgenteDeCredibilidade_ADK.name} ---")
    settings.logger.info(f"  Modelo Configurado: {AgenteDeCredibilidade_ADK.model}")

    # --- DEBUG: INSPECIONANDO AgenteDeCredibilidade_ADK.tools ---
    settings.logger.info("\n--- DEBUG: INSPECIONANDO AgenteDeCredibilidade_ADK.tools ---")
    tool_names_for_log = [] 
    if hasattr(AgenteDeCredibilidade_ADK, 'tools') and AgenteDeCredibilidade_ADK.tools is not None:
        settings.logger.info(f"Tipo de AgenteDeCredibilidade_ADK.tools: {type(AgenteDeCredibilidade_ADK.tools)}")
        if isinstance(AgenteDeCredibilidade_ADK.tools, list):
            settings.logger.info(f"Número de ferramentas: {len(AgenteDeCredibilidade_ADK.tools)}")
            for idx, tool_item in enumerate(AgenteDeCredibilidade_ADK.tools):
                settings.logger.info(f"  Ferramenta {idx}: {tool_item}")
                settings.logger.info(f"    Tipo da Ferramenta {idx}: {type(tool_item)}")
                settings.logger.info(f"    Possui atributo 'name'? {'Sim' if hasattr(tool_item, 'name') else 'NÃO'}")
                
                tool_name = f"UNKNOWN_TOOL_{idx}" 
                if hasattr(tool_item, 'name'):
                    tool_name = tool_item.name
                    settings.logger.info(f"      tool_item.name: {tool_name}")
                elif hasattr(tool_item, 'func') and hasattr(tool_item.func, '__name__'): 
                    tool_name = tool_item.func.__name__
                    settings.logger.info(f"      tool_item.func.__name__: {tool_name}")
                elif hasattr(tool_item, '__name__'): 
                    tool_name = tool_item.__name__
                    settings.logger.info(f"      tool_item.__name__: {tool_item.__name__}")
                
                tool_names_for_log.append(tool_name)

                if hasattr(tool_item, 'func'): 
                    settings.logger.info(f"      tool_item.func: {tool_item.func}")
                    settings.logger.info(f"      tool_item.func.__name__: {tool_item.func.__name__}")
        else:
            settings.logger.info("AgenteDeCredibilidade_ADK.tools NÃO é uma lista.")
    else:
        settings.logger.info("AgenteDeCredibilidade_ADK NÃO possui atributo 'tools' ou é None.")
    settings.logger.info("--- FIM DEBUG: INSPECIONANDO AgenteDeCredibilidade_ADK.tools ---\n")

    settings.logger.info(f"  Ferramentas Disponíveis (coletado): {tool_names_for_log}")

    settings.logger.info("\n--- SIMULANDO EXECUÇÃO DO AGENTE (CHAMADAS DIRETAS À FERRAMENTA DE CREDIBILIDADE) ---")
    
    # Mock ToolContext (não é estritamente necessário para esta ferramenta, mas é bom ter para consistência)
    class SimpleTestToolContext:
        def __init__(self):
            self.state = {} 

    mock_ctx_credibility = SimpleTestToolContext() 
    
    settings.logger.info(f"MockToolContext inicializado para simulação de teste. Estado inicial: {mock_ctx_credibility.state}")

    # --- Dados de Teste 1: Fonte Conhecida (InfoMoney) ---
    settings.logger.info("\nSimulando credibilidade para fonte CONHECIDA (InfoMoney):")
    result_known_source = get_credibility_tool_adk_instance.func(
        source_domain="infomoney.com.br",
        source_name_raw="InfoMoney"
    )
    settings.logger.info(f"Resultado credibilidade InfoMoney: {json.dumps(result_known_source, indent=2, ensure_ascii=False)}")

    # --- Dados de Teste 2: Fonte Conhecida (CVM) ---
    settings.logger.info("\nSimulando credibilidade para fonte CONHECIDA (CVM - Regulatórios):")
    result_cvm_source = get_credibility_tool_adk_instance.func(
        source_domain="cvm.gov.br",
        source_name_raw="CVM - Regulatórios"
    )
    settings.logger.info(f"Resultado credibilidade CVM: {json.dumps(result_cvm_source, indent=2, ensure_ascii=False)}")

    # --- Dados de Teste 3: Fonte Desconhecida ---
    settings.logger.info("\nSimulando credibilidade para fonte DESCONHECIDA (blogpessoal.com):")
    result_unknown_source = get_credibility_tool_adk_instance.func(
        source_domain="blogpessoal.com",
        source_name_raw="Blog Pessoal do Zé"
    )
    settings.logger.info(f"Resultado credibilidade Blog Pessoal: {json.dumps(result_unknown_source, indent=2, ensure_ascii=False)}")

    # --- Dados de Teste 4: Fonte com apenas domínio ---
    settings.logger.info("\nSimulando credibilidade para fonte com APENAS DOMÍNIO (nytimes.com):")
    result_domain_only = get_credibility_tool_adk_instance.func(
        source_domain="nytimes.com"
    )
    settings.logger.info(f"Resultado credibilidade NYTimes (apenas domínio): {json.dumps(result_domain_only, indent=2, ensure_ascii=False)}")

    settings.logger.info("\n--- Fim do Teste Standalone do Agente de Credibilidade ---")