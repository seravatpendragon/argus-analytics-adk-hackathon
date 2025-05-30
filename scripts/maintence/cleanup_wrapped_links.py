# src/scripts/maintenance/cleanup_wrapped_links.py

import os
import sys
import json
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from urllib.parse import urlparse, parse_qs
import tldextract

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_PATH = os.path.dirname(os.path.abspath(__file__))
    # Ajuste os ".." para que PROJECT_ROOT seja a raiz do seu projeto
    # Se cleanup_wrapped_links.py está em src/scripts/maintenance/
    PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_SCRIPT_PATH, "..", ".."))
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    print(f"PROJECT_ROOT ({PROJECT_ROOT}) foi adicionado/confirmado no sys.path para cleanup_wrapped_links.")
except NameError:
    PROJECT_ROOT = os.path.abspath(os.path.join(os.getcwd()))
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    print(f"AVISO (cleanup_wrapped_links): __file__ não definido. Usando PROJECT_ROOT como: {PROJECT_ROOT}")

try:
    from config import settings
    from src.database.db_utils import get_db_session, get_or_create_news_source
    from src.database.create_db_tables import NewsArticle, NewsSource, NewsArticleCompanyLink, NewsArticleSegmentLink
    
    if not hasattr(settings, 'logger'):
        import logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
        settings.logger = logging.getLogger(__name__)
        settings.logger.info("Logger fallback inicializado em cleanup_wrapped_links.")
    print("Módulos do projeto importados com sucesso para cleanup_wrapped_links.")
except ImportError as e:
    print(f"Erro CRÍTICO em cleanup_wrapped_links.py ao importar módulos: {e}")
    print(f"sys.path atual: {sys.path}")
    sys.exit(1)
except Exception as e:
    print(f"Erro inesperado durante imports iniciais em cleanup_wrapped_links: {e}")
    sys.exit(1)

# --- Constantes ---
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
CREDIBILITY_FILENAME = "news_source_domain.json" # Seu arquivo de credibilidade

# --- Funções Utilitárias (copiadas/adaptadas dos coletores) ---
def load_json_file(file_path: str) -> dict | None:
    if not os.path.exists(file_path):
        settings.logger.error(f"Arquivo de configuração não existe: {file_path}")
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        settings.logger.error(f"Erro ao carregar JSON de {file_path}: {e}", exc_info=True)
        return None

def clean_google_alert_url_for_cleanup(raw_url: str) -> str: # Nome ligeiramente diferente para evitar conflito se importado
    if not raw_url: return raw_url
    is_google_redirect = False
    if "google.com/url?" in raw_url:
        parsed_url_check = urlparse(raw_url)
        if 'url' in parse_qs(parsed_url_check.query): is_google_redirect = True
    
    if is_google_redirect:
        try:
            parsed_url = urlparse(raw_url)
            query_params = parse_qs(parsed_url.query)
            target_urls = query_params.get('url')
            if target_urls: return target_urls[0]
            target_urls_q = query_params.get('q')
            if target_urls_q: return target_urls_q[0]
            return raw_url # Parâmetro não encontrado
        except Exception: return raw_url # Erro no parse
    return raw_url

def get_domain_from_url_for_cleanup(url: str) -> str | None: # Nome ligeiramente diferente
    if not url: return None
    try:
        # Não chama clean_google_alert_url_for_cleanup aqui, pois espera-se que a URL já esteja limpa
        extracted = tldextract.extract(url)
        domain = extracted.top_domain_under_public_suffix
        if domain: return domain.lower()
        hostname = urlparse(url).hostname
        if hostname: return hostname.lower().replace("www.", "")
        return None
    except Exception: return None


def cleanup_article_links(db_session: Session, loaded_credibility_data: dict, dry_run: bool = True):
    settings.logger.info(f"--- Iniciando Limpeza de Links de Artigos (Dry Run: {dry_run}) ---")
    
    articles_to_check = db_session.query(NewsArticle)\
                                  .filter(NewsArticle.article_link.ilike('https://www.google.com/url?%'))\
                                  .all()

    settings.logger.info(f"Encontrados {len(articles_to_check)} artigos com links potencialmente encapsulados pelo Google.")

    updated_count = 0
    deleted_count = 0
    errors_count = 0
    
    # Para rastrear links limpos já processados nesta sessão e para qual ID eles foram mapeados
    processed_clean_links_map = {} # { "cleaned_link_url": news_article_id_que_vai_receber_este_link }

    # Primeiro, carregar todos os links limpos que já existem no BD para referência rápida
    # Isso pode consumir memória se houver milhões de artigos, mas para dezenas/centenas de milhares é ok.
    # Se for um problema, a query dentro do loop é mais segura, mas mais lenta.
    # Alternativa: não pré-carregar e sempre consultar o BD. Por simplicidade, vamos manter a consulta no loop por ora.

    for article_db_obj in articles_to_check:
        raw_link = article_db_obj.article_link
        cleaned_link = clean_google_alert_url_for_cleanup(raw_link)

        if cleaned_link == raw_link:
            settings.logger.debug(f"Artigo ID {article_db_obj.news_article_id}: Link '{raw_link[:70]}...' não precisou de limpeza.")
            continue

        settings.logger.info(f"Processando Artigo ID {article_db_obj.news_article_id}: Link original '{raw_link[:70]}...' -> Limpo para '{cleaned_link[:70]}...'")

        # 1. Verificar se este `cleaned_link` já foi "reivindicado" por outro artigo nesta sessão de limpeza
        if cleaned_link in processed_clean_links_map:
            # Se o ID que reivindicou é diferente do ID atual, então o atual é um duplicado
            if processed_clean_links_map[cleaned_link] != article_db_obj.news_article_id:
                settings.logger.warning(
                    f"Artigo ID {article_db_obj.news_article_id} (link sujo) limpo para '{cleaned_link[:70]}...', "
                    f"que já foi mapeado para Artigo ID {processed_clean_links_map[cleaned_link]} nesta sessão. "
                    f"{'DELETARIA' if dry_run else 'DELETANDO'} Artigo ID {article_db_obj.news_article_id}."
                )
                if not dry_run:
                    try:
                        # Deletar links FK antes
                        db_session.query(NewsArticleCompanyLink).filter(NewsArticleCompanyLink.news_article_id == article_db_obj.news_article_id).delete(synchronize_session='fetch')
                        db_session.query(NewsArticleSegmentLink).filter(NewsArticleSegmentLink.news_article_id == article_db_obj.news_article_id).delete(synchronize_session='fetch')
                        db_session.delete(article_db_obj)
                        # Não fazer commit aqui, será feito no final. A deleção fica pendente na sessão.
                        deleted_count += 1
                    except Exception as e:
                        settings.logger.error(f"Erro ao marcar para deletar Artigo ID {article_db_obj.news_article_id} duplicado: {e}", exc_info=True)
                        errors_count += 1
                        # Não precisa de rollback aqui, o commit final falhará ou o item não será deletado.
                continue # Pula para o próximo artigo
            # else: # O cleaned_link já foi processado para este mesmo artigo (improvável chegar aqui com a lógica atual, mas seguro)
            #     pass

        # 2. Verificar se o `cleaned_link` já existe no BD em OUTRO artigo
        existing_article_with_clean_link_in_db = db_session.query(NewsArticle.news_article_id)\
                                                     .filter(NewsArticle.article_link == cleaned_link,
                                                             NewsArticle.news_article_id != article_db_obj.news_article_id)\
                                                     .first()
        
        if existing_article_with_clean_link_in_db:
            settings.logger.warning(
                f"Artigo ID {article_db_obj.news_article_id} (link sujo) limpo para '{cleaned_link[:70]}...', "
                f"que já EXISTE no BD para Artigo ID {existing_article_with_clean_link_in_db.news_article_id}. "
                f"{'DELETARIA' if dry_run else 'DELETANDO'} Artigo ID {article_db_obj.news_article_id}."
            )
            if not dry_run:
                try:
                    db_session.query(NewsArticleCompanyLink).filter(NewsArticleCompanyLink.news_article_id == article_db_obj.news_article_id).delete(synchronize_session='fetch')
                    db_session.query(NewsArticleSegmentLink).filter(NewsArticleSegmentLink.news_article_id == article_db_obj.news_article_id).delete(synchronize_session='fetch')
                    db_session.delete(article_db_obj)
                    deleted_count += 1
                except Exception as e:
                    settings.logger.error(f"Erro ao marcar para deletar Artigo ID {article_db_obj.news_article_id} duplicado (existente no BD): {e}", exc_info=True)
                    errors_count += 1
            continue

        # 3. Se chegamos aqui, o cleaned_link é único (ou pertence a este artigo se já estivesse limpo)
        # e não foi reivindicado por outro artigo nesta sessão. Podemos atualizar.
        new_source_domain = get_domain_from_url_for_cleanup(cleaned_link)
        if not new_source_domain:
            settings.logger.error(f"Artigo ID {article_db_obj.news_article_id}: Não foi possível extrair novo domínio de '{cleaned_link}'. Link não será atualizado.")
            errors_count += 1
            continue

        correct_news_source_obj = get_or_create_news_source(
            db_session, new_source_domain, None, loaded_credibility_data
        )

        if not correct_news_source_obj:
            settings.logger.error(f"Artigo ID {article_db_obj.news_article_id}: Falha ao obter/criar NewsSource para novo domínio '{new_source_domain}'. Link e fonte não serão atualizados.")
            errors_count += 1
            continue
        
        if dry_run:
            settings.logger.info(
                f"DRY RUN: Artigo ID {article_db_obj.news_article_id}: ATUALIZARIA link para '{cleaned_link[:70]}...' "
                f"e news_source_id para {correct_news_source_obj.news_source_id} (Fonte: {new_source_domain})."
            )
        else:
            # Marca para atualização. O commit real acontece no final.
            article_db_obj.article_link = cleaned_link
            article_db_obj.news_source_id = correct_news_source_obj.news_source_id
            settings.logger.info(
                f"Artigo ID {article_db_obj.news_article_id}: Marcado para ATUALIZAR link para '{cleaned_link[:70]}...'. "
                f"NewsSource ID para {correct_news_source_obj.news_source_id} (Fonte: {new_source_domain})."
            )
            updated_count +=1
        
        # Adiciona ao mapa de links processados para esta sessão
        processed_clean_links_map[cleaned_link] = article_db_obj.news_article_id


    if not dry_run: # Só tenta commitar se não for dry_run e houver algo para commitar
        if updated_count > 0 or deleted_count > 0:
            try:
                db_session.commit()
                settings.logger.info(f"Commit da limpeza de links realizado: {updated_count} atualizados, {deleted_count} deletados.")
            except IntegrityError as ie: # Captura especificamente o IntegrityError que vimos
                db_session.rollback()
                settings.logger.error(f"ERRO DE INTEGRIDADE NO COMMIT FINAL (UniqueViolation): {ie}", exc_info=True)
                settings.logger.error("Isso pode indicar que múltiplos links sujos foram limpos para a mesma URL final, e a checagem no loop não pegou todos os casos. Uma revisão mais detalhada dos dados ou commits parciais podem ser necessários.")
                errors_count += 1 # Conta como um erro de processamento geral
            except Exception as e:
                db_session.rollback()
                settings.logger.error(f"Erro no commit final da limpeza de links: {e}", exc_info=True)
                errors_count += 1
        else:
            settings.logger.info("Nenhuma alteração (update/delete) foi marcada para commit.")
            
    elif dry_run:
        settings.logger.info("Dry run concluído. Nenhuma alteração foi feita no banco de dados.")
    

    settings.logger.info(f"--- Resumo da Limpeza de Links ---")
    settings.logger.info(f"Artigos verificados: {len(articles_to_check)}")
    settings.logger.info(f"Artigos teriam/foram link atualizado: {updated_count}")
    settings.logger.info(f"Artigos teriam/foram deletados (duplicatas): {deleted_count}")
    settings.logger.info(f"Erros durante o processamento: {errors_count}")
    settings.logger.info(f"Modo Dry Run: {dry_run}")


def main():
    settings.logger.info("=== Iniciando Script de Limpeza de Links de Artigos ===")
    
    credibility_config_path = os.path.join(CONFIG_DIR, CREDIBILITY_FILENAME)
    loaded_credibility_data = load_json_file(credibility_config_path)

    if loaded_credibility_data is None:
        settings.logger.error(f"Dados de credibilidade de '{credibility_config_path}' não carregados. Usando dicionário vazio. Novas fontes podem não ter scores corretos.")
        loaded_credibility_data = {}

    db_session: Session | None = None
    
    # PERGUNTA AO USUÁRIO SOBRE DRY RUN
    user_input = input("Você deseja executar este script em modo DRY RUN (apenas simular, sem salvar no BD)? (S/N): ").strip().lower()
    is_dry_run = user_input == 's'

    if not is_dry_run:
        confirm_input = input(
            "ATENÇÃO: Este script MODIFICARÁ dados no banco de dados (atualizará links e poderá DELETAR artigos duplicados).\n"
            "VOCÊ FEZ UM BACKUP DO BANCO DE DADOS? (S/N): "
        ).strip().lower()
        if confirm_input != 's':
            settings.logger.info("Limpeza abortada pelo usuário (backup não confirmado).")
            return
    
    try:
        db_session = get_db_session()
        cleanup_article_links(db_session, loaded_credibility_data, dry_run=is_dry_run)
    except Exception as e:
        settings.logger.critical(f"Erro catastrófico no script de limpeza: {e}", exc_info=True)
        if db_session and not is_dry_run: # Tentar rollback se não for dry run e houve erro com sessão aberta
            try: db_session.rollback()
            except Exception as rb_e: settings.logger.error(f"Erro ao tentar rollback da sessão: {rb_e}")
    finally:
        if db_session:
            settings.logger.info("Fechando sessão do banco de dados (cleanup script).")
            db_session.close()

    settings.logger.info("=== Script de Limpeza de Links de Artigos Finalizado ===")

if __name__ == "__main__":
    main()