# src/agents/agente_pre_processador_noticia_adk/agent.py

import os
import sys
from pathlib import Path
import json
from datetime import datetime

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent # Sobe 3 níveis (agente_pre_processador_noticia_adk -> agents -> src -> PROJECT_ROOT)
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    print(f"PROJECT_ROOT ({PROJECT_ROOT}) foi adicionado/confirmado no sys.path para agent.py (AgentePreProcessadorNoticia).")
except NameError:
    PROJECT_ROOT = Path(os.getcwd())
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    print(f"AVISO (agent.py AgentePreProcessadorNoticia): __file__ não definido. Usando PROJECT_ROOT como: {PROJECT_ROOT}")

try:
    from config import settings
    from google.adk.agents import Agent
    from google.adk.tools import FunctionTool
    
    # Importa a ferramenta de pré-processamento
    from .tools.tool_preprocess_metadata import tool_preprocess_article_metadata

    # Importa o prompt local
    from . import prompt as agente_prompt

    # Fallback do logger se settings.logger não estiver disponível
    if not hasattr(settings, 'logger'):
        import logging
        log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        settings.logger = logging.getLogger("agente_pre_processador_noticia_adk_fb_logger")
        settings.logger.info("Logger fallback inicializado em agent.py.")
    print("Módulos do projeto e ADK importados com sucesso para AgentePreProcessadorNoticia_ADK.")
except ImportError as e:
    settings.logger.error(f"Erro CRÍTICO em agent.py (AgentePreProcessadorNoticia_ADK) ao importar módulos: {e}")
    settings.logger.error(f"PROJECT_ROOT calculado: {PROJECT_ROOT}")
    settings.logger.error(f"sys.path atual: {sys.path}")
    sys.exit(1)
except Exception as e:
    settings.logger.error(f"Erro INESPERADO durante imports iniciais em agent.py (AgentePreProcessadorNoticia_ADK): {e}")
    sys.exit(1)

# --- Definição do Modelo LLM a ser usado por este agente ---
MODELO_LLM_AGENTE = "gemini-2.0-flash-001" 
settings.logger.info(f"Modelo LLM para AgentePreProcessadorNoticia_ADK: {MODELO_LLM_AGENTE}")

# --- Envolver a função de pré-processamento com FunctionTool ---
preprocess_tool_adk_instance = FunctionTool(func=tool_preprocess_article_metadata)

# --- Definição do Agente ---
AgentePreProcessadorNoticia_ADK = Agent(
    name="agente_pre_processador_noticia_adk_v1",
    model=MODELO_LLM_AGENTE,
    description=(
        "Agente responsável por pré-processar e padronizar metadados brutos de artigos de notícias "
        "e documentos regulatórios para as próximas etapas do pipeline."
    ),
    instruction=agente_prompt.PROMPT,
    tools=[
        preprocess_tool_adk_instance, # A ferramenta que faz o pré-processamento
    ],
)

if __name__ == '__main__':
    # Este bloco é para um teste muito básico da definição do agente e uma simulação
    # de como o agente usaria sua ferramenta, sem usar o ADK Runner.
    
    settings.logger.info(f"--- Teste Standalone da Definição e Fluxo Simulado do Agente: {AgentePreProcessadorNoticia_ADK.name} ---")
    settings.logger.info(f"  Modelo Configurado: {AgentePreProcessadorNoticia_ADK.model}")

    # --- DEBUG: INSPECIONANDO AgentePreProcessadorNoticia_ADK.tools ---
    print("\n--- DEBUG: INSPECIONANDO AgentePreProcessadorNoticia_ADK.tools ---")
    tool_names_for_log = [] 
    if hasattr(AgentePreProcessadorNoticia_ADK, 'tools') and AgentePreProcessadorNoticia_ADK.tools is not None:
        print(f"Tipo de AgentePreProcessadorNoticia_ADK.tools: {type(AgentePreProcessadorNoticia_ADK.tools)}")
        if isinstance(AgentePreProcessadorNoticia_ADK.tools, list):
            print(f"Número de ferramentas: {len(AgentePreProcessadorNoticia_ADK.tools)}")
            for idx, tool_item in enumerate(AgentePreProcessadorNoticia_ADK.tools):
                print(f"  Ferramenta {idx}: {tool_item}")
                print(f"    Tipo da Ferramenta {idx}: {type(tool_item)}")
                print(f"    Possui atributo 'name'? {'Sim' if hasattr(tool_item, 'name') else 'NÃO'}")
                
                tool_name = f"UNKNOWN_TOOL_{idx}" 
                if hasattr(tool_item, 'name'):
                    tool_name = tool_item.name
                    print(f"      tool_item.name: {tool_name}")
                elif hasattr(tool_item, 'func') and hasattr(tool_item.func, '__name__'): 
                    tool_name = tool_item.func.__name__
                    print(f"      tool_item.func.__name__: {tool_name}")
                elif hasattr(tool_item, '__name__'): 
                    tool_name = tool_item.__name__
                    print(f"      tool_item.__name__: {tool_item.__name__}")
                
                tool_names_for_log.append(tool_name)

                if hasattr(tool_item, 'func'): 
                    print(f"      tool_item.func: {tool_item.func}")
                    print(f"      tool_item.func.__name__: {tool_item.func.__name__}")
        else:
            print("AgentePreProcessadorNoticia_ADK.tools NÃO é uma lista.")
    else:
        print("AgentePreProcessadorNoticia_ADK NÃO possui atributo 'tools' ou é None.")
    print("--- FIM DEBUG: INSPECIONANDO AgentePreProcessadorNoticia_ADK.tools ---\n")

    settings.logger.info(f"  Ferramentas Disponíveis (coletado): {tool_names_for_log}")

    settings.logger.info("\n--- SIMULANDO EXECUÇÃO DO AGENTE (CHAMADAS DIRETAS À FERRAMENTA DE PRÉ-PROCESSAMENTO) ---")
    
    # Mock ToolContext (não é estritamente necessário para esta ferramenta, mas é bom ter para consistência)
    class SimpleTestToolContext:
        def __init__(self):
            self.state = {} 

    mock_ctx_preprocess = SimpleTestToolContext() 
    
    settings.logger.info(f"MockToolContext inicializado para simulação de teste. Estado inicial: {mock_ctx_preprocess.state}")

    # --- Dados de Teste 1: Notícia NewsAPI Bruta ---
    raw_newsapi_data = {
        "source_type": "NewsAPI",
        "title": "Petrobras avalia nova rota de escoamento para gás natural do pré-sal, diz fonte",
        "url": "https://www.infomoney.com.br/mercados/petrobras-avalia-nova-rota-de-escoamento-para-gas-natural-do-pre-sal-diz-fonte/",
        "author": "Reuters",
        "publishedAt": "2025-06-03T10:30:00Z",
        "description": "A Petrobras está estudando alternativas para escoar a produção de gás natural...",
        "content": "Conteúdo completo do artigo da InfoMoney...",
        "source": {"id": "info-money", "name": "InfoMoney"}
    }
    settings.logger.info("\nSimulando pré-processamento de NOTÍCIA (NewsAPI):")
    processed_news_data = preprocess_tool_adk_instance.func(raw_article_data=raw_newsapi_data)
    settings.logger.info(f"Resultado do pré-processamento de Notícia: {json.dumps(processed_news_data, indent=2, ensure_ascii=False)}")

    # --- Dados de Teste 2: Documento CVM (IPE) Bruto (como viria do Coletor Regulatórios) ---
    raw_cvm_data = {
        "source_type": "CVM_IPE",
        "title": "COMUNICADO AO MERCADO: Detalhes sobre a recompra de ações da PETR4",
        "document_url": "https://www.rad.cvm.gov.br/ENET/frmDownloadDocumento.aspx?cod=12345",
        "publication_date_iso": "2025-05-28T14:00:00+00:00",
        "document_type": "Comunicado ao Mercado",
        "protocol_id": "009512CVM20250528RECOMPRA",
        "company_cvm_code": "9512",
        "company_name": "PETRÓLEO BRASILEIRO S.A. - PETROBRAS",
        "source_main_file": "ipe_cia_aberta_2025.zip",
        "full_text": "Este é o texto integral do comunicado ao mercado sobre a recompra de ações da Petrobras."
    }
    settings.logger.info("\nSimulando pré-processamento de DOCUMENTO CVM (IPE):")
    processed_cvm_data = preprocess_tool_adk_instance.func(raw_article_data=raw_cvm_data)
    settings.logger.info(f"Resultado do pré-processamento de Documento CVM: {json.dumps(processed_cvm_data, indent=2, ensure_ascii=False)}")

    # --- Dados de Teste 3: Notícia RSS Bruta ---
    raw_rss_data = {
        "source_type": "RSS",
        "title": "Analistas veem oportunidade em PETR4 após balanço do 1T",
        "link": "https://www.seudinheiro.com/noticias/analistas-petr4-balanco-1t/",
        "summary": "Sumário da notícia do Seu Dinheiro sobre o balanço da Petrobras no primeiro trimestre.",
        "published_parsed_iso": "2025-06-02T09:00:00Z",
        "source_name": "Seu Dinheiro",
        "feed_url": "https://www.seudinheiro.com/feed/"
    }
    settings.logger.info("\nSimulando pré-processamento de NOTÍCIA (RSS):")
    processed_rss_data = preprocess_tool_adk_instance.func(raw_article_data=raw_rss_data)
    settings.logger.info(f"Resultado do pré-processamento de Notícia RSS: {json.dumps(processed_rss_data, indent=2, ensure_ascii=False)}")


    settings.logger.info("\n--- Fim do Teste Standalone do Agente Pré-Processador de Notícias ---")