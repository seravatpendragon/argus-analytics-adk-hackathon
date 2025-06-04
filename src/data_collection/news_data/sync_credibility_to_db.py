# sync_credibility_to_db.py (Exemplo)
import os
import json
import sys
from pathlib import Path

# --- Configuração de Caminhos e Imports do Projeto ---
project_root_path = Path(__file__).resolve().parent.parent.parent.parent
if str(project_root_path) not in sys.path:
    sys.path.append(str(project_root_path))

try:
    from config import settings
    from src.database.db_utils import get_db_session, get_or_create_news_source
    from src.database.create_db_tables import NewsSource # Para queries diretas se necessário
except ImportError as e:
    settings.logger.error(f"Erro CRÍTICO ao importar módulos do projeto: {e}")
    sys.exit(1)

CONFIG_DIR = os.path.join(project_root_path, "config")
CREDIBILITY_FILE_PATH = os.path.join(CONFIG_DIR, "news_source_domain.json")

def load_json_file(file_path):
    # ... (função load_json_file) ...
    try:
        with open(file_path, 'r', encoding='utf-8') as f: return json.load(f)
    except FileNotFoundError: settings.logger.info(f"Erro: Arquivo não encontrado - {file_path}"); return None
    except json.JSONDecodeError: settings.logger.info(f"Erro: JSON inválido - {file_path}"); return None


def sync_credibility():
    if not hasattr(settings, 'logger'): # Fallback
        import logging
        logging.basicConfig(level=logging.INFO)
        settings.logger = logging.getLogger(__name__)

    settings.logger.info("Iniciando sincronização de news_source_domain.json para o banco de dados...")
    
    loaded_credibility_data = load_json_file(CREDIBILITY_FILE_PATH)
    if not loaded_credibility_data:
        settings.logger.error("Não foi possível carregar news_source_domain.json. Sincronização abortada.")
        return

    db_session = None
    updated_sources = 0
    created_sources = 0
    try:
        db_session = get_db_session()
        for domain, data in loaded_credibility_data.items():
            source_name = data.get("source_name", domain)
            overall_score = data.get("overall_credibility_score")
            
            if overall_score is None:
                settings.logger.warning(f"Score não encontrado para '{domain}' no JSON. Pulando.")
                continue

            existing_source = db_session.query(NewsSource).filter(
                (NewsSource.url_base == domain.lower()) | (NewsSource.name == source_name[:255])
            ).first()
            if existing_source:
                atualizou = False
                # Atualiza score se mudou
                if existing_source.base_credibility_score != overall_score:
                    existing_source.base_credibility_score = overall_score
                    atualizou = True
                # Atualiza name se mudou
                if existing_source.name != source_name[:255]:
                    existing_source.name = source_name[:255]
                    atualizou = True
                # Atualiza url_base se mudou
                if existing_source.url_base != domain.lower():
                    existing_source.url_base = domain.lower()
                    atualizou = True
                if atualizou:
                    settings.logger.info(f"Atualizando NewsSource para '{domain}' com score {overall_score}.")
                    updated_sources += 1
                else:
                    settings.logger.info(f"Nenhuma alteração necessária para '{domain}'.")
            else:
                new_source = NewsSource(
                    name=source_name[:255],
                    url_base=domain.lower(),
                    base_credibility_score=overall_score
                )
                db_session.add(new_source)
                settings.logger.info(f"Criando nova NewsSource para '{domain}' com score {overall_score}.")
                created_sources += 1
        
        db_session.commit()
        settings.logger.info(f"Sincronização concluída. {created_sources} fontes criadas, {updated_sources} fontes atualizadas.")

    except Exception as e:
        settings.logger.error(f"Erro durante a sincronização de credibilidade: {e}", exc_info=True)
        if db_session:
            db_session.rollback()
    finally:
        if db_session:
            db_session.close()

if __name__ == "__main__":
    sync_credibility()