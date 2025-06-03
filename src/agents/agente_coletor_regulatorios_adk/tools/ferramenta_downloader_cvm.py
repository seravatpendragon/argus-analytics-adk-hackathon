# src/agents/agente_coletor_regulatorios_adk/tools/ferramenta_downloader_cvm.py
from datetime import datetime
import os
import sys
import json
import requests
from pathlib import Path
import time
import shutil # Adicionado para shutil.copyfileobj

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

try:
    from config import settings
    if not hasattr(settings, 'logger'):
        import logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
        settings.logger = logging.getLogger("ferramenta_downloader_cvm_fb_logger")
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
    settings = type('SettingsFallback', (), {'logger': logging.getLogger("ferramenta_downloader_cvm_no_settings_logger")})()
    settings.logger.error("Falha ao importar config.settings em downloader_cvm. Usando logger de fallback.")


# --- Constantes ---
CONFIG_DIR = PROJECT_ROOT / "config"
CVM_DATA_SOURCES_CONFIG_FILE = CONFIG_DIR / "cvm_data_sources.json"
DATA_CVM_RAW_PATH = PROJECT_ROOT / "data" / "raw" / "cvm"

_cvm_sources_map_cache = None

def _load_cvm_sources_config() -> dict | None:
    global _cvm_sources_map_cache
    if not CVM_DATA_SOURCES_CONFIG_FILE.exists():
        settings.logger.error(f"ARQUIVO DE CONFIG CVM NÃO ENCONTRADO EM: {CVM_DATA_SOURCES_CONFIG_FILE}")
        return None
    try:
        with open(CVM_DATA_SOURCES_CONFIG_FILE, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        settings.logger.debug(f"DEBUG: Conteúdo bruto carregado de {CVM_DATA_SOURCES_CONFIG_FILE}: {json.dumps(config_data, indent=2)}")

        if "fontes_cvm" not in config_data or not isinstance(config_data["fontes_cvm"], list):
            settings.logger.error(f"DEBUG: Estrutura inválida em {CVM_DATA_SOURCES_CONFIG_FILE}: chave 'fontes_cvm' não encontrada ou não é uma lista.")
            return None
        
        source_map = {
            source_conf.get("id"): source_conf 
            for source_conf in config_data["fontes_cvm"] 
            if source_conf.get("id")
        }
        _cvm_sources_map_cache = source_map
        return _cvm_sources_map_cache
    except Exception as e:
        settings.logger.error(f"DEBUG: Erro ao carregar ou parsear {CVM_DATA_SOURCES_CONFIG_FILE}: {e}", exc_info=True)
        return None

def get_cvm_source_config(source_id: str) -> dict | None:
    global _cvm_sources_map_cache
    if _cvm_sources_map_cache is None:
        _load_cvm_sources_config()
    
    if _cvm_sources_map_cache is None: return None
    return _cvm_sources_map_cache.get(source_id)


def tool_download_cvm_data(anos: list[int], tipos_doc_ids: list[str]) -> dict:
    """
    Baixa arquivos de dados da CVM (ZIP ou CSV) para os anos e IDs de tipos de documentos especificados,
    conforme configurado em 'cvm_data_sources.json'. Os arquivos são salvos localmente e
    substituídos se já existirem para garantir os dados mais recentes.

    Args:
        anos (list[int]): Lista de anos para baixar os dados (ex: [2025, 2024]).
        tipos_doc_ids (list[str]): Lista de IDs de tipos de documentos a baixar (ex: ["IPE", "CAD"]).
                                   Estes IDs devem corresponder aos 'id' no cvm_data_sources.json.
    Returns:
        dict: Um dicionário contendo:
              'status': 'success' ou 'error'.
              'downloaded_files_map': Em caso de sucesso, um dicionário mapeando uma chave 
                                      (ex: 'IPE_2025_zip') para o caminho local do arquivo.
              'error_message': Em caso de erro, uma mensagem descritiva.
              'partial_success': True se alguns arquivos foram baixados mas outros falharam.
    """
    settings.logger.info(f" ferramenta_downloader_cvm: Iniciando download para anos: {anos}, tipos_ids: {tipos_doc_ids}")
    downloaded_files_map = {}
    user_agent = getattr(settings, 'USER_AGENT', "Mozilla/5.0 Python/Requests ArgusProject/CVMDownloader")
    overall_status = "success"
    error_messages = []
    partial_success = False

    for tipo_id in tipos_doc_ids:
        source_config = get_cvm_source_config(tipo_id)
        if not source_config:
            msg = f"Configuração não encontrada para o tipo_doc_id '{tipo_id}'. Pulando."
            settings.logger.error(msg)
            error_messages.append(msg)
            overall_status = "error"
            partial_success = True
            continue

        subpasta_local_key = source_config.get("subpasta_local", tipo_id.upper())
        local_tipo_path = DATA_CVM_RAW_PATH / subpasta_local_key
        local_tipo_path.mkdir(parents=True, exist_ok=True)
        
        is_annual_source = source_config.get("anual", False)
        # Usa o primeiro ano para fontes não anuais, ou o ano atual se a lista de anos estiver vazia.
        years_to_process = anos if is_annual_source else [anos[0] if anos else datetime.now().year]

        for ano_idx, ano in enumerate(years_to_process):
            file_key_default = f"{tipo_id}_{ano}_ERRO_GERAL" if is_annual_source else f"{tipo_id}_ERRO_GERAL"
            filename, file_url, local_file_path, file_key = None, None, None, file_key_default
            try:
                current_filename_template = source_config.get("filename_template")
                current_url_template = source_config.get("url_template")

                if not current_filename_template or not current_url_template:
                    msg = f"Templates 'filename_template' ou 'url_template' ausentes na config para '{tipo_id}'. Pulando ano {ano}."
                    settings.logger.error(msg)
                    error_messages.append(msg)
                    overall_status = "error"
                    partial_success = True
                    if not is_annual_source: break
                    continue

                filename = current_filename_template.format(ano=ano) if is_annual_source else current_filename_template
                file_url = current_url_template.format(ano=ano) if is_annual_source else current_url_template
                
                file_key = f"{tipo_id}_{ano}" if is_annual_source else tipo_id
                file_key += "_zip" if source_config.get("tipo_retorno") == "ZIP" else "_csv"

                if is_annual_source:
                    local_ano_path = local_tipo_path / str(ano)
                    local_ano_path.mkdir(parents=True, exist_ok=True)
                    local_file_path = local_ano_path / filename
                else:
                    local_file_path = local_tipo_path / filename
                
                settings.logger.info(f"Baixando (e substituindo se existir): {file_url} para {local_file_path}")
                if local_file_path.exists():
                    settings.logger.info(f"Arquivo '{filename}' já existe localmente. Será substituído.")
                
                response = requests.get(file_url, headers={'User-Agent': user_agent}, stream=True, timeout=300)
                response.raise_for_status()
                
                with open(local_file_path, 'wb') as f:
                    shutil.copyfileobj(response.raw, f) 
                
                settings.logger.info(f"Arquivo '{filename}' baixado/substituído com sucesso em '{local_file_path}'.")
                downloaded_files_map[file_key] = str(local_file_path)

            except requests.exceptions.RequestException as e:
                msg = f"Erro ao baixar '{filename or 'desconhecido'}' de '{file_url or 'URL desconhecida'}': {e}"
                settings.logger.error(msg)
                error_messages.append(msg)
                downloaded_files_map[file_key] = f"ERRO_DOWNLOAD"
                overall_status = "error"
                partial_success = True
            except KeyError as ke:
                msg = f"Erro de formatação de template (KeyError) para '{tipo_id}' (ano {ano}): {ke}."
                settings.logger.error(msg)
                error_messages.append(msg)
                downloaded_files_map[file_key] = f"ERRO_TEMPLATE_KEY"
                overall_status = "error"
                partial_success = True
            except Exception as e:
                msg = f"Erro inesperado ao processar '{tipo_id}' para ano {ano}: {e}"
                settings.logger.error(msg, exc_info=True)
                error_messages.append(msg)
                downloaded_files_map[file_key] = f"ERRO_INESPERADO"
                overall_status = "error"
                partial_success = True

            if not is_annual_source: break

            if len(tipos_doc_ids) > 1 or len(years_to_process) > 1 : # Só adiciona delay se houver mais trabalho a fazer
                 if not (tipo_id == tipos_doc_ids[-1] and ano == years_to_process[-1]): # Não após o último de todos
                    cvm_delay = getattr(settings, 'API_DELAYS', {}).get("CVM", 1) 
                    if isinstance(cvm_delay, (int,float)) and cvm_delay > 0: time.sleep(cvm_delay)
                    else: time.sleep(0.5)

    settings.logger.info("Download de dados da CVM concluído.")
    
    result = {"status": overall_status, "downloaded_files_map": downloaded_files_map}
    if error_messages:
        result["error_message"] = "; ".join(error_messages)
    if partial_success and overall_status == "success": # Se houve erros mas alguns sucessos
        result["status"] = "partial_success"
        
    return result

if __name__ == '__main__':
    # ... (bloco de teste como antes, mas agora esperando um dicionário com 'status') ...
    settings.logger.info("--- Teste Standalone da ferramenta_downloader_cvm ---")
    DATA_CVM_RAW_PATH.mkdir(parents=True, exist_ok=True)
    anos_para_teste = [datetime.now().year]
    # Use os IDs EXATOS do seu cvm_data_sources.json
    tipos_para_teste = ["CAD_CIA_ABERTA", "IPE_CIA_ABERTA"] # Se no JSON os IDs são "CAD_CIA_ABERTA", use isso aqui.

    resultados_completos = tool_download_cvm_data(anos_para_teste, tipos_para_teste)
    print("\nResultados Completos do Download (Teste):")
    print(json.dumps(resultados_completos, indent=2))