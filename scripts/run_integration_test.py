# run_integration_test.py

import os
import sys
from pathlib import Path
import json
from datetime import datetime

# --- Configuração de Caminhos para Imports do Projeto ---
# Adiciona o diretório raiz do projeto ao sys.path
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    # CORREÇÃO CRÍTICA AQUI: PROJECT_ROOT é o diretório PARENT de 'scripts'
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent 
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    print(f"PROJECT_ROOT ({PROJECT_ROOT}) foi adicionado/confirmado no sys.path para run_integration_test.py.")
except NameError:
    PROJECT_ROOT = Path(os.getcwd())
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    print(f"AVISO (run_integration_test.py): __file__ não definido. Usando PROJECT_ROOT como: {PROJECT_ROOT}")

# Adiciona a pasta 'src' ao sys.path para importar módulos internos
# Agora src_path será PROJECT_ROOT / "src", que é o caminho correto
src_path = PROJECT_ROOT / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
    print(f"src_path ({src_path}) foi adicionado/confirmado no sys.path.")

try:
    # Agora 'config' deve ser encontrado porque PROJECT_ROOT está no sys.path
    from config import settings
    
    # Importa as ferramentas e prompts dos agentes que vamos testar
    from agents.agente_coletor_regulatorios_adk.tools.ferramenta_downloader_cvm import tool_download_cvm_data
    from agents.agente_coletor_regulatorios_adk.tools.ferramenta_processador_ipe import tool_process_cvm_ipe_local
    from agents.agente_coletor_regulatorios_adk import prompt as coletor_prompt_config

    from agents.agente_armazenador_artigo_adk.tools.tool_persist_data import tool_persist_news_or_cvm_document

    # Importa ToolContext (real ou mock)
    try:
        from google.adk.tools.tool_context import ToolContext
    except ImportError:
        class ToolContext:
            def __init__(self):
                self.state = {}
            pass

    print("Módulos de agentes e ferramentas importados com sucesso.")

except ImportError as e:
    settings.logger.error(f"Erro CRÍTICO ao importar módulos em run_integration_test.py: {e}")
    settings.logger.error(f"Verifique se as pastas 'src/agents/agente_coletor_regulatorios_adk' e 'src/agents/agente_armazenador_artigo_adk' existem e contêm os arquivos necessários.")
    settings.logger.error(f"sys.path atual: {sys.path}")
    sys.exit(1)
except Exception as e:
    settings.logger.error(f"Erro INESPERADO durante imports iniciais em run_integration_test.py: {e}")
    sys.exit(1)

# Configuração do logger (se não estiver vindo de settings)
if not hasattr(settings, 'logger'):
    import logging
    log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_format)
    settings.logger = logging.getLogger("integration_test_logger")
    settings.logger.info("Logger fallback inicializado em run_integration_test.py.")


settings.logger.info("--- INICIANDO TESTE DE INTEGRAÇÃO SIMULADO: Coletor CVM -> Armazenador Artigo ---")

# --- Mock ToolContext para simular o estado da sessão ---
class SimpleTestToolContext:
    def __init__(self):
        self.state = {} 

mock_session_state_context = SimpleTestToolContext()
settings.logger.info(f"MockToolContext para estado da sessão inicializado. Estado: {mock_session_state_context.state}")


# --- 1. SIMULAR EXECUÇÃO DO AGENTE COLETOR REGULATÓRIOS (Coleta CVM) ---
settings.logger.info("\n--- FASE 1: Simulando Coleta de Documentos CVM ---")

# Garante que a pasta de download exista
cvm_raw_data_path = PROJECT_ROOT / "data" / "raw" / "cvm"
if not cvm_raw_data_path.exists():
    cvm_raw_data_path.mkdir(parents=True, exist_ok=True)
    settings.logger.info(f"Pasta de dados CVM criada em: {cvm_raw_data_path}")

anos_para_coleta = [int(coletor_prompt_config.ANO_CORRENTE_STR)]
tipos_doc_ids_para_coleta = coletor_prompt_config.TIPOS_ARQUIVO_CVM_DOWNLOAD

settings.logger.info(f"Chamando tool_download_cvm_data para anos={anos_para_coleta}, tipos_doc_ids={tipos_doc_ids_para_coleta}")
resultado_download = tool_download_cvm_data(anos=anos_para_coleta, tipos_doc_ids=tipos_doc_ids_para_coleta)
settings.logger.info(f"Resultado do download: {json.dumps(resultado_download, indent=2)}")

mapa_arquivos_locais = resultado_download.get("downloaded_files_map", {})
documentos_cvm_coletados = []

# Simular processamento para os arquivos IPE baixados
for ano_str_prompt in [coletor_prompt_config.ANO_CORRENTE_STR, coletor_prompt_config.ANO_ANTERIOR_STR]:
    if int(ano_str_prompt) not in anos_para_coleta:
        settings.logger.warning(f"Pulando processamento para ano {ano_str_prompt}, não incluído na coleta.")
        continue

    chave_zip_ipe = f"IPE_CIA_ABERTA_{ano_str_prompt}_zip"
    if chave_zip_ipe in mapa_arquivos_locais and isinstance(mapa_arquivos_locais[chave_zip_ipe], str) and not mapa_arquivos_locais[chave_zip_ipe].startswith("ERRO"):
        caminho_zip = mapa_arquivos_locais[chave_zip_ipe]
        settings.logger.info(f"Chamando tool_process_cvm_ipe_local para {caminho_zip} (PETR4 CD_CVM: {coletor_prompt_config.CD_CVM_PETROBRAS})")
        
        resultado_processamento = tool_process_cvm_ipe_local(
            caminho_zip_local=caminho_zip,
            cd_cvm_empresa=coletor_prompt_config.CD_CVM_PETROBRAS,
            tool_context=mock_session_state_context 
        )
        if resultado_processamento.get("status") == "success":
            novos_docs_ano = resultado_processamento.get("novos_documentos", [])
            documentos_cvm_coletados.extend(novos_docs_ano)
            settings.logger.info(f"Processamento para ano {ano_str_prompt}: {len(novos_docs_ano)} novos documentos encontrados.")
        else:
            settings.logger.error(f"Erro ao processar IPE para o ano {ano_str_prompt}: {resultado_processamento.get('error_message')}")
    else:
        settings.logger.warning(f"Arquivo IPE {ano_str_prompt} não disponível para processamento (chave: {chave_zip_ipe}).")

settings.logger.info(f"Total de documentos CVM coletados e processados: {len(documentos_cvm_coletados)}")


# --- 2. SIMULAR PASSAGEM DE DADOS PARA O AGENTE ARMAZENADOR ---
settings.logger.info("\n--- FASE 2: Simulando Persistência de Documentos CVM no BD ---")

if not documentos_cvm_coletados:
    settings.logger.info("Nenhum documento CVM coletado para persistir. Encerrando teste de integração.")
else:
    settings.logger.info(f"Iniciando persistência de {len(documentos_cvm_coletados)} documentos CVM.")
    for idx, doc_data in enumerate(documentos_cvm_coletados):
        settings.logger.info(f"Persistindo documento CVM {idx+1}/{len(documentos_cvm_coletados)}: {doc_data.get('title', 'Sem Título')}")
        
        doc_data["source_type"] = "CVM_IPE" 
        
        result_persist = tool_persist_news_or_cvm_document(article_data=doc_data, tool_context=mock_session_state_context)
        
        if result_persist.get("status") == "success":
            settings.logger.info(f"Documento CVM ID {result_persist.get('news_article_id')} persistido com sucesso.")
        else:
            settings.logger.error(f"Falha ao persistir documento CVM: {result_persist.get('message')}. Dados: {doc_data.get('title')}")

settings.logger.info("\n--- TESTE DE INTEGRAÇÃO SIMULADO CONCLUÍDO ---")