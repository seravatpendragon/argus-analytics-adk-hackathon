# src/scripts/news_data/newsapicollector.py

import json
import os
import sys
import time
from config import settings
from datetime import date, datetime, timezone
from urllib.parse import urlparse # Adicionado para fallback em get_domain_from_url
import tldextract # pip install tldextract
import requests
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

# --- Configuração de Caminhos para Imports do Projeto ---
# Presume que este script está em src/scripts/news_data/
# A raiz do projeto seria .../../.. (tres níveis acima)
try:
    CURRENT_SCRIPT_PATH = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_SCRIPT_PATH, "..", "..", ".."))
    if PROJECT_ROOT not in sys.path:
        sys.path.append(PROJECT_ROOT)
    settings.logger.info(f"PROJECT_ROOT adicionado ao sys.path: {PROJECT_ROOT}") # Debug
except NameError: # __file__ not defined, e.g. in interactive mode
    PROJECT_ROOT = os.path.abspath(os.path.join(os.getcwd()))
    if PROJECT_ROOT not in sys.path:
        sys.path.append(PROJECT_ROOT)
    settings.logger.info(f"AVISO: __file__ não definido. Usando PROJECT_ROOT como: {PROJECT_ROOT}")


try:
    from config import settings # Para API Keys e logger
    from src.database.db_utils import (
        get_db_session,
        get_or_create_news_source,
        get_company_id_for_ticker,
        get_segment_id_by_name
    )
    from src.database.create_db_tables import ( # Modelos SQLAlchemy
        NewsArticle,
        NewsArticleCompanyLink,
        NewsArticleSegmentLink
        # NewsSource, Company, Segment são usados internamente por db_utils
    )
    settings.logger.info("Módulos do projeto importados com sucesso.") # Debug
except ImportError as e:
    settings.logger.info(f"Erro CRÍTICO em newsapicollector.py ao importar módulos: {e}")
    settings.logger.info(f"sys.path atual: {sys.path}")
    settings.logger.info(f"Verifique se o PROJECT_ROOT ({PROJECT_ROOT}) está correto e se os módulos existem.")
    sys.exit(1)
except Exception as e:
    settings.logger.info(f"Erro inesperado durante imports iniciais: {e}")
    sys.exit(1)


# --- Constantes de Configuração ---
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
NEWSAPI_CONFIG_FILENAME = "newsapi_news_config.json"
CREDIBILITY_FILENAME = "news_source_domain.json"


# --- Funções Utilitárias ---
def load_json_file(file_path: str) -> dict | None:
    """Carrega um arquivo JSON de forma segura."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        settings.logger.error(f"Arquivo de configuração não encontrado: {file_path}")
        return None
    except json.JSONDecodeError as e:
        settings.logger.error(f"Erro ao decodificar JSON de {file_path}: {e}")
        return None
    except Exception as e:
        settings.logger.error(f"Erro inesperado ao ler {file_path}: {e}", exc_info=True)
        return None

def get_domain_from_url(url: str) -> str | None:
    """Extrai o domínio registrável (ex: google.com) de uma URL, normalizado e sem 'www.'."""
    if not url:
        return None
    try:
        # Usar `include_psl_private_domains=True` pode ser útil para alguns domínios .co.uk, .com.br, etc.
        # Mas para consistência com o que é geralmente desejado como "domínio principal", o padrão é bom.
        extracted = tldextract.extract(url)
        domain = extracted.top_domain_under_public_suffix # Retorna 'google.com' de 'news.google.com'
        if domain:
            return domain.lower() # tldextract já remove www. do registered_domain
        # Fallback se registered_domain for vazio (ex: IP, localhost)
        hostname = urlparse(url).hostname
        if hostname:
            return hostname.lower().replace("www.", "") # Remover www. manualmente se for hostname
        return None
    except Exception as e:
        settings.logger.warning(f"Não foi possível extrair domínio de '{url}' usando tldextract: {e}. Tentando fallback.")
        try: # Fallback mais simples se tldextract falhar por alguma razão
            hostname = urlparse(url).hostname
            if hostname:
                # Remover www. manualmente e converter para minúsculas
                return hostname.lower().replace("www.", "")
        except Exception as final_e:
            settings.logger.error(f"Falha total ao extrair domínio/hostname de '{url}': {final_e}", exc_info=True)
        return None


def assign_initial_article_type(title: str | None, summary: str | None) -> str:
    """Atribui um tipo de artigo inicial baseado em palavras-chave (heurística)."""
    title_lower = title.lower() if title else ""
    summary_lower = summary.lower() if summary else ""
    text_to_search = title_lower + " " + summary_lower

    if not text_to_search.strip():
        return "Outros"

    if "fato relevante" in text_to_search:
        return "Fato Relevante"
    if "resultado" in text_to_search and \
       ("trimestral" in text_to_search or "balanço" in text_to_search or \
        "lucro" in text_to_search or "anual" in text_to_search or "reporta" in text_to_search): # Adicionado "reporta"
        return "Resultados Trimestrais/Anuais"
    if "dividendo" in text_to_search or "jcp" in text_to_search or "provento" in text_to_search:
        return "Dividendos"
    if "cotação" in text_to_search or "preço da ação" in text_to_search or "recomendação" in text_to_search:
        return "Mercado/Cotação"
    # Adicione mais heurísticas conforme necessário
    return "Outros"


# --- Lógica Principal de Coleta da NewsAPI ---
def collect_articles_from_newsapi(
        newsapi_config: dict,
        loaded_credibility_data: dict,
        db_session: Session
    ) -> int:
    """
    Coleta artigos da NewsAPI, processa-os e salva no banco de dados.
    Retorna o número de novos artigos salvos.
    """
    if not hasattr(settings, 'NEWSAPI_API_KEY') or not settings.NEWSAPI_API_KEY:
        settings.logger.error("NEWSAPI_API_KEY não configurada em settings.py. Coleta da NewsAPI abortada.")
        return 0

    base_url = newsapi_config.get("base_url")
    queries = newsapi_config.get("queries", []) # Lista de configurações de query

    if not base_url or not queries:
        settings.logger.error("Configuração 'base_url' ou 'queries' ausente para NewsAPI. Coleta abortada.")
        return 0

    headers = {"X-Api-Key": settings.NEWSAPI_API_KEY}
    total_new_articles_saved_session = 0
    
    num_queries = len(queries) # Total de queries a serem processadas

    for i, query_config in enumerate(queries): # Usamos enumerate para saber o índice da query atual
        query_name = query_config.get("query_name", "Query NewsAPI Padrão")
        params = query_config.get("params", {})
        target_company_ticker = query_config.get("target_company_ticker")
        target_segment_name = query_config.get("target_segment_name")

        settings.logger.info(f"Executando NewsAPI Query: '{query_name}' com parâmetros: {params} ({i+1}/{num_queries})")

        try:
            response = requests.get(base_url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            api_response_data = response.json()
        except requests.exceptions.RequestException as e:
            settings.logger.error(f"Erro na requisição à NewsAPI para query '{query_name}': {e}")
            # Adiciona delay mesmo em caso de erro na request para não bombardear a API
            if i < num_queries - 1: # Se não for a última query
                try:
                    time.sleep(settings.API_DELAYS["NEWSAPI"])
                    settings.logger.info(f"Aguardando {settings.API_DELAYS['NEWSAPI']}s após erro antes da próxima query da NewsAPI...")
                except (AttributeError, KeyError, TypeError) as delay_exc: # TypeError para caso API_DELAYS não seja dict ou NEWSAPI não seja número
                    settings.logger.warning(f"Configuração API_DELAYS['NEWSAPI'] inválida ou não encontrada em settings ({delay_exc}). Sem delay aplicado após erro.")
            continue 
        except json.JSONDecodeError as e:
            settings.logger.error(f"Erro ao decodificar JSON da NewsAPI para query '{query_name}': {e}. Resposta: {response.text[:200]}")
            # Similar ao acima, adicionar delay após erro
            if i < num_queries - 1:
                try:
                    time.sleep(settings.API_DELAYS["NEWSAPI"])
                    settings.logger.info(f"Aguardando {settings.API_DELAYS['NEWSAPI']}s após erro de JSON antes da próxima query da NewsAPI...")
                except (AttributeError, KeyError, TypeError) as delay_exc:
                    settings.logger.warning(f"Configuração API_DELAYS['NEWSAPI'] inválida ou não encontrada em settings ({delay_exc}). Sem delay aplicado após erro.")
            continue

        if api_response_data.get("status") != "ok":
            settings.logger.warning(f"NewsAPI retornou status não 'ok' para query '{query_name}': {api_response_data.get('message')}")
            # Adicionar delay aqui também
            if i < num_queries - 1:
                try:
                    time.sleep(settings.API_DELAYS["NEWSAPI"])
                    settings.logger.info(f"Aguardando {settings.API_DELAYS['NEWSAPI']}s após status não 'ok' antes da próxima query da NewsAPI...")
                except (AttributeError, KeyError, TypeError) as delay_exc:
                    settings.logger.warning(f"Configuração API_DELAYS['NEWSAPI'] inválida ou não encontrada em settings ({delay_exc}). Sem delay aplicado após status não 'ok'.")
            continue
        
        articles_from_api = api_response_data.get("articles", [])
        if not articles_from_api:
            settings.logger.info(f"Nenhum artigo encontrado na NewsAPI para a query: '{query_name}'.")
            # Mesmo sem artigos, aplicamos delay se houver próxima query
            if i < num_queries - 1:
                try:
                    time.sleep(settings.API_DELAYS["NEWSAPI"])
                    settings.logger.info(f"Aguardando {settings.API_DELAYS['NEWSAPI']}s (nenhum artigo encontrado) antes da próxima query da NewsAPI...")
                except (AttributeError, KeyError, TypeError) as delay_exc:
                    settings.logger.warning(f"Configuração API_DELAYS['NEWSAPI'] inválida ou não encontrada em settings ({delay_exc}). Sem delay aplicado.")
            continue # Pula para a próxima query
            
        settings.logger.info(f"Recebidos {len(articles_from_api)} artigos da NewsAPI para '{query_name}'. Processando...")
        
        new_articles_for_this_query = 0
        for api_article in articles_from_api:
            # ... (toda a sua lógica de processamento do artigo:
            #        verificar duplicidade, extrair dados, get_or_create_news_source,
            #        criar NewsArticle, criar links, etc.) ...
            # Exemplo de onde ficaria o log do artigo processado (se novo)
            # if article_foi_salvo: new_articles_for_this_query += 1
            # ... (sua lógica atual de processamento do api_article) ...
            article_link = api_article.get("url")
            if not article_link:
                settings.logger.warning("Artigo da NewsAPI recebido sem URL. Pulando.")
                continue

            try:
                existing_db_article = db_session.query(NewsArticle.news_article_id).filter(NewsArticle.article_link == article_link).first()
                if existing_db_article:
                    settings.logger.debug(f"Artigo já existe no BD (link): {article_link[:70]}...")
                    continue
            except Exception as e:
                settings.logger.error(f"Erro ao verificar duplicidade do artigo {article_link}: {e}", exc_info=True)
                continue

            title_raw = api_article.get("title")
            title = title_raw if title_raw else "Sem Título"
            summary = api_article.get("description")
            published_at_str = api_article.get("publishedAt")
            publication_date_dt = None
            if published_at_str:
                try:
                    publication_date_dt = datetime.fromisoformat(published_at_str.replace("Z", "+00:00")).astimezone(timezone.utc)
                except ValueError:
                    settings.logger.warning(f"Formato de data inválido da NewsAPI: {published_at_str} para artigo '{title}'. Usando data atual.")
                    publication_date_dt = datetime.now(timezone.utc)

            source_api_name = api_article.get("source", {}).get("name")
            source_domain = get_domain_from_url(article_link)

            if not source_domain:
                settings.logger.warning(f"Não foi possível obter domínio para o artigo: '{title}' (Link: {article_link}). Pulando.")
                continue
            
            news_source_obj = get_or_create_news_source(
                db_session, source_domain, source_api_name, loaded_credibility_data
            )

            if not news_source_obj:
                settings.logger.error(f"Falha crítica ao obter/criar NewsSource para domínio '{source_domain}'. Artigo '{title}' não será salvo.")
                continue

            initial_article_type = assign_initial_article_type(title, summary)

            try:
                new_article_to_save = NewsArticle(
                    headline=title, # Já tratado para não ser None
                    article_link=article_link,
                    publication_date=publication_date_dt,
                    news_source_id=news_source_obj.news_source_id,
                    summary=summary,
                    article_text_content=None,
                    article_type=initial_article_type,
                    processing_status='pending_full_text_fetch',
                    source_feed_name=f"NewsAPI - {query_name}",
                    collection_date=datetime.now(timezone.utc)
                )
                db_session.add(new_article_to_save)
                db_session.flush()

                company_id_to_link = get_company_id_for_ticker(db_session, target_company_ticker) if target_company_ticker else None
                if company_id_to_link:
                    link_c_exists = db_session.query(NewsArticleCompanyLink).filter_by(
                        news_article_id=new_article_to_save.news_article_id, company_id=company_id_to_link
                    ).first()
                    if not link_c_exists:
                        db_session.add(NewsArticleCompanyLink(news_article_id=new_article_to_save.news_article_id, company_id=company_id_to_link))
                
                segment_id_to_link = get_segment_id_by_name(db_session, target_segment_name) if target_segment_name else None
                if segment_id_to_link:
                    link_s_exists = db_session.query(NewsArticleSegmentLink).filter_by(
                        news_article_id=new_article_to_save.news_article_id, segment_id=segment_id_to_link
                    ).first()
                    if not link_s_exists:
                         db_session.add(NewsArticleSegmentLink(news_article_id=new_article_to_save.news_article_id, segment_id=segment_id_to_link))
                
                new_articles_for_this_query += 1
                log_title_display = title if title != "Sem Título" else "Artigo sem título ou com título None"
                settings.logger.info(f"Novo artigo da NewsAPI adicionado à sessão: '{log_title_display[:50]}...' (Fonte: {source_domain})")

            except IntegrityError:
                db_session.rollback()
                settings.logger.warning(f"Erro de integridade ao tentar salvar artigo (provável duplicata): {article_link}")
            except Exception as e:
                db_session.rollback()
                settings.logger.error(f"Erro ao criar objeto NewsArticle ou links para '{title}': {e}", exc_info=True)
        
        if new_articles_for_this_query > 0:
            try:
                db_session.commit()
                settings.logger.info(f"{new_articles_for_this_query} novos artigos da query '{query_name}' commitados no BD.")
                total_new_articles_saved_session += new_articles_for_this_query
            except Exception as e:
                db_session.rollback()
                settings.logger.error(f"Erro no commit da NewsAPI para query '{query_name}': {e}", exc_info=True)
        else:
            settings.logger.info(f"Nenhum artigo novo para commitar da query '{query_name}'.")

        # --- ADICIONAR DELAY AQUI ---
        # Só aplica delay se houver mais queries e esta não for a última
        if i < num_queries - 1:
            try:
                # Acessa a configuração de delay do settings.py
                # Exemplo: settings.API_DELAYS = {"NEWSAPI": 1, "OUTRA_API": 5}
                time.sleep(settings.API_DELAYS["NEWSAPI"])
                if isinstance(settings.API_DELAYS["NEWSAPI"], (int, float)) and settings.API_DELAYS["NEWSAPI"] > 0:
                    settings.logger.info(f"Aguardando {settings.API_DELAYS['NEWSAPI']}s antes da próxima query da NewsAPI...")
                else:
                    settings.logger.warning(f"Valor de delay inválido para NEWSAPI em settings.API_DELAYS: {settings.API_DELAYS['NEWSAPI']}. Sem delay aplicado.")
            except (AttributeError, KeyError, TypeError) as e: # AttributeError se API_DELAYS não existir, KeyError se "NEWSAPI" não existir, TypeError se valor não numérico
                settings.logger.warning(f"Configuração API_DELAYS['NEWSAPI'] não encontrada ou inválida em settings.py ({e}). Sem delay aplicado entre queries.")
            except Exception as e: # Captura outros erros inesperados no delay
                 settings.logger.error(f"Erro inesperado ao tentar aplicar delay: {e}", exc_info=True)
        # --- FIM DO DELAY ---

    return total_new_articles_saved_session

# --- Função Principal do Coletor ---
def main():
    """Função principal para orquestrar a coleta de notícias da NewsAPI."""
    
    # Garantir que o logger de settings esteja disponível
    if not hasattr(settings, 'logger'):
        # Configuração de logger fallback muito simples se settings.py não tiver um
        import logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        settings.logger = logging.getLogger("newsapicollector")
        settings.logger.info("Logger fallback configurado para newsapicollector.")

    settings.logger.info("=== Iniciando Coletor de Notícias da NewsAPI ===")

    # 1. Carregar configurações externas
    newsapi_config_path = os.path.join(CONFIG_DIR, NEWSAPI_CONFIG_FILENAME)
    credibility_config_path = os.path.join(CONFIG_DIR, CREDIBILITY_FILENAME)

    newsapi_config_main = load_json_file(newsapi_config_path)
    loaded_credibility_data = load_json_file(credibility_config_path)

    if not newsapi_config_main or "newsapi" not in newsapi_config_main:
        settings.logger.critical(f"Configuração da NewsAPI não encontrada ou inválida em '{newsapi_config_path}'. Abortando.")
        return
    
    newsapi_specific_config = newsapi_config_main["newsapi"] # Pega a parte específica da NewsAPI

    if loaded_credibility_data is None: # Se o arquivo não existe ou é inválido, load_json_file retorna None
        settings.logger.warning(f"Dados de credibilidade de '{credibility_config_path}' não carregados. Novas fontes receberão score padrão, mas nomes de fontes conhecidas podem não ser os ideais.")
        loaded_credibility_data = {} # Usa um dicionário vazio para evitar erros, scores virão do default em db_utils

    # 2. Obter sessão do banco de dados
    db_session: Session | None = None
    try:
        db_session = get_db_session() # Do seu db_utils.py
        settings.logger.info("Sessão do banco de dados obtida com sucesso.")

        # 3. Chamar a lógica de coleta
        num_articles_saved = collect_articles_from_newsapi(
            newsapi_specific_config,
            loaded_credibility_data,
            db_session
        )
        settings.logger.info(f"Total de {num_articles_saved} novos artigos da NewsAPI foram salvos nesta execução.")

    except Exception as e:
        settings.logger.critical(f"Erro catastrófico no script principal newsapicollector: {e}", exc_info=True)
        if db_session: # Tentar rollback se houve erro com sessão aberta
            try:
                db_session.rollback()
            except Exception as rb_e:
                settings.logger.error(f"Erro ao tentar rollback da sessão: {rb_e}")
    finally:
        if db_session:
            settings.logger.info("Fechando sessão do banco de dados.")
            db_session.close()

    settings.logger.info("=== Coletor de Notícias da NewsAPI Finalizado ===")


if __name__ == "__main__":
    # Este bloco é executado quando o script é chamado diretamente

    # Opcional: Criar arquivos de config de exemplo se não existirem
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
        settings.logger.info(f"Diretório '{CONFIG_DIR}' criado.")

    newsapi_example_path = os.path.join(CONFIG_DIR, NEWSAPI_CONFIG_FILENAME)
    if not os.path.exists(newsapi_example_path):
        example_api_cfg = {
            "newsapi": {
                "base_url": "https://newsapi.org/v2/everything",
                "queries": [{
                    "query_name": "Exemplo Petrobras (NewsAPI)",
                    "params": {"q": "Petrobras OR PETR4", "language": "pt", "pageSize": 5},
                    "target_company_ticker": "PETR4"
                }]
            }
        }
        with open(newsapi_example_path, 'w', encoding='utf-8') as f:
            json.dump(example_api_cfg, f, indent=4)
        settings.logger.info(f"Arquivo de exemplo '{NEWSAPI_CONFIG_FILENAME}' criado. Edite-o.")

    credibility_example_path = os.path.join(CONFIG_DIR, CREDIBILITY_FILENAME)
    if not os.path.exists(credibility_example_path):
        example_cred_cfg = {
            "exemplo.com": {"source_name": "Site Exemplo", "overall_credibility_score": 0.7, "assessment_date": "2025-01-01"}
        }
        with open(credibility_example_path, 'w', encoding='utf-8') as f:
            json.dump(example_cred_cfg, f, indent=4)
        settings.logger.info(f"Arquivo de exemplo '{CREDIBILITY_FILENAME}' criado. Popule-o.")

    main()