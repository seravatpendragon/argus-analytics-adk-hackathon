# src/agents/agente_de_fonte_noticia_adk/agent.py

import os
import sys
from pathlib import Path
import json
from datetime import datetime
import logging

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent # Sobe 3 níveis
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
    
    # Importa a ferramenta de persistência de fonte
    from .tools.tool_ensure_news_source_in_db import tool_ensure_news_source_in_db

    # Importa o prompt local
    from . import prompt as agente_prompt

    # Fallback do logger se settings.logger não estiver disponível
    if not hasattr(settings, 'logger'):
        import logging
        log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        settings.logger = logging.getLogger("agente_de_fonte_noticia_adk_fb_logger")
        settings.logger.info("Logger fallback inicializado em agent.py.")
    settings.logger.info("Módulos do projeto e ADK importados com sucesso para AgenteDeFonteNoticia_ADK.")
except ImportError as e:
    settings.logger.error(f"Erro CRÍTICO em agent.py (AgenteDeFonteNoticia_ADK) ao importar módulos: {e}")
    settings.logger.error(f"PROJECT_ROOT calculado: {PROJECT_ROOT}")
    settings.logger.error(f"sys.path atual: {sys.path}")
    sys.exit(1)
except Exception as e:
    settings.logger.error(f"Erro INESPERADO durante imports iniciais em agent.py (AgenteDeFonteNoticia_ADK): {e}")
    sys.exit(1)

# --- Definição do Modelo LLM a ser usado por este agente ---
MODELO_LLM_AGENTE = "gemini-2.0-flash-001" 
settings.logger.info(f"Modelo LLM para AgenteDeFonteNoticia_ADK: {MODELO_LLM_AGENTE}")

# --- Envolver a função de persistência de fonte com FunctionTool ---
ensure_source_tool_adk_instance = FunctionTool(func=tool_ensure_news_source_in_db)

# --- Definição do Agente ---
AgenteDeFonteNoticia_ADK = Agent(
    name="agente_de_fonte_noticia_adk_v1",
    model=MODELO_LLM_AGENTE,
    description=(
        "Agente responsável por garantir que as fontes de notícias estejam registradas no banco de dados "
        "e retornar seus IDs únicos para vinculação com os artigos."
    ),
    instruction=agente_prompt.PROMPT,
    tools=[
        ensure_source_tool_adk_instance, # A ferramenta que garante a fonte no DB
    ],
)

if __name__ == '__main__':
    # Este bloco é para um teste muito básico da definição do agente e uma simulação
    # de como o agente usaria sua ferramenta, sem usar o ADK Runner.
    
    settings.logger.info(f"--- Teste Standalone da Definição e Fluxo Simulado do Agente: {AgenteDeFonteNoticia_ADK.name} ---")
    settings.logger.info(f"  Modelo Configurado: {AgenteDeFonteNoticia_ADK.model}")

    # --- DEBUG: INSPECIONANDO AgenteDeFonteNoticia_ADK.tools ---
    settings.logger.info("\n--- DEBUG: INSPECIONANDO AgenteDeFonteNoticia_ADK.tools ---")
    tool_names_for_log = [] 
    if hasattr(AgenteDeFonteNoticia_ADK, 'tools') and AgenteDeFonteNoticia_ADK.tools is not None:
        settings.logger.info(f"Tipo de AgenteDeFonteNoticia_ADK.tools: {type(AgenteDeFonteNoticia_ADK.tools)}")
        if isinstance(AgenteDeFonteNoticia_ADK.tools, list):
            settings.logger.info(f"Número de ferramentas: {len(AgenteDeFonteNoticia_ADK.tools)}")
            for idx, tool_item in enumerate(AgenteDeFonteNoticia_ADK.tools):
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
            settings.logger.info("AgenteDeFonteNoticia_ADK.tools NÃO é uma lista.")
    else:
        settings.logger.info("AgenteDeFonteNoticia_ADK NÃO possui atributo 'tools' ou é None.")
    settings.logger.info("--- FIM DEBUG: INSPECIONANDO AgenteDeFonteNoticia_ADK.tools ---\n")

    settings.logger.info(f"  Ferramentas Disponíveis (coletado): {tool_names_for_log}")

    settings.logger.info("\n--- SIMULANDO EXECUÇÃO DO AGENTE (CHAMADAS DIRETAS À FERRAMENTA DE FONTE) ---")
    
    # Mock ToolContext (não é estritamente necessário para esta ferramenta, mas é bom ter para consistência)
    class SimpleTestToolContext:
        def __init__(self):
            self.state = {} 

    mock_ctx_source = SimpleTestToolContext() 
    
    settings.logger.info(f"MockToolContext inicializado para simulação de teste. Estado inicial: {mock_ctx_source.state}")

    # --- Dados de Credibilidade de Teste (como viriam do AgenteDeCredibilidade_ADK) ---
    # Para este teste, precisamos carregar os dados de credibilidade aqui também
    # para passar para a ferramenta.
    _temp_loaded_credibility_data = {}
    try:
        # Caminho para news_source_domain.json
        file_path = PROJECT_ROOT / "config" / "news_source_domain.json"
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            for domain_key, details in raw_data.items():
                source_name = details.get("source_name") or domain_key
                _temp_loaded_credibility_data[source_name] = details
                if 'domain' not in details:
                    details['domain'] = domain_key
        settings.logger.info("Dados de credibilidade carregados para teste de fonte.")
    except Exception as e:
        settings.logger.error(f"Erro ao carregar news_source_domain.json para teste de fonte: {e}")
        _temp_loaded_credibility_data = {} # Garante que seja um dicionário vazio

    # Teste 1: Fonte Conhecida (InfoMoney)
    settings.logger.info("\nSimulando garantia de fonte CONHECIDA (InfoMoney):")
    result_known_source = ensure_source_tool_adk_instance.func(
        source_name_curated="InfoMoney",
        source_domain="infomoney.com.br",
        base_credibility_score=0.86, # Score vindo do AgenteDeCredibilidade_ADK
        loaded_credibility_data=_temp_loaded_credibility_data,
        tool_context=mock_ctx_source
    )
    settings.logger.info(f"Resultado garantia InfoMoney: {json.dumps(result_known_source, indent=2, ensure_ascii=False)}")

    # Teste 2: Fonte Conhecida (CVM - Regulatórios)
    settings.logger.info("\nSimulando garantia de fonte CONHECIDA (CVM - Regulatórios):")
    result_cvm_source = ensure_source_tool_adk_instance.func(
        source_name_curated="Comissão de Valores Mobiliários", # Nome curado do JSON
        source_domain="cvm.gov.br", # Domínio real da CVM
        base_credibility_score=1.0, # Score vindo do AgenteDeCredibilidade_ADK
        loaded_credibility_data=_temp_loaded_credibility_data,
        tool_context=mock_ctx_source
    )
    settings.logger.info(f"Resultado garantia CVM: {json.dumps(result_cvm_source, indent=2, ensure_ascii=False)}")

    # Teste 3: Fonte Desconhecida (Blog Pessoal)
    settings.logger.info("\nSimulando garantia de fonte DESCONHECIDA (blogpessoal.com):")
    result_unknown_source = ensure_source_tool_adk_instance.func(
        source_name_curated="Blog Pessoal do Zé",
        source_domain="blogpessoal.com",
        base_credibility_score=0.6, # Score padrão
        loaded_credibility_data=_temp_loaded_credibility_data,
        tool_context=mock_ctx_source
    )
    settings.logger.info(f"Resultado garantia Blog Pessoal: {json.dumps(result_unknown_source, indent=2, ensure_ascii=False)}")

    settings.logger.info("\n--- Fim do Teste Standalone do Agente de Fonte de Notícia ---")