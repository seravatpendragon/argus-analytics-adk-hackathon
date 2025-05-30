# src/scripts/news_data/news_rss_collector.py

import feedparser
import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
import tldextract
import requests
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pathlib import Path

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    print(f"PROJECT_ROOT ({PROJECT_ROOT}) foi adicionado/confirmado no sys.path para news_rss_collector.")
except NameError:
    PROJECT_ROOT = Path(os.getcwd())
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    print(f"AVISO (news_rss_collector): __file__ não definido. Usando PROJECT_ROOT como: {PROJECT_ROOT}")

try:
    from config import settings
    from src.database.db_utils import (
        get_db_session,
        get_or_create_news_source,
        get_company_id_for_ticker,
        get_segment_id_by_name
    )
    from src.database.create_db_tables import (
        NewsArticle,
        NewsArticleCompanyLink,
        NewsArticleSegmentLink
    )
    if not hasattr(settings, 'logger'):
        import logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
        settings.logger = logging.getLogger("news_rss_collector_fallback_logger")
        settings.logger.info("Logger fallback inicializado, pois não encontrado em settings.")
    print("Módulos do projeto importados com sucesso para news_rss_collector.")
except ImportError as e:
    print(f"Erro CRÍTICO em news_rss_collector.py ao importar módulos: {e}")
    print(f"sys.path atual: {sys.path}")
    sys.exit(1)
except Exception as e:
    print(f"Erro inesperado durante imports iniciais em news_rss_collector: {e}")
    sys.exit(1)

# --- Constantes de Configuração ---
CONFIG_DIR = PROJECT_ROOT / "config"
RSS_SOURCES_FILENAME = "rss_news_config.json"
CREDIBILITY_FILENAME = "news_source_domain.json"

# --- Funções Utilitárias ---
def load_json_file(file_path: Path) -> dict | list | None:
    if not file_path.exists():
        settings.logger.error(f"Arquivo de configuração não existe: {file_path}")
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        settings.logger.error(f"Erro ao decodificar JSON de {file_path}: {e}")
        return None
    except Exception as e:
        settings.logger.error(f"Erro inesperado ao ler {file_path}: {e}", exc_info=True)
        return None

def _clean_google_param_url(raw_url: str) -> str | None:
    if not raw_url or "google.com/url?" not in raw_url:
        return None
    try:
        parsed_url = urlparse(raw_url)
        query_params = parse_qs(parsed_url.query)
        target_urls = query_params.get('url') or query_params.get('q')
        if target_urls: return target_urls[0]
        settings.logger.debug(f"Google redirect URL ('/url?') detectada, mas parâmetro 'url' ou 'q' não encontrado: {raw_url}") # Mudado para debug
    except Exception as e:
        settings.logger.error(f"Erro ao tentar limpar URL Google ('/url?') '{raw_url}': {e}", exc_info=True)
    return None

def resolve_article_link(raw_link: str, feed_source_name_for_log: str) -> str:
    if not raw_link:
        settings.logger.warning(f"Link bruto vazio fornecido para resolução (Feed: {feed_source_name_for_log}).")
        return ""

    param_cleaned_link = _clean_google_param_url(raw_link)
    if param_cleaned_link:
        settings.logger.debug(f"Link '/url?' limpo por parâmetro: '{raw_link[:70]}...' -> '{param_cleaned_link[:70]}...' (Feed: {feed_source_name_for_log})")
        return param_cleaned_link
    
    if raw_link.startswith("https://news.google.com/rss/articles/"):
        settings.logger.debug(f"Tentando resolver link Google News '/rss/articles/': {raw_link[:70]}... (Feed: {feed_source_name_for_log})")
        try:
            user_agent = getattr(settings, 'USER_AGENT', "Mozilla/5.0 Python/Requests")
            headers = {'User-Agent': user_agent}
            response = requests.head(raw_link, allow_redirects=True, timeout=10)
            final_url = response.url
            if final_url != raw_link:
                settings.logger.info(f"Link Google News '/rss/articles/' resolvido via HEAD: '{raw_link[:70]}...' -> '{final_url[:70]}...' (Feed: {feed_source_name_for_log})")
            else:
                settings.logger.debug(f"Link Google News '/rss/articles/' HEAD request não alterou URL: '{raw_link[:70]}...' (Feed: {feed_source_name_for_log})")
            return final_url
        except requests.exceptions.Timeout:
            settings.logger.warning(f"Timeout (10s) ao resolver redirect para '{raw_link[:70]}...' (Feed: {feed_source_name_for_log}). Usando link original.")
        except requests.exceptions.RequestException as e:
            settings.logger.warning(f"Falha ao resolver redirect para '{raw_link[:70]}...' (Feed: {feed_source_name_for_log}): {e}. Usando link original.")
        return raw_link
    return raw_link

def get_domain_from_url(url_to_parse: str) -> str | None:
    if not url_to_parse: return None
    try:
        extracted = tldextract.extract(url_to_parse)
        domain = extracted.top_domain_under_public_suffix
        if domain: return domain.lower()
        hostname = urlparse(url_to_parse).hostname
        if hostname: return hostname.lower().replace("www.", "")
        return None
    except Exception as e:
        settings.logger.error(f"Falha ao extrair domínio de URL '{url_to_parse}': {e}", exc_info=True)
        return None

def assign_initial_article_type(title: str | None, summary: str | None) -> str:
    title_lower = title.lower() if title else ""
    summary_lower = summary.lower() if summary else ""
    text_to_search = title_lower + " " + summary_lower
    if not text_to_search.strip(): return "Outros"
    if "fato relevante" in text_to_search: return "Fato Relevante"
    if "resultado" in text_to_search and \
       ("trimestral" in text_to_search or "balanço" in text_to_search or \
        "lucro" in text_to_search or "anual" in text_to_search or "reporta" in text_to_search):
        return "Resultados Trimestrais/Anuais"
    # ... (resto da sua lógica de assign_initial_article_type)
    return "Outros"

# --- Lógica Principal de Coleta de Feeds RSS ---
def collect_articles_from_rss(
        rss_sources_config: list,
        loaded_credibility_data: dict,
        db_session: Session
    ) -> int:
    if not rss_sources_config:
        settings.logger.info("Nenhuma configuração de feed RSS fornecida.")
        return 0

    total_new_articles_saved_session = 0
    feedparser_agent = getattr(settings, 'USER_AGENT', "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 ArgusRSSCollector/1.2")
    request_headers = {'Accept': 'application/rss+xml,application/xml,application/atom+xml,*/*'}

    num_feeds = len(rss_sources_config)
    for i, feed_config in enumerate(rss_sources_config):
        feed_source_name_from_config = feed_config.get("source_name", f"Feed RSS Index {i}")
        feed_url = feed_config.get("feed_url")
        target_company_ticker = feed_config.get("target_company_ticker")
        target_segment_name = feed_config.get("target_segment_name")
        # <<< NOVO: Obter o domínio de publicador pré-definido da configuração do feed >>>
        defined_publisher_domain_override = feed_config.get("publisher_domain_override")

        if not feed_url:
            settings.logger.warning(f"URL do feed não encontrada para '{feed_source_name_from_config}'. Pulando.")
            continue

        settings.logger.info(f"Processando Feed RSS: '{feed_source_name_from_config}' ({feed_url}) [{i+1}/{num_feeds}]")
        # ... (lógica de busca e parsing do feed_data como antes) ...
        feed_data = None
        try:
            feed_data = feedparser.parse(feed_url, agent=feedparser_agent, request_headers=request_headers)
        except Exception as e:
            settings.logger.error(f"Erro EXCEPCIONAL ao buscar feed '{feed_source_name_from_config}': {e}", exc_info=True)
            if i < num_feeds - 1: # Delay
                try:
                    delay_seconds = getattr(settings, 'API_DELAYS', {}).get("RSS", 0.5)
                    if isinstance(delay_seconds, (int, float)) and delay_seconds > 0: time.sleep(delay_seconds)
                except Exception: pass
            continue
        if not feed_data or feed_data.bozo: # Checa se feed_data é None ou bozo
            # ... (tratamento de erro bozo e delay como antes) ...
            continue
        if not feed_data.entries:
            # ... (tratamento de feed vazio e delay como antes) ...
            continue
        
        settings.logger.info(f"Encontrados {len(feed_data.entries)} artigos no feed '{feed_source_name_from_config}'. Processando...")
        new_articles_for_this_feed = 0
        for entry in feed_data.entries:
            settings.logger.info(f"--- Debug Artigo (Feed: {feed_source_name_from_config}) ---")
            raw_article_link = entry.get("link")
            settings.logger.info(f"Raw Link do Feed: {raw_article_link}")
            
            article_link_for_db = resolve_article_link(raw_article_link, feed_source_name_from_config)
            settings.logger.info(f"Link para BD (após resolve_article_link): {article_link_for_db}")

            if not article_link_for_db:
                settings.logger.warning(f"Link do artigo resultou em vazio após resolução. Pulando.")
                settings.logger.info("--- Fim Debug Artigo ---")
                continue
            
            # ... (lógica de checagem de duplicatas com article_link_for_db) ...

            title_raw = entry.get("title")
            title = title_raw if title_raw else "Sem Título"
            settings.logger.info(f"Título do Artigo: {title[:60]}...")
            
            # ... (extração de summary, publication_date_dt) ...
            summary_raw = entry.get("summary") or entry.get("description"); summary = summary_raw if summary_raw else ""
            # ... (código de data) ...
            publication_date_dt = None; time_struct = entry.get("published_parsed") or entry.get("updated_parsed")
            if time_struct:
                try: publication_date_dt = datetime(time_struct.tm_year, time_struct.tm_mon, time_struct.tm_mday, time_struct.tm_hour, time_struct.tm_min, time_struct.tm_sec, tzinfo=timezone.utc)
                except: publication_date_dt = datetime.now(timezone.utc); settings.logger.warning(f"Data 'parsed' inválida para '{title}'. Usando data atual.")
            else: publication_date_dt = datetime.now(timezone.utc); settings.logger.warning(f"Data não encontrada para '{title}'. Usando data atual.")


            # --- LÓGICA REFINADA PARA OBTER DOMÍNIO DA FONTE PARA CREDIBILIDADE ---
            domain_for_credibility_check = None
            publisher_name_hint = None

            # 1. Usar o 'publisher_domain_override' da configuração do feed, se existir
            if defined_publisher_domain_override:
                domain_for_credibility_check = get_domain_from_url(defined_publisher_domain_override) # Normaliza o override
                settings.logger.info(f"Usando 'publisher_domain_override' ('{defined_publisher_domain_override}' -> '{domain_for_credibility_check}') para credibilidade.")
                # Para o nome, podemos tentar o 'source_name' da tag <source> se coincidir com o override
                if hasattr(entry, 'source') and entry.source and hasattr(entry.source, 'title') and entry.source.title:
                    temp_domain_from_tag = get_domain_from_url(entry.source.href if hasattr(entry.source, 'href') else None)
                    if temp_domain_from_tag == domain_for_credibility_check:
                        publisher_name_hint = entry.source.title
            
            # 2. Se não houver override, tentar obter da tag <source> do item RSS
            if not domain_for_credibility_check and hasattr(entry, 'source') and entry.source and hasattr(entry.source, 'href') and entry.source.href:
                source_url_from_tag = entry.source.href
                domain_for_credibility_check = get_domain_from_url(source_url_from_tag)
                settings.logger.info(f"Domínio para credibilidade (de entry.source.href='{source_url_from_tag}'): {domain_for_credibility_check}")
                if hasattr(entry.source, 'title') and entry.source.title:
                    publisher_name_hint = entry.source.title
            
            # 3. Se ainda não tiver, usar o domínio do link resolvido do artigo
            if not domain_for_credibility_check:
                domain_for_credibility_check = get_domain_from_url(article_link_for_db)
                settings.logger.info(f"Domínio para credibilidade (do link resolvido do artigo='{article_link_for_db[:70]}...'): {domain_for_credibility_check}")
            
            # 4. Hint de nome do publicador (fallback para o título geral do feed)
            if not publisher_name_hint and hasattr(feed_data, 'feed') and feed_data.feed and hasattr(feed_data.feed, 'title') and feed_data.feed.title:
                publisher_name_hint = feed_data.feed.title
            
            # 5. Último fallback para o domínio se tudo falhar (raro se article_link_for_db for válido)
            if not domain_for_credibility_check:
                domain_from_feed_link = get_domain_from_url(feed_data.feed.get('link')) if hasattr(feed_data, 'feed') and feed_data.feed else None
                if domain_from_feed_link:
                    domain_for_credibility_check = domain_from_feed_link
                    settings.logger.warning(f"Usando domínio do próprio feed '{domain_for_credibility_check}' como ÚLTIMO RECURSO para credibilidade do artigo: '{title}'")
                else:
                    settings.logger.error(f"CRÍTICO: Não foi possível obter um domínio de publicador válido para credibilidade do artigo RSS: '{title}' (Link original: {raw_article_link}). Pulando.")
                    settings.logger.info("--- Fim Debug Artigo ---")
                    continue
            settings.logger.info(f"Domínio final para verificação de credibilidade: {domain_for_credibility_check}, Hint de nome: {publisher_name_hint}")
            # --- FIM DA LÓGICA REFINADA ---

            if loaded_credibility_data and domain_for_credibility_check:
                if domain_for_credibility_check in loaded_credibility_data:
                    settings.logger.info(f"VERIFICAÇÃO: Domínio '{domain_for_credibility_check}' ENCONTRADO no loaded_credibility_data. Score no JSON: {loaded_credibility_data[domain_for_credibility_check].get('overall_credibility_score')}")
                else:
                    settings.logger.warning(f"VERIFICAÇÃO: Domínio '{domain_for_credibility_check}' NÃO ENCONTRADO no loaded_credibility_data.")
            # ... (restante dos logs de verificação) ...

            news_source_obj = get_or_create_news_source(
                db_session, domain_for_credibility_check, publisher_name_hint, loaded_credibility_data
            )

            if news_source_obj:
                settings.logger.info(f"NewsSource OBTIDA/CRIADA: ID {news_source_obj.news_source_id}, Nome: '{news_source_obj.name}', Score no BD: {news_source_obj.base_credibility_score}")
            else:
                settings.logger.error(f"Falha crítica ao obter/criar NewsSource para domínio RSS '{domain_for_credibility_check}'. Artigo '{title}' não será salvo.")
                settings.logger.info("--- Fim Debug Artigo ---")
                continue
            
            # ... (resto do processamento do artigo e salvamento, usando article_link_for_db para NewsArticle.article_link) ...
            initial_article_type = assign_initial_article_type(title, summary)
            try:
                new_article_to_save = NewsArticle(
                    headline=title, article_link=article_link_for_db, publication_date=publication_date_dt,
                    news_source_id=news_source_obj.news_source_id, summary=summary, article_text_content=None,
                    article_type=initial_article_type, processing_status='pending_full_text_fetch',
                    source_feed_name=feed_source_name_from_config, source_feed_url=feed_url,
                    collection_date=datetime.now(timezone.utc)
                )
                db_session.add(new_article_to_save)
                db_session.flush()

                # Lógica de Vínculo
                company_id_to_link = get_company_id_for_ticker(db_session, target_company_ticker) if target_company_ticker else None
                if company_id_to_link:
                    if not db_session.query(NewsArticleCompanyLink).filter_by(news_article_id=new_article_to_save.news_article_id, company_id=company_id_to_link).first():
                        db_session.add(NewsArticleCompanyLink(news_article_id=new_article_to_save.news_article_id, company_id=company_id_to_link))
                
                segment_id_to_link = get_segment_id_by_name(db_session, target_segment_name) if target_segment_name else None
                if segment_id_to_link:
                    if not db_session.query(NewsArticleSegmentLink).filter_by(news_article_id=new_article_to_save.news_article_id, segment_id=segment_id_to_link).first():
                         db_session.add(NewsArticleSegmentLink(news_article_id=new_article_to_save.news_article_id, segment_id=segment_id_to_link))
                
                new_articles_for_this_feed += 1
                log_title_display = title if title != "Sem Título" else "Artigo RSS sem título"
                settings.logger.info(f"Novo artigo de RSS adicionado à sessão: '{log_title_display[:50]}...' (Publicador: {domain_for_credibility_check}, Feed: {feed_source_name_from_config})")
            except IntegrityError: # ... (resto do try-except)
                db_session.rollback(); settings.logger.warning(f"Erro de integridade (duplicata?): {article_link_for_db}")
            except Exception as e: # ...
                db_session.rollback(); settings.logger.error(f"Erro ao salvar artigo RSS '{title}': {e}", exc_info=True)

            settings.logger.info("--- Fim Debug Artigo ---")
        
        # ... (commit por feed e delay entre feeds, como antes) ...
        if new_articles_for_this_feed > 0:
            try:
                db_session.commit()
                settings.logger.info(f"{new_articles_for_this_feed} novos artigos do feed '{feed_source_name_from_config}' commitados.")
                total_new_articles_saved_session += new_articles_for_this_feed
            except Exception as e:
                db_session.rollback()
                settings.logger.error(f"Erro no commit do feed RSS '{feed_source_name_from_config}': {e}", exc_info=True)
        else:
            settings.logger.info(f"Nenhum artigo novo para commitar do feed '{feed_source_name_from_config}'.")

        if i < num_feeds - 1: # Delay
            try:
                delay_seconds = 0.5 
                if hasattr(settings, 'API_DELAYS') and isinstance(settings.API_DELAYS, dict):
                    rss_delay_val = settings.API_DELAYS.get("RSS")
                    if isinstance(rss_delay_val, (int, float)) and rss_delay_val > 0: delay_seconds = rss_delay_val
                    elif rss_delay_val is not None: settings.logger.warning(f"Delay RSS inválido: {rss_delay_val}. Usando {delay_seconds}s.")
                settings.logger.info(f"Aguardando {delay_seconds}s antes do próximo feed RSS...")
                time.sleep(delay_seconds)
            except Exception as e:
                 settings.logger.error(f"Erro no delay RSS: {e}", exc_info=True)
                 time.sleep(0.5)

    return total_new_articles_saved_session

# --- Função Principal do Coletor ---
def main():
    # ... (main como antes, garantindo que CONFIG_DIR, RSS_SOURCES_FILENAME, CREDIBILITY_FILENAME usem Path se necessário)
    if not hasattr(settings, 'logger'):
        import logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
        settings.logger = logging.getLogger("news_rss_collector_main")
        settings.logger.info("Logger fallback (main) configurado.")

    settings.logger.info("=== Iniciando Coletor de Notícias de Feeds RSS ===")

    rss_sources_path = CONFIG_DIR / RSS_SOURCES_FILENAME
    credibility_config_path = CONFIG_DIR / CREDIBILITY_FILENAME

    rss_sources_config_list = load_json_file(rss_sources_path)
    loaded_credibility_data = load_json_file(credibility_config_path)

    if not isinstance(rss_sources_config_list, list):
        settings.logger.critical(f"Config de feeds RSS '{rss_sources_path}' não é lista ou falhou ao carregar. Abortando.")
        return
    
    if loaded_credibility_data is None:
        settings.logger.warning(f"Dados de credibilidade de '{credibility_config_path}' não carregados. Novas fontes receberão score padrão (0.6).")
        loaded_credibility_data = {}

    db_session: Session | None = None
    try:
        db_session = get_db_session()
        settings.logger.info("Sessão do BD obtida para RSS collector.")

        num_articles_saved = collect_articles_from_rss(rss_sources_config_list, loaded_credibility_data, db_session)
        settings.logger.info(f"Total de {num_articles_saved} novos artigos de RSS foram salvos nesta execução.")

    except Exception as e:
        settings.logger.critical(f"Erro catastrófico no script news_rss_collector: {e}", exc_info=True)
        if db_session:
            try: db_session.rollback()
            except Exception as rb_e: settings.logger.error(f"Erro ao tentar rollback da sessão RSS: {rb_e}")
    finally:
        if db_session:
            settings.logger.info("Fechando sessão do BD (RSS collector).")
            db_session.close()

    settings.logger.info("=== Coletor de Notícias de Feeds RSS Finalizado ===")


if __name__ == "__main__":
    # ... (bloco if __name__ == "__main__" como antes, com criação de arquivos de exemplo) ...
    if not CONFIG_DIR.exists():
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            print(f"Diretório '{CONFIG_DIR}' criado.")
        except OSError as e:
            print(f"Erro ao criar diretório '{CONFIG_DIR}': {e}. Verifique permissões.")
            sys.exit(1)

    rss_example_path = CONFIG_DIR / RSS_SOURCES_FILENAME
    if not rss_example_path.exists():
        example_rss_cfg = [{"source_name": "Exemplo Feed RSS", "feed_url": "URL_EXEMPLO_RSS_AQUI", "category": "Geral", "target_company_ticker": None, "target_segment_name": None, "publisher_domain_override": None}]
        try:
            with open(rss_example_path, 'w', encoding='utf-8') as f: json.dump(example_rss_cfg, f, indent=4)
            print(f"Arquivo de exemplo '{RSS_SOURCES_FILENAME}' criado em '{CONFIG_DIR}'. Edite-o.")
        except IOError as e: print(f"Erro ao criar arquivo de exemplo '{RSS_SOURCES_FILENAME}': {e}")

    credibility_example_path = CONFIG_DIR / CREDIBILITY_FILENAME
    if not credibility_example_path.exists():
        example_cred_cfg = {"example.com": {"source_name": "Exemplo Publicador", "overall_credibility_score": 0.7, "assessment_date": "YYYY-MM-DD"}}
        try:
            with open(credibility_example_path, 'w', encoding='utf-8') as f: json.dump(example_cred_cfg, f, indent=4)
            print(f"Arquivo de exemplo '{CREDIBILITY_FILENAME}' criado em '{CONFIG_DIR}'. Popule-o.")
        except IOError as e: print(f"Erro ao criar arquivo de exemplo '{CREDIBILITY_FILENAME}': {e}")
            
    main()