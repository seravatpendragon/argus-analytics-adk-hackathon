import os
import requests
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List
from email.utils import parsedate_to_datetime
from config import settings

def tool_download_cvm_data(anos: Optional[List[int]] = None) -> dict:
    """
    Verifica de forma inteligente se os arquivos de dados IPE da CVM precisam ser atualizados
    comparando as datas de modificação local e remota antes de baixar.
    """
    if anos is None:
        anos = [datetime.now().year, datetime.now().year - 1]
    
    settings.logger.info(f"Iniciando verificação/download inteligente de dados da CVM para anos: {anos}")
    base_url = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/"
    download_dir = Path(settings.RAW_DATA_DIR) / "cvm" / "IPE"
    
    downloaded_files_map = {}
    
    for ano in anos:
        file_name = f"ipe_cia_aberta_{ano}.zip"
        year_dir = download_dir / str(ano)
        file_path = year_dir / file_name
        url = base_url + file_name
        
        year_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Faz uma requisição HEAD para pegar os metadados do arquivo remoto
            response = requests.head(url, timeout=10)
            response.raise_for_status()
            remote_last_modified_str = response.headers.get('Last-Modified')
            if not remote_last_modified_str:
                raise ValueError("Cabeçalho 'Last-Modified' não encontrado na resposta do servidor.")
            
            remote_last_modified_dt = parsedate_to_datetime(remote_last_modified_str)

            # Verifica se o arquivo local existe e compara as datas
            if file_path.exists():
                local_last_modified_ts = os.path.getmtime(file_path)
                local_last_modified_dt = datetime.fromtimestamp(local_last_modified_ts, tz=timezone.utc)
                
                if local_last_modified_dt >= remote_last_modified_dt:
                    settings.logger.info(f"Versão local de '{file_name}' está atualizada. Download pulado.")
                    downloaded_files_map[f"IPE_{ano}_zip"] = str(file_path)
                    continue

            # Se o arquivo não existe ou está desatualizado, baixa
            settings.logger.info(f"Versão remota de '{file_name}' é mais nova. Baixando...")
            download_response = requests.get(url, stream=True)
            download_response.raise_for_status()
            with open(file_path, 'wb') as f:
                for chunk in download_response.iter_content(chunk_size=8192):
                    f.write(chunk)
            downloaded_files_map[f"IPE_{ano}_zip"] = str(file_path)
            settings.logger.info(f"Download de '{file_name}' concluído com sucesso.")

        except requests.exceptions.RequestException as e:
            settings.logger.error(f"Falha na comunicação com o servidor CVM para '{url}': {e}")
        except Exception as e:
            settings.logger.error(f"Erro inesperado no processo de download para o ano {ano}: {e}", exc_info=True)

    return {"status": "success", "message": "Verificação de download inteligente concluída.", "downloaded_files_map": downloaded_files_map}