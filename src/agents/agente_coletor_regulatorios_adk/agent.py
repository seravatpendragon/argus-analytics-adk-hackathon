# src/agents/agente_coletor_regulatorios_adk/agent.py

import os
import sys
from pathlib import Path
import json # Para o bloco de teste
from datetime import datetime # Para o bloco de teste
import logging

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    # Sobe: agente_coletor_regulatorios_adk -> agents -> src -> PROJECT_ROOT
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    # Fallback para ambientes onde __file__ pode não estar definido (ex: alguns REPLs interativos)
    PROJECT_ROOT = Path(os.getcwd())
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

try:
    from config import settings
    from google.adk.agents import Agent # Classe base do ADK [cite: 1]
    from google.adk.tools import FunctionTool # Importante para envolver as ferramentas [cite: 148]
    
    # Para o MockToolContext no bloco de teste, importamos o real se ADK estiver acessível
    try:
        # Tenta importar o ToolContext real do ADK.
        # O ToolContext é uma classe importante que dá acesso ao estado da sessão, informações do agente, etc. [cite: 470, 471]
        from google.adk.tools.tool_context import ToolContext
        _TOOL_CONTEXT_IMPORTED_SUCCESSFULLY = True
    except ImportError:
        # Se ToolContext não puder ser importado (ex: ADK não totalmente instalado ou caminho incorreto),
        # define uma classe dummy para que o script de teste não quebre.
        # Esta classe dummy simula apenas o atributo 'state' que a ferramenta de processamento IPE precisa.
        settings.logger.info("AVISO (agent.py): google.adk.tools.tool_context.ToolContext não pôde ser importado. Usando MockToolContext simples.")
        class ToolContext: # type: ignore
            def __init__(self):
                self.state = {}
            pass
        _TOOL_CONTEXT_IMPORTED_SUCCESSFULLY = False

    # Importa as FUNÇÕES das ferramentas da subpasta 'tools'
    from .tools.ferramenta_downloader_cvm import tool_download_cvm_data
    from .tools.ferramenta_processador_ipe import tool_process_cvm_ipe_local
    # Importa o prompt e constantes do arquivo prompt.py local
    from . import prompt as agente_prompt

    # Fallback do logger se settings.logger não estiver disponível
    if not hasattr(settings, 'logger'):
        import logging
        log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        settings.logger = logging.getLogger("agente_coletor_regulatorios_adk_fb_logger")
        settings.logger.info("Logger fallback inicializado em agent.py.")
    settings.logger.info("Módulos do projeto e ADK importados com sucesso para AgenteColetorRegulatorios_ADK.")
except ImportError as e:
    settings.logger.info(f"Erro CRÍTICO em agent.py (AgenteColetorRegulatorios_ADK) ao importar módulos: {e}")
    settings.logger.info(f"PROJECT_ROOT calculado: {PROJECT_ROOT}")
    settings.logger.info(f"sys.path atual: {sys.path}")
    # Garante que 'settings' e 'ToolContext' existam para que o restante do script não quebre
    if 'settings' not in locals() and 'settings' not in globals():
        import logging; logging.basicConfig(level=logging.INFO)
        _fb_logger = logging.getLogger("agent_coletor_reg_NO_SETTINGS_logger")
        settings = type('SettingsFallback', (), {'logger': _fb_logger})() # type: ignore
    if 'ToolContext' not in globals() and 'ToolContext' not in locals():
        class ToolContext: # type: ignore
            def __init__(self):
                self.state = {}
            pass
        _TOOL_CONTEXT_IMPORTED_SUCCESSFULLY = False # Garante que a flag seja False em caso de erro de importação
    # sys.exit(1) # Comentado para permitir análise estática
except Exception as e:
    settings.logger.info(f"Erro INESPERADO durante imports iniciais em agent.py (AgenteColetorRegulatorios_ADK): {e}")
    # Garante que 'settings' e 'ToolContext' existam como fallback
    if 'settings' not in locals() and 'settings' not in globals():
        import logging; logging.basicConfig(level=logging.INFO)
        _fb_logger = logging.getLogger("agent_coletor_reg_NO_SETTINGS_logger2")
        settings = type('SettingsFallback', (), {'logger': _fb_logger})() # type: ignore
    if 'ToolContext' not in globals() and 'ToolContext' not in locals():
        class ToolContext: # type: ignore
            def __init__(self):
                self.state = {}
            pass
        _TOOL_CONTEXT_IMPORTED_SUCCESSFULLY = False # Garante que a flag seja False em caso de erro inesperado
    # sys.exit(1)

# --- Definição do Modelo LLM a ser usado por este agente ---
# Conforme sua especificação. Verifique se é o identificador correto para ADK/Vertex AI.
MODELO_LLM_AGENTE = "gemini-2.0-flash-001" 
# MODELO_LLM_AGENTE = getattr(settings, "GEMINI_MODEL_NAME_FOR_ADK_AGENTS", "gemini-2.0-flash-001") # Alternativa via settings

settings.logger.info(f"Modelo LLM para AgenteColetorRegulatorios_ADK: {MODELO_LLM_AGENTE}")

# --- Envolver as funções das ferramentas com FunctionTool ---
# As docstrings das funções originais serão usadas pelo ADK para o LLM. [cite: 158]
# O 'name' da FunctionTool será inferido a partir do nome da função. [cite: 164]
download_cvm_tool_adk_instance = FunctionTool(func=tool_download_cvm_data) 
process_ipe_tool_adk_instance = FunctionTool(func=tool_process_cvm_ipe_local)

# --- Definição do Agente ---
AgenteColetorRegulatorios_ADK = Agent(
logger.info(f'Modelo LLM para o agente {Path(__file__).name} (AgenteColetorRegulatorios_ADK (Nome não extraído)): {MODELO_LLM_AGENTE}')
logger.info(f'Definição do Agente AgenteColetorRegulatorios_ADK (Nome não extraído) carregada com sucesso em {Path(__file__).name}.')
logger.info(f'Modelo LLM para o agente {Path(__file__).name}: {MODELO_LLM_AGENTE}')
logger.info(f'Definição do Agente {AgenteColetorRegulatorios_ADK.name} carregada com sucesso em {Path(__file__).name}.')
    logger.info(f'Modelo LLM para o agente {Path(__file__).name}: {MODELO_LLM_AGENTE}')
    logger.info(f'Definição do Agente {AgenteColetorRegulatorios_ADK.name} carregada com sucesso em {Path(__file__).name}.')
    logger.info(f'Modelo LLM para o agente {Path(__file__).name}: {MODELO_LLM_AGENTE}')
    logger.info(f'Definição do Agente {AgenteColetorRegulatorios_ADK.name} carregada com sucesso em {Path(__file__).name}.')
    logger.info(f'Modelo LLM para o agente {Path(__file__).name}: {MODELO_LLM_AGENTE}')
    logger.info(f'Definição do Agente {AgenteColetorRegulatorios_ADK.name} carregada com sucesso em {Path(__file__).name}.')
logger.info(f"Modelo LLM para o agente {Path(__file__).name}: {MODELO_LLM_AGENTE}")
logger.info(f"Definição do Agente {AgenteColetorRegulatorios_ADK.name} carregada com sucesso em {Path(__file__).name}.")
logger.info(f"Modelo LLM para o agente {Path(__file__).name}: {MODELO_LLM_AGENTE}")
logger.info(f"Definição do Agente {AgenteColetorRegulatorios_ADK.name} carregada com sucesso em {Path(__file__).name}.")
    name="agente_coletor_regulatorios_cvm_petr4_v1",
    model=MODELO_LLM_AGENTE,
    description=(
        "Agente especializado em coletar documentos regulatórios IPE (Informações Periódicas e Eventuais) "
        "da CVM para a empresa PETR4 (usando o CD_CVM da Petrobras). Ele baixa os arquivos anuais relevantes, "
        "processa-os para identificar novos Fatos Relevantes, Comunicados ao Mercado e Avisos aos Acionistas, "
        "e retorna os metadados desses novos documentos."
    ),
    instruction=agente_prompt.PROMPT,
    tools=[
        download_cvm_tool_adk_instance,    # Passa a instância de FunctionTool
        process_ipe_tool_adk_instance      # Passa a instância de FunctionTool
    ],
    # enable_dynamic_tool_schema=True, # Se o ADK tiver essa opção e suas ferramentas usarem Pydantic.
                                     # Para funções simples, geralmente não é necessário.
)

if __name__ == '__main__':
    # Este bloco é para um teste muito básico da definição do agente e uma simulação
    # de como o agente usaria suas ferramentas, seguindo o prompt.
    # Não é uma execução real do agente via ADK Runner.
    
    settings.logger.info(f"--- Teste Standalone da Definição e Fluxo Simulado do Agente: {AgenteColetorRegulatorios_ADK.name} ---")
    settings.logger.info(f"  Modelo Configurado: {AgenteColetorRegulatorios_ADK.model}")

    # --- DEBUG: INSPECIONANDO AgenteColetorRegulatorios_ADK.tools ---
    settings.logger.info("\n--- DEBUG: INSPECIONANDO AgenteColetorRegulatorios_ADK.tools ---")
    tool_names_for_log = [] # Lista para coletar os nomes das ferramentas para o log principal
    if hasattr(AgenteColetorRegulatorios_ADK, 'tools') and AgenteColetorRegulatorios_ADK.tools is not None:
        settings.logger.info(f"Tipo de AgenteColetorRegulatorios_ADK.tools: {type(AgenteColetorRegulatorios_ADK.tools)}")
        if isinstance(AgenteColetorRegulatorios_ADK.tools, list):
            settings.logger.info(f"Número de ferramentas: {len(AgenteColetorRegulatorios_ADK.tools)}")
            for idx, tool_item in enumerate(AgenteColetorRegulatorios_ADK.tools):
                settings.logger.info(f"  Ferramenta {idx}: {tool_item}")
                settings.logger.info(f"    Tipo da Ferramenta {idx}: {type(tool_item)}")
                settings.logger.info(f"    Possui atributo 'name'? {'Sim' if hasattr(tool_item, 'name') else 'NÃO'}")
                
                tool_name = f"UNKNOWN_TOOL_{idx}" # Default fallback para o nome
                if hasattr(tool_item, 'name'):
                    tool_name = tool_item.name
                    settings.logger.info(f"      tool_item.name: {tool_name}")
                elif hasattr(tool_item, 'func') and hasattr(tool_item.func, '__name__'): # Para casos onde FunctionTool não tem .name direto, mas a função wrapped tem
                    tool_name = tool_item.func.__name__
                    settings.logger.info(f"      tool_item.func.__name__: {tool_name}")
                elif hasattr(tool_item, '__name__'): # Para o caso de ser a função pura
                    tool_name = tool_item.__name__
                    settings.logger.info(f"      tool_item.__name__: {tool_name}")
                
                tool_names_for_log.append(tool_name)

                if hasattr(tool_item, 'func'): # Sempre mostra o func se existir, para verificar o wrapper
                    settings.logger.info(f"      tool_item.func: {tool_item.func}")
                    settings.logger.info(f"      tool_item.func.__name__: {tool_item.func.__name__}")
        else:
            settings.logger.info("AgenteColetorRegulatorios_ADK.tools NÃO é uma lista.")
    else:
        settings.logger.info("AgenteColetorRegulatorios_ADK NÃO possui atributo 'tools' ou é None.")
    settings.logger.info("--- FIM DEBUG: INSPECIONANDO AgenteColetorRegulatorios_ADK.tools ---\n")

    # Agora, a linha que causava o erro deve funcionar, usando a lista 'tool_names_for_log'
    settings.logger.info(f"  Ferramentas Disponíveis (coletado): {tool_names_for_log}")
    settings.logger.info(f"  CD_CVM_PETROBRAS usado no prompt: {agente_prompt.CD_CVM_PETROBRAS}")
    settings.logger.info(f"  Anos no prompt: {agente_prompt.ANO_CORRENTE_STR}, {agente_prompt.ANO_ANTERIOR_STR}")
    # Certifique-se de que a variável esteja correta no prompt.py
    settings.logger.info(f"  Tipos de Documento CVM para Download no prompt: {agente_prompt.TIPOS_ARQUIVO_CVM_DOWNLOAD}")

    settings.logger.info("\n--- SIMULANDO EXECUÇÃO DO AGENTE (CHAMADAS DIRETAS ÀS FERRAMENTAS COMO O LLM FARIA) ---")
    
    if not (PROJECT_ROOT / "data" / "raw" / "cvm").exists():
        (PROJECT_ROOT / "data" / "raw" / "cvm").mkdir(parents=True, exist_ok=True)
        settings.logger.info(f"Pasta de dados criada em: {PROJECT_ROOT / 'data' / 'raw' / 'cvm'}")

    # 1. Simular chamada ao downloader (Passo 1 do Prompt)
    anos_para_simulacao = [int(agente_prompt.ANO_CORRENTE_STR)] 
    # anos_para_simulacao.append(int(agente_prompt.ANO_ANTERIOR_STR)) # Adicione para testar ano anterior
    tipos_doc_ids_para_simulacao = agente_prompt.TIPOS_ARQUIVO_CVM_DOWNLOAD
    
    # Acessa o nome da ferramenta para o log usando a instância FunctionTool diretamente
    settings.logger.info(f"Simulando {download_cvm_tool_adk_instance.name} com anos={anos_para_simulacao}, tipos_doc_ids={tipos_doc_ids_para_simulacao}")
    # Acessa a função original através do atributo .func do FunctionTool para teste direto
    resultado_download_dict = download_cvm_tool_adk_instance.func(anos=anos_para_simulacao, tipos_doc_ids=tipos_doc_ids_para_simulacao)
    settings.logger.info(f"Resultado simulado do download: {json.dumps(resultado_download_dict, indent=2)}")

    mapa_arquivos_locais = resultado_download_dict.get("downloaded_files_map", {})
    todos_novos_documentos_simulados = []
    
    # Mock ToolContext para a ferramenta de processamento
    # Crie uma classe mock simples que simula apenas o atributo .state que a ferramenta de processamento IPE precisa.
    class SimpleTestToolContext:
        def __init__(self):
            self.state = {} # A ferramenta de processamento IPE acessa self.state

    mock_ctx_processador = SimpleTestToolContext() # <--- MODIFICADO AQUI
    
    settings.logger.info(f"MockToolContext inicializado para simulação de teste. Estado inicial: {mock_ctx_processador.state}")

    # Simular processamento para os arquivos IPE baixados (Passos 2 e 3 do Prompt)
    anos_no_prompt_para_processar = [agente_prompt.ANO_CORRENTE_STR, agente_prompt.ANO_ANTERIOR_STR]

    for ano_str_prompt in anos_no_prompt_para_processar:
        # Se você está simulando apenas o ano corrente para o download,
        # pule o processamento do ano anterior se ele não foi baixado.
        if int(ano_str_prompt) not in anos_para_simulacao: 
            settings.logger.warning(f"Pulando simulação de processamento para ano {ano_str_prompt}, pois não foi incluído no download simulado.")
            continue

        chave_zip_ipe = f"IPE_CIA_ABERTA_{ano_str_prompt}_zip" # Chave consistente com o nome do arquivo no mapa
        if chave_zip_ipe in mapa_arquivos_locais and isinstance(mapa_arquivos_locais[chave_zip_ipe], str) and not mapa_arquivos_locais[chave_zip_ipe].startswith("ERRO"):
            caminho_zip = mapa_arquivos_locais[chave_zip_ipe]
            settings.logger.info(f"\nSimulando {process_ipe_tool_adk_instance.name} para {caminho_zip} (PETR4 CD_CVM: {agente_prompt.CD_CVM_PETROBRAS})")
            
            # Acessa a função original através do atributo .func do FunctionTool para teste direto
            resultado_processamento_dict = process_ipe_tool_adk_instance.func(
                caminho_zip_local=caminho_zip,
                cd_cvm_empresa=agente_prompt.CD_CVM_PETROBRAS,
                tool_context=mock_ctx_processador # Passa o ToolContext mock
            )
            if resultado_processamento_dict.get("status") == "success":
                novos_docs_ano = resultado_processamento_dict.get("novos_documentos", [])
                todos_novos_documentos_simulados.extend(novos_docs_ano)
                settings.logger.info(f"  Documentos encontrados para o ano {ano_str_prompt}: {len(novos_docs_ano)}")
            else:
                settings.logger.error(f"  Erro ao processar IPE para o ano {ano_str_prompt}: {resultado_processamento_dict.get('error_message')}")
        else:
            settings.logger.warning(f"Não foi possível simular processamento para IPE {ano_str_prompt} - arquivo não baixado ou erro no download (chave: {chave_zip_ipe}).")
    
    settings.logger.info(f"\n--- SIMULAÇÃO DO AGENTE: Resultado Final Consolidado (primeiros 3 docs) ---")
    if todos_novos_documentos_simulados:
        for idx, doc in enumerate(todos_novos_documentos_simulados[:3]):
            settings.logger.info(f"Documento {idx+1}: {json.dumps(doc, indent=2, ensure_ascii=False)}")
        settings.logger.info(f"(Total de {len(todos_novos_documentos_simulados)} documentos simulados como coletados)")
    else:
        settings.logger.info("Nenhum novo documento foi simulado como coletado.")
    
    settings.logger.info("\n--- Fim do Teste Standalone da Definição do Agente ---")