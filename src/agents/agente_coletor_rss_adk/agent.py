# src/agents/agente_coletor_rss_adk/agent.py

import os
import sys
from pathlib import Path
import json
from datetime import datetime

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent # Sobe 3 níveis
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    print(f"PROJECT_ROOT ({PROJECT_ROOT}) foi adicionado/confirmado no sys.path para agent.py (AgenteColetorRSS).")
except NameError:
    PROJECT_ROOT = Path(os.getcwd())
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    print(f"AVISO (agent.py AgenteColetorRSS): __file__ não definido. Usando PROJECT_ROOT como: {PROJECT_ROOT}")

try:
    from config import settings
    from google.adk.agents import Agent
    from google.adk.tools import FunctionTool
    
    # Importa a ferramenta de coleta RSS
    from .tools.tool_collect_rss_articles import tool_collect_rss_articles

    # Importa o prompt local
    from . import prompt as agente_prompt

    # Fallback do logger se settings.logger não estiver disponível
    if not hasattr(settings, 'logger'):
        import logging
        log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        settings.logger = logging.getLogger("agente_coletor_rss_adk_fb_logger")
        settings.logger.info("Logger fallback inicializado em agent.py.")
    print("Módulos do projeto e ADK importados com sucesso para AgenteColetorRSS_ADK.")
except ImportError as e:
    settings.logger.error(f"Erro CRÍTICO em agent.py (AgenteColetorRSS_ADK) ao importar módulos: {e}")
    settings.logger.error(f"PROJECT_ROOT calculado: {PROJECT_ROOT}")
    settings.logger.error(f"sys.path atual: {sys.path}")
    sys.exit(1)
except Exception as e:
    settings.logger.error(f"Erro INESPERADO durante imports iniciais em agent.py (AgenteColetorRSS_ADK): {e}")
    sys.exit(1)

# --- Definição do Modelo LLM a ser usado por este agente ---
MODELO_LLM_AGENTE = "gemini-2.0-flash-001" 
settings.logger.info(f"Modelo LLM para AgenteColetorRSS_ADK: {MODELO_LLM_AGENTE}")

# --- Envolver a função de coleta RSS com FunctionTool ---
collect_rss_tool_adk_instance = FunctionTool(func=tool_collect_rss_articles)

# --- Definição do Agente ---
AgenteColetorRSS_ADK = Agent(
    name="agente_coletor_rss_adk_v1",
    model=MODELO_LLM_AGENTE,
    description=(
        "Agente responsável por coletar artigos de notícias de feeds RSS configurados."
    ),
    instruction=agente_prompt.PROMPT,
    tools=[
        collect_rss_tool_adk_instance, # A ferramenta que faz a coleta
    ],
)

if __name__ == '__main__':
    # Este bloco é para um teste muito básico da definição do agente e uma simulação
    # de como o agente usaria sua ferramenta, sem usar o ADK Runner.
    
    settings.logger.info(f"--- Teste Standalone da Definição e Fluxo Simulado do Agente: {AgenteColetorRSS_ADK.name} ---")
    settings.logger.info(f"  Modelo Configurado: {AgenteColetorRSS_ADK.model}")

    # --- DEBUG: INSPECIONANDO AgenteColetorRSS_ADK.tools ---
    print("\n--- DEBUG: INSPECIONANDO AgenteColetorRSS_ADK.tools ---")
    tool_names_for_log = [] 
    if hasattr(AgenteColetorRSS_ADK, 'tools') and AgenteColetorRSS_ADK.tools is not None:
        print(f"Tipo de AgenteColetorRSS_ADK.tools: {type(AgenteColetorRSS_ADK.tools)}")
        if isinstance(AgenteColetorRSS_ADK.tools, list):
            print(f"Número de ferramentas: {len(AgenteColetorRSS_ADK.tools)}")
            for idx, tool_item in enumerate(AgenteColetorRSS_ADK.tools):
                print(f"  Ferramenta {idx}: {tool_item}")
                print(f"    Tipo da Ferramenta {idx}: {type(tool_item)}")
                print(f"    Possui atributo 'name'? {'Sim' if hasattr(tool_item, 'name') else 'NÃO'}")
                
                tool_name = f"UNKNOWN_TOOL_{idx}" 
                if hasattr(tool_item, 'name'):
                    tool_name = tool_item.name
                    print(f"      tool_item.name: {tool_name}")
                elif hasattr(tool_item, 'func') and hasattr(tool_item.func, '__name__'): 
                    tool_name = tool_item.func.__name__
                    print(f"      tool_item.func.__name__: {tool_item.func.__name__}")
                elif hasattr(tool_item, '__name__'): 
                    tool_name = tool_item.__name__
                    print(f"      tool_item.__name__: {tool_item.__name__}")
                
                tool_names_for_log.append(tool_name)

                if hasattr(tool_item, 'func'): 
                    print(f"      tool_item.func: {tool_item.func}")
                    print(f"      tool_item.func.__name__: {tool_item.func.__name__}")
        else:
            print("AgenteColetorRSS_ADK.tools NÃO é uma lista.")
    else:
        print("AgenteColetorRSS_ADK NÃO possui atributo 'tools' ou é None.")
    print("--- FIM DEBUG: INSPECIONANDO AgenteColetorRSS_ADK.tools ---\n")

    settings.logger.info(f"  Ferramentas Disponíveis (coletado): {tool_names_for_log}")

    settings.logger.info("\n--- SIMULANDO EXECUÇÃO DO AGENTE (CHAMADAS DIRETAS À FERRAMENTA DE COLETA) ---")
    
    # Mock ToolContext (não é estritamente necessário para esta ferramenta, mas é bom ter para consistência)
    class SimpleTestToolContext:
        def __init__(self):
            self.state = {} 

    mock_ctx_collect = SimpleTestToolContext() 
    
    settings.logger.info(f"MockToolContext inicializado para simulação de teste. Estado inicial: {mock_ctx_collect.state}")

    # --- Dados de Teste: Coleta RSS ---
    settings.logger.info("\nSimulando coleta de artigos RSS para feeds específicos:")
    result_rss_collect = collect_rss_tool_adk_instance.func(
        feed_names=["Mock RSS Feed"], # Usar o nome do feed mockado
        tool_context=mock_ctx_collect
    )
    settings.logger.info(f"Resultado da coleta RSS: {json.dumps(result_rss_collect, indent=2, ensure_ascii=False)}")

    settings.logger.info("\n--- Fim do Teste Standalone do Agente Coletor RSS ---")