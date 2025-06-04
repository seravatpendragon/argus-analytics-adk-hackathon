# src/agents/agente_gerenciador_analise_llm_adk/agent.py

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
    print(f"PROJECT_ROOT ({PROJECT_ROOT}) foi adicionado/confirmado no sys.path para agent.py (AgenteGerenciadorAnaliseLLM).")
except NameError:
    PROJECT_ROOT = Path(os.getcwd())
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    print(f"AVISO (agent.py AgenteGerenciadorAnaliseLLM): __file__ não definido. Usando PROJECT_ROOT como: {PROJECT_ROOT}")

try:
    from config import settings
    from google.adk.agents import Agent
    from google.adk.tools import FunctionTool
    
    # Importa a ferramenta de busca de artigos pendentes
    from .tools.tool_fetch_pending_articles import tool_fetch_pending_articles

    # Importa o prompt local
    from . import prompt as agente_prompt

    # Fallback do logger se settings.logger não estiver disponível
    if not hasattr(settings, 'logger'):
        import logging
        log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        settings.logger = logging.getLogger("agente_gerenciador_analise_llm_adk_fb_logger")
        settings.logger.info("Logger fallback inicializado em agent.py.")
    print("Módulos do projeto e ADK importados com sucesso para AgenteGerenciadorAnaliseLLM_ADK.")
except ImportError as e:
    settings.logger.error(f"Erro CRÍTICO em agent.py (AgenteGerenciadorAnaliseLLM_ADK) ao importar módulos: {e}")
    settings.logger.error(f"PROJECT_ROOT calculado: {PROJECT_ROOT}")
    settings.logger.error(f"sys.path atual: {sys.path}")
    sys.exit(1)
except Exception as e:
    settings.logger.error(f"Erro INESPERADO durante imports iniciais em agent.py (AgenteGerenciadorAnaliseLLM_ADK): {e}")
    sys.exit(1)

# --- Definição do Modelo LLM a ser usado por este agente ---
MODELO_LLM_AGENTE = "gemini-2.0-flash-001" 
settings.logger.info(f"Modelo LLM para AgenteGerenciadorAnaliseLLM_ADK: {MODELO_LLM_AGENTE}")

# --- Envolver a função de busca de artigos com FunctionTool ---
fetch_articles_tool_adk_instance = FunctionTool(func=tool_fetch_pending_articles)

# --- Definição do Agente ---
AgenteGerenciadorDeAnaliseLLM_ADK = Agent(
    name="agente_gerenciador_analise_llm_adk_v1",
    model=MODELO_LLM_AGENTE,
    description=(
        "Agente responsável por orquestrar a análise de artigos e documentos por Large Language Models (LLMs), "
        "buscando itens pendentes e delegando a sub-agentes especializados."
    ),
    instruction=agente_prompt.PROMPT,
    tools=[
        fetch_articles_tool_adk_instance, # A ferramenta que busca artigos pendentes
    ],
    # sub_agents=[] # Aqui serão adicionados os sub-agentes de análise (Sentimento, Maslow, etc.)
)

if __name__ == '__main__':
    # Este bloco é para um teste muito básico da definição do agente e uma simulação
    # de como o agente usaria sua ferramenta, sem usar o ADK Runner.
    
    settings.logger.info(f"--- Teste Standalone da Definição e Fluxo Simulado do Agente: {AgenteGerenciadorDeAnaliseLLM_ADK.name} ---")
    settings.logger.info(f"  Modelo Configurado: {AgenteGerenciadorDeAnaliseLLM_ADK.model}")

    # --- DEBUG: INSPECIONANDO AgenteGerenciadorDeAnaliseLLM_ADK.tools ---
    print("\n--- DEBUG: INSPECIONANDO AgenteGerenciadorDeAnaliseLLM_ADK.tools ---")
    tool_names_for_log = [] 
    if hasattr(AgenteGerenciadorDeAnaliseLLM_ADK, 'tools') and AgenteGerenciadorDeAnaliseLLM_ADK.tools is not None:
        print(f"Tipo de AgenteGerenciadorDeAnaliseLLM_ADK.tools: {type(AgenteGerenciadorDeAnaliseLLM_ADK.tools)}")
        if isinstance(AgenteGerenciadorDeAnaliseLLM_ADK.tools, list):
            print(f"Número de ferramentas: {len(AgenteGerenciadorDeAnaliseLLM_ADK.tools)}")
            for idx, tool_item in enumerate(AgenteGerenciadorDeAnaliseLLM_ADK.tools):
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
            print("AgenteGerenciadorDeAnaliseLLM_ADK.tools NÃO é uma lista.")
    else:
        print("AgenteGerenciadorDeAnaliseLLM_ADK NÃO possui atributo 'tools' ou é None.")
    print("--- FIM DEBUG: INSPECIONANDO AgenteGerenciadorDeAnaliseLLM_ADK.tools ---\n")

    settings.logger.info(f"  Ferramentas Disponíveis (coletado): {tool_names_for_log}")

    settings.logger.info("\n--- SIMULANDO EXECUÇÃO DO AGENTE (CHAMADAS DIRETAS À FERRAMENTA DE BUSCA) ---")
    
    # Mock ToolContext (não é estritamente necessário para esta ferramenta, mas é bom ter para consistência)
    class SimpleTestToolContext:
        def __init__(self):
            self.state = {} 

    mock_ctx_manager = SimpleTestToolContext() 
    
    settings.logger.info(f"MockToolContext inicializado para simulação de teste. Estado inicial: {mock_ctx_manager.state}")

    # --- Teste: Buscar artigos pendentes ---
    settings.logger.info("\nSimulando busca por 3 artigos pendentes:")
    result_fetch_articles = fetch_articles_tool_adk_instance.func(
        limit=3
    )
    settings.logger.info(f"Resultado da busca: {json.dumps(result_fetch_articles, indent=2, ensure_ascii=False)}")

    settings.logger.info("\n--- Fim do Teste Standalone do Agente Gerenciador de Análise LLM ---")