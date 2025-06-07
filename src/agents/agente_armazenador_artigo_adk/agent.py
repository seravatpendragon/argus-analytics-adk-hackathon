# src/agents/agente_armazenador_artigo_adk/agent.py

import os
import sys
from pathlib import Path
import json
from datetime import datetime
import logging

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent
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
    
    # Importa a ferramenta de persistência
    from .tools.tool_persist_data import tool_persist_news_or_cvm_document

    # Importa o prompt local
    from . import prompt as agente_prompt

    # Fallback do logger se settings.logger não estiver disponível
    if not hasattr(settings, 'logger'):
        import logging
        log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        settings.logger = logging.getLogger("agente_armazenador_artigo_adk_fb_logger")
        settings.logger.info("Logger fallback inicializado em agent.py.")
    settings.logger.info("Módulos do projeto e ADK importados com sucesso para AgenteArmazenadorArtigo_ADK.")
except ImportError as e:
    settings.logger.info(f"Erro CRÍTICO em agent.py (AgenteArmazenadorArtigo_ADK) ao importar módulos: {e}")
    settings.logger.info(f"PROJECT_ROOT calculado: {PROJECT_ROOT}")
    settings.logger.info(f"sys.path atual: {sys.path}")
    if 'settings' not in locals() and 'settings' not in globals():
        import logging; logging.basicConfig(level=logging.INFO)
        _fb_logger = logging.getLogger("agent_armazenador_NO_SETTINGS_logger")
        settings = type('SettingsFallback', (), {'logger': _fb_logger})() # type: ignore
    sys.exit(1) # Saia se os imports críticos falharem
except Exception as e:
    settings.logger.info(f"Erro INESPERADO durante imports iniciais em agent.py (AgenteArmazenadorArtigo_ADK): {e}")
    if 'settings' not in locals() and 'settings' not in globals():
        import logging; logging.basicConfig(level=logging.INFO)
        _fb_logger = logging.getLogger("agent_armazenador_NO_SETTINGS_logger2")
        settings = type('SettingsFallback', (), {'logger': _fb_logger})() # type: ignore
    sys.exit(1)

# --- Definição do Modelo LLM a ser usado por este agente ---
MODELO_LLM_AGENTE = "gemini-2.0-flash-001" 
settings.logger.info(f"Modelo LLM para AgenteArmazenadorArtigo_ADK: {MODELO_LLM_AGENTE}")

# --- Envolver a função de persistência com FunctionTool ---
persist_tool_adk_instance = FunctionTool(func=tool_persist_news_or_cvm_document)

# --- Definição do Agente ---
AgenteArmazenadorArtigo_ADK = Agent(
    name="agente_armazenador_artigo_adk_v1",
    model=MODELO_LLM_AGENTE,
    description=(
        "Agente responsável por persistir metadados de artigos de notícias e documentos regulatórios "
        "na tabela NewsArticles do banco de dados unificado."
    ),
    instruction=agente_prompt.PROMPT,
    tools=[
        persist_tool_adk_instance, # A ferramenta que faz a persistência
    ],
)

if __name__ == '__main__':
    # Este bloco é para um teste muito básico da definição do agente e uma simulação
    # de como o agente usaria sua ferramenta, sem usar o ADK Runner.
    
    settings.logger.info(f"--- Teste Standalone da Definição e Fluxo Simulado do Agente: {AgenteArmazenadorArtigo_ADK.name} ---")
    settings.logger.info(f"  Modelo Configurado: {MODELO_LLM_AGENTE}")

    # --- DEBUG: INSPECIONANDO AgenteArmazenadorArtigo_ADK.tools ---
    settings.logger.info("\n--- DEBUG: INSPECIONANDO AgenteArmazenadorArtigo_ADK.tools ---")
    tool_names_for_log = [] 
    if hasattr(AgenteArmazenadorArtigo_ADK, 'tools') and AgenteArmazenadorArtigo_ADK.tools is not None:
        settings.logger.info(f"Tipo de AgenteArmazenadorArtigo_ADK.tools: {type(AgenteArmazenadorArtigo_ADK.tools)}")
        if isinstance(AgenteArmazenadorArtigo_ADK.tools, list):
            settings.logger.info(f"Número de ferramentas: {len(AgenteArmazenadorArtigo_ADK.tools)}")
            for idx, tool_item in enumerate(AgenteArmazenadorArtigo_ADK.tools):
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
            settings.logger.info("AgenteArmazenadorArtigo_ADK.tools NÃO é uma lista.")
    else:
        settings.logger.info("AgenteArmazenadorArtigo_ADK NÃO possui atributo 'tools' ou é None.")
    settings.logger.info("--- FIM DEBUG: INSPECIONANDO AgenteArmazenadorArtigo_ADK.tools ---\n")

    settings.logger.info(f"  Ferramentas Disponíveis (coletado): {tool_names_for_log}")

    settings.logger.info("\n--- SIMULANDO EXECUÇÃO DO AGENTE (CHAMADAS DIRETAS À FERRAMENTA DE PERSISTÊNCIA) ---")
    
    # Mock ToolContext para a ferramenta de persistência
    class SimpleTestToolContext:
        def __init__(self):
            self.state = {} 

    mock_ctx_persist = SimpleTestToolContext() 
    
    settings.logger.info(f"MockToolContext inicializado para simulação de teste. Estado inicial: {mock_ctx_persist.state}")

    # --- Dados de Teste: Notícia NewsAPI ---
    news_article_data = {
        "source_type": "NewsAPI",
        "title": "PETR4 Anuncia Novo Projeto de Exploração no Pré-Sal",
        "url": "http://exemplo.com/noticia-petr4-exploracao",
        "publishedAt": "2025-06-03T14:30:00Z",
        "description": "A Petrobras divulgou planos para um ambicioso projeto de exploração na bacia de Santos, com potencial para aumentar significativamente suas reservas.",
        "source": {"id": "agencia-de-noticias", "name": "Agência de Notícias Teste"}, 
        "company_cvm_code": "9512", # <-- ADICIONADO AQUI
        "full_text": "Texto completo da notícia sobre o novo projeto de exploração da PETR4 no pré-sal. Detalhes sobre o investimento e o cronograma previsto para as operações."
    }
    settings.logger.info("\nSimulando persistência de NOTÍCIA (NewsAPI):")
    result_news = persist_tool_adk_instance.func(article_data=news_article_data, tool_context=mock_ctx_persist)
    settings.logger.info(f"Resultado da persistência de Notícia: {json.dumps(result_news, indent=2)}")

    # --- Dados de Teste: Documento CVM (IPE) ---
    cvm_document_data = {
        "source_type": "CVM_IPE",
        "title": "Fato Relevante: Acordo de Parceria Estratégica com Empresa X",
        "document_url": "https://www.rad.cvm.gov.br/documento_cvm_acordo_petr4.pdf",
        "publication_date_iso": "2025-06-01T10:00:00+00:00",
        "document_type": "Fato Relevante",
        "protocol_id": "009512IPE20250601ACORDO123",
        "company_cvm_code": "9512",
        "company_name": "PETRÓLEO BRASILEIRO S.A. - PETROBRAS",
        "source_main_file": "ipe_cia_aberta_2025.zip",
        "full_text": "Conteúdo integral do Fato Relevante sobre o acordo de parceria estratégica da Petrobras."
    }
    settings.logger.info("\nSimulando persistência de DOCUMENTO CVM (IPE):")
    result_cvm = persist_tool_adk_instance.func(article_data=cvm_document_data, tool_context=mock_ctx_persist)
    settings.logger.info(f"Resultado da persistência de Documento CVM: {json.dumps(result_cvm, indent=2)}")

    settings.logger.info("\n--- Fim do Teste Standalone do Agente Armazenador de Artigos ---")