# src/database/db_utils.py
# -*- coding: utf-8 -*-

import json
import re
import sys
import os
from venv import logger
from sqlalchemy import create_engine, or_, select, func, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects import postgresql
from datetime import date, datetime, timezone
import pandas as pd # Adicionado para o caso de uso de get_latest_effective_date

from typing import List, Dict, Optional # Para type hints (opcional, mas boa prática)

# Importe seu logger de settings e o modelo EconomicIndicatorValue
from config import settings
from .create_db_tables import EconomicDataSource, EconomicIndicatorValue
from sqlalchemy.exc import IntegrityError

# Adiciona o diretório raiz do projeto ao sys.path
project_root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root_path not in sys.path:
    sys.path.append(project_root_path)

try:
    from config import settings
    from src.database.create_db_tables import ( # Garanta que create_db_tables.py esteja em src/database/
        Base, EconomicIndicator, EconomicIndicatorValue, Company,
        EconomicSector, Subsector, Segment,
        AnalyticalTheory, TheoryFrameworkDimension, CompanyMaslowProfile,
        # --- ADICIONE ESTES MODELOS ---
        NewsSource, NewsArticle, NewsArticleCompanyLink, NewsArticleSegmentLink
        # --- FIM DA ADIÇÃO ---
    )
except ImportError as e:
    settings.logger.error(f"Erro CRÍTICO em db_utils.py ao importar settings ou modelos: {e}")
    # Verifique se o arquivo create_db_tables.py está no local correto (src/database/)
    # e se todos os modelos acima estão definidos nele.
    sys.exit(1)

_engine = None

def get_db_engine():
    """
    Retorna a engine SQLAlchemy singleton para o banco ativo.
    """
    global _engine
    if _engine is None:
        if not settings.ACTIVE_DATABASE_URL:
            settings.logger.critical("db_utils: ACTIVE_DATABASE_URL não configurada.")
            raise ValueError("ACTIVE_DATABASE_URL não configurada.")
        _engine = create_engine(settings.ACTIVE_DATABASE_URL, **settings.SQLALCHEMY_ENGINE_OPTIONS)
        settings.logger.info("db_utils: Engine do banco de dados criada.")
    return _engine

def get_db_session() -> Session:
    """
    Cria e retorna uma nova sessão SQLAlchemy para o banco ativo.
    """
    engine = get_db_engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    settings.logger.debug("db_utils: Nova sessão do banco criada.")
    return session

        
def get_segment_id_by_name(session: Session, segment_name: str) -> int | None:
    """
    Retorna o segment_id para o nome do segmento informado, ou None se não encontrado.
    """
    if not segment_name or not segment_name.strip():
        settings.logger.debug("get_segment_id_by_name: segment_name não fornecido ou vazio.")
        return None

    search_name = segment_name.strip()
    settings.logger.debug(f"Buscando segment_id para o nome: '{search_name}'")

    # Ajuste o filtro se o nome do seu segmento estiver em outra tabela ou precisar de join
    stmt = select(Segment.segment_id).where(func.lower(Segment.name) == func.lower(search_name))
    segment_id = session.execute(stmt).scalar_one_or_none()

    if segment_id is not None:
        settings.logger.debug(f"Segment_id {segment_id} encontrado para o nome: '{search_name}'")
        return segment_id

    settings.logger.info(f"Nenhum segmento encontrado para o nome: '{search_name}' em get_segment_id_by_name.")
    return None

def get_company_id_for_ticker(session: Session, ticker_symbol: str) -> int | None:
    """
    Retorna o company_id para o ticker informado, ou None se não encontrado.
    """
    settings.logger.debug(f"Buscando company_id para o ticker: '{ticker_symbol}'")
    stmt = select(Company.company_id).where(Company.ticker == ticker_symbol)
    company_id = session.execute(stmt).scalar_one_or_none()
    if company_id is not None:
        settings.logger.debug(f"Company_id {company_id} encontrado para o ticker: '{ticker_symbol}'")
        return company_id
    settings.logger.info(f"Nenhuma empresa encontrada para o ticker: '{ticker_symbol}' em get_company_id_for_ticker.")
    return None

def get_or_create_indicator_id(session: Session, indicator_name: str, indicator_type: str, 
                               frequency: str, unit: str, econ_data_source_id: int = None) -> int | None:
    """
    Busca ou cria um indicador econômico pelo nome e tipo.
    Atualiza frequência, unidade e fonte se necessário.
    """
    search_name = indicator_name.strip()
    search_type = indicator_type.strip()

    settings.logger.info(f"---- GET_OR_CREATE_INDICATOR ----")
    settings.logger.info(f"Buscando por: Nome='{search_name}' (Original: '{indicator_name}'), Tipo='{search_type}' (Original: '{indicator_type}')")

    indicator = session.query(EconomicIndicator)\
                     .filter(EconomicIndicator.name == search_name, 
                             EconomicIndicator.indicator_type == search_type)\
                     .first()

    if indicator:
        updated = False
        if indicator.frequency != frequency: indicator.frequency = frequency; updated = True
        if indicator.unit != unit: indicator.unit = unit; updated = True
        if econ_data_source_id is not None and indicator.econ_data_source_id != econ_data_source_id:
            indicator.econ_data_source_id = econ_data_source_id; updated = True
        if updated:
            try:
                session.commit()
                settings.logger.debug(f"Indicador ID {indicator.indicator_id} '{search_name}' atualizado.")
            except Exception as e:
                session.rollback()
                settings.logger.error(f"Erro ao ATUALIZAR indicador '{search_name}': {e}")
        return indicator.indicator_id
    else:
        new_indicator = EconomicIndicator(name=search_name, indicator_type=search_type, frequency=frequency, unit=unit, econ_data_source_id=econ_data_source_id)
        session.add(new_indicator)
        session.flush() # Usa flush para atribuir o ID sem commitar a transação
        logger.info(f"Novo indicador preparado para inserção: ID {new_indicator.indicator_id} para Nome='{search_name}'")
        return new_indicator.indicator_id

def get_or_create_news_source(session: Session,
                              source_domain: str,
                              source_api_name: str | None,
                              loaded_credibility_data: dict,
                              default_unverified_score: float = 0.6) -> NewsSource | None:
    if not source_domain:
        settings.logger.warning("get_or_create_news_source: source_domain não fornecido.")
        return None

    normalized_domain = source_domain.lower()
    if normalized_domain.startswith("www."):
        normalized_domain = normalized_domain[4:]

    # 1. Tenta buscar a fonte existente
    news_source = session.query(NewsSource).filter(NewsSource.url_base == normalized_domain).first()

    if news_source:
        settings.logger.debug(f"NewsSource ENCONTRADA no BD para '{normalized_domain}': ID {news_source.news_source_id}, Score: {news_source.base_credibility_score}")
        # Opcional: Lógica para atualizar score se o JSON mudou e é mais recente.
        # Isso seria mais apropriado para o script sync_credibility_to_db.py.
        # Por ora, se a fonte existe, apenas a retornamos.
        # Contudo, se o nome no JSON for diferente do nome no BD, PODERÍAMOS atualizar o nome aqui.
        credibility_info_json = loaded_credibility_data.get(normalized_domain)
        if credibility_info_json:
            json_source_name = credibility_info_json.get("source_name")
            json_score = credibility_info_json.get("overall_credibility_score") # Score do JSON
            
            made_changes = False
            if json_source_name and news_source.name != json_source_name:
                settings.logger.info(f"DB_UTILS: Atualizando nome da NewsSource ID {news_source.news_source_id} de '{news_source.name}' para '{json_source_name}' (do JSON).")
                news_source.name = json_source_name[:255]
                made_changes = True
            
            # Decide se atualiza o score:
            # Poderíamos sempre atualizar para o score do JSON se a fonte for encontrada no JSON.
            # Ou apenas se o score atual for o default (0.6), indicando que foi auto-criada antes.
            if json_score is not None and news_source.base_credibility_score != json_score:
                 # Se o score atual é o default E o JSON tem um score diferente, atualiza.
                 # OU se simplesmente queremos que o JSON sempre sobreponha o que está no BD para fontes conhecidas.
                 # Para este exemplo, vamos sempre atualizar para o score do JSON se a fonte estiver no JSON.
                settings.logger.info(f"DB_UTILS: Atualizando score da NewsSource ID {news_source.news_source_id} de '{news_source.base_credibility_score}' para '{json_score}' (do JSON).")
                news_source.base_credibility_score = json_score
                made_changes = True

            if made_changes:
                try:
                    session.commit()
                except Exception as e_commit_update:
                    session.rollback()
                    settings.logger.error(f"DB_UTILS: Erro ao commitar atualização para NewsSource '{normalized_domain}': {e_commit_update}", exc_info=True)
                    # Retorna o objeto news_source como estava antes da tentativa de atualização com falha no commit
                    # Para isso, precisamos re-buscar ou não alterar o objeto em memória se o commit falhar.
                    # Por simplicidade, vamos assumir que a atualização ou funciona ou o objeto não é alterado de forma inconsistente.
                    # Uma forma mais segura seria:
                    # old_name = news_source.name
                    # old_score = news_source.base_credibility_score
                    # news_source.name = ...
                    # news_source.base_credibility_score = ...
                    # try: session.commit()
                    # except: session.rollback(); news_source.name = old_name; news_source.base_credibility_score = old_score

        return news_source
    else:
        # Fonte não existe no BD, vamos criar.
        settings.logger.debug(f"DB_UTILS: NewsSource para '{normalized_domain}' não encontrada no BD. Tentando criar.")
        credibility_info_json = loaded_credibility_data.get(normalized_domain)
        
        score_to_assign = default_unverified_score
        name_for_db = normalized_domain # Default name se não estiver no JSON

        if credibility_info_json:
            name_for_db = credibility_info_json.get("source_name", normalized_domain)
            score_to_assign = credibility_info_json.get("overall_credibility_score", default_unverified_score)
            settings.logger.info(
                f"DB_UTILS: Fonte '{normalized_domain}' encontrada no JSON. Nome no BD: '{name_for_db}', Score: {score_to_assign}"
            )
        else:
            settings.logger.warning(
                f"DB_UTILS: Fonte DESCONHECIDA '{normalized_domain}' (Hint original do feed/API: '{source_api_name}') não encontrada em news_source_domain.json. "
                f"Nome da fonte no BD será '{name_for_db}'. Atribuindo score base {score_to_assign}. "
                f"Por favor, revise e adicione ao JSON."
            )
        
        new_source = NewsSource(
            name=name_for_db[:255],
            url_base=normalized_domain,
            base_credibility_score=score_to_assign
        )
        session.add(new_source)
        try:
            session.commit()
            settings.logger.info(f"DB_UTILS: Nova NewsSource ID {new_source.news_source_id} CRIADA para '{normalized_domain}' com nome '{new_source.name}' e score {new_source.base_credibility_score}.")
            return new_source
        except IntegrityError as ie: # Captura a exceção para logar detalhes
            session.rollback()
            # Log detalhado do erro de integridade
            error_detail = getattr(ie, 'orig', repr(ie)) # Tenta pegar a exceção original do driver (psycopg2)
            constraint_name_match = re.search(r'constraint "([^"]+)"', str(error_detail)) # Tenta pegar nome da constraint
            constraint_violated = constraint_name_match.group(1) if constraint_name_match else "desconhecida"

            settings.logger.error(
                f"DB_UTILS: Erro de INTEGRIDADE ao COMITAR criação de NewsSource para '{normalized_domain}'. "
                f"Constraint violada: '{constraint_violated}'. Detalhes: {error_detail}. Tentando buscar novamente."
            )
            
            # Tenta buscar novamente, pois pode ter sido criada por outra transação concorrente (raro)
            # ou a primeira busca falhou por algum motivo sutil.
            retry_source = session.query(NewsSource).filter(NewsSource.url_base == normalized_domain).first()
            if retry_source:
                settings.logger.info(f"DB_UTILS: NewsSource para '{normalized_domain}' ENCONTRADA na RETENTATIVA de busca. ID: {retry_source.news_source_id}. Score no BD: {retry_source.base_credibility_score}")
                # Opcional: se o score no BD for 0.6 e o JSON tiver um score melhor, atualizar aqui.
                if credibility_info_json and retry_source.base_credibility_score == default_unverified_score:
                    json_score = credibility_info_json.get("overall_credibility_score")
                    json_name = credibility_info_json.get("source_name")
                    if json_score is not None and json_score != default_unverified_score:
                        settings.logger.info(f"DB_UTILS: Fonte '{normalized_domain}' (ID {retry_source.news_source_id}) encontrada na retentativa com score padrão. "
                                            f"JSON tem score {json_score}. ATUALIZANDO.")
                        retry_source.base_credibility_score = json_score
                        if json_name: retry_source.name = json_name[:255]
                        try:
                            session.commit()
                            settings.logger.info(f"DB_UTILS: Score/Nome da NewsSource ID {retry_source.news_source_id} atualizado para {retry_source.base_credibility_score}/{retry_source.name} via retentativa.")
                        except Exception as e_update_retry:
                            session.rollback()
                            settings.logger.error(f"DB_UTILS: Erro ao ATUALIZAR NewsSource ID {retry_source.news_source_id} na retentativa: {e_update_retry}")
                return retry_source
            else:
                settings.logger.critical(
                    f"DB_UTILS: NewsSource para '{normalized_domain}' NÃO encontrada na retentativa de busca após IntegrityError. "
                    f"Isso é INESPERADO se a constraint violada foi em 'url_base'. Verifique outras constraints UNIQUE (ex: 'name')."
                )
                return None
        except Exception as e: # Outras exceções durante o commit
            session.rollback()
            settings.logger.error(f"DB_UTILS: Erro desconhecido ao criar NewsSource para '{normalized_domain}': {e}", exc_info=True)
            return None

def normalize_indicator_values(data_list, sentinel=1):
    """
    Substitui None por sentinel nos campos company_id e segment_id.
    """
    for d in data_list:
        if d.get('company_id') is None:
            d['company_id'] = sentinel
        if d.get('segment_id') is None:
            d['segment_id'] = sentinel
    return data_list

def batch_upsert_indicator_values(session, data_to_insert_list):
    """
    Realiza upsert em lote para EconomicIndicatorValue.
    Agora depende do índice único (NOT NULL) e do ON CONFLICT do Postgres.
    """
    if not data_to_insert_list:
        settings.logger.info("batch_upsert_indicator_values: Nenhuma lista para inserir.")
        return 0

    table = EconomicIndicatorValue.__table__
    # Normaliza os dados para garantir que não haja None
    normalize_indicator_values(data_to_insert_list, sentinel=1)

    insert_stmt = pg_insert(table).values(data_to_insert_list)
    # Faz apenas insert ou ignora duplicatas (não faz update)
    upsert_stmt = insert_stmt.on_conflict_do_nothing(
        index_elements=['indicator_id', 'effective_date', 'company_id', 'segment_id']
    )
    try:
        result = session.execute(upsert_stmt)
        session.commit()
        rowcount = result.rowcount if result else 0
        settings.logger.info(
            f"{len(data_to_insert_list)} registros enviados para {table.name}. Inseridos: {rowcount}"
        )
        return rowcount
    except IntegrityError as e:
        session.rollback()
        settings.logger.error(f"Erro inesperado durante o batch insert em {table.name}: {e}", exc_info=True)
        raise

def get_latest_effective_date(session: Session, indicator_id_to_check: int, 
                              company_id_to_check: int = None, 
                              segment_id_to_check: int = None,
                              subsector_id_to_check: int = None,
                              economic_sector_id_to_check: int = None) -> date | None:
    """
    Retorna a data mais recente (effective_date) para o indicador e filtros informados.
    """
    settings.logger.debug(f"GET_LATEST_EFFECTIVE_DATE - Args: indicator_id={indicator_id_to_check}, company_id={company_id_to_check}, segment_id={segment_id_to_check}")
    
    q = session.query(func.max(EconomicIndicatorValue.effective_date))\
        .filter(EconomicIndicatorValue.indicator_id == indicator_id_to_check)

    if company_id_to_check is not None: q = q.filter(EconomicIndicatorValue.company_id == company_id_to_check)
    else: q = q.filter(EconomicIndicatorValue.company_id.is_(None))

    if segment_id_to_check is not None: q = q.filter(EconomicIndicatorValue.segment_id == segment_id_to_check)
    else: q = q.filter(EconomicIndicatorValue.segment_id.is_(None))
    
    if hasattr(EconomicIndicatorValue, 'subsector_id'):
        if subsector_id_to_check is not None: q = q.filter(EconomicIndicatorValue.subsector_id == subsector_id_to_check)
        else: q = q.filter(EconomicIndicatorValue.subsector_id.is_(None))

    if hasattr(EconomicIndicatorValue, 'economic_sector_id'):
        if economic_sector_id_to_check is not None: q = q.filter(EconomicIndicatorValue.economic_sector_id == economic_sector_id_to_check)
        else: q = q.filter(EconomicIndicatorValue.economic_sector_id.is_(None))
            
    latest_date_val = q.scalar()
    settings.logger.info(f"GET_LATEST_EFFECTIVE_DATE - Query Result para ind_id={indicator_id_to_check}: {latest_date_val}")
    return latest_date_val

# --- Função para CompanyMaslowProfile (como definida anteriormente) ---
def batch_upsert_company_maslow_profile(session: Session, data_to_upsert_list: list[dict]):
    """
    Realiza upsert em lote para perfis Maslow de empresas.
    """
    if not data_to_upsert_list:
        settings.logger.info("batch_upsert_company_maslow_profile: Nenhuma lista para inserir.")
        return

    table = CompanyMaslowProfile.__table__
    conflict_target_columns = ['company_id', 'maslow_dimension_id']
    
    processed_data_list = []
    all_expected_keys_maslow = {col.name for col in table.columns}

    for item_original in data_to_upsert_list:
        item_processed = {}
        valid_item = True
        for col_name in all_expected_keys_maslow:
            if col_name in item_original:
                item_processed[col_name] = item_original[col_name]
            elif col_name in conflict_target_columns or table.columns[col_name].nullable:
                item_processed[col_name] = None
            elif not table.columns[col_name].nullable and \
                 not table.columns[col_name].server_default and \
                 not (hasattr(table.columns[col_name], 'default') and table.columns[col_name].default):
                settings.logger.error(f"Coluna Maslow obrigatória '{col_name}' ausente em dados: {item_original}. Pulando.")
                valid_item = False
                break
        if valid_item:
            processed_data_list.append(item_processed)

    if not processed_data_list:
        settings.logger.info("batch_upsert_company_maslow_profile: Nenhum item válido para inserir após processamento.")
        return

    insert_stmt = pg_insert(table).values(processed_data_list)
    update_set = {
        'weight': insert_stmt.excluded.weight,
        'justification': insert_stmt.excluded.justification
    }

    final_stmt = insert_stmt.on_conflict_do_update(
        index_elements=conflict_target_columns,
        set_=update_set
    )
    try:
        session.execute(final_stmt)
        session.commit()
    except Exception as e:
        if "duplicate key value violates unique constraint" in str(e) or "duplicate key value violates unique index" in str(e):
            session.rollback()
            settings.logger.info("Registro duplicado ignorado pelo índice único com COALESCE.")
        else:
            raise
    settings.logger.info(f"{len(processed_data_list)} perfis Maslow de empresa processados (UPSERT).")

def get_or_create_indicator(session: Session, name: str, source_name: str, **kwargs) -> EconomicIndicator:
    """
    Busca um indicador pelo nome. Se não existir, cria o indicador e sua fonte de dados.
    Usa 'name' como o parâmetro para o nome do indicador.
    """
    indicator = session.query(EconomicIndicator).filter(EconomicIndicator.name == name).first()
    if indicator:
        return indicator

    settings.logger.info(f"Indicador '{name}' não encontrado, criando novo...")
    
    data_source = session.query(EconomicDataSource).filter(EconomicDataSource.name == source_name).first()
    if not data_source:
        data_source = EconomicDataSource(name=source_name)
        session.add(data_source)
        session.flush()

    new_indicator = EconomicIndicator(
        name=name,
        econ_data_source_id=data_source.econ_data_source_id,
        indicator_type=kwargs.get('indicator_type'),
        frequency=kwargs.get('frequency'),
        unit=kwargs.get('unit')
    )
    session.add(new_indicator)
    session.commit()
    return new_indicator


def batch_upsert_indicator_values(session: Session, data_to_insert_list: list[dict]):
    """
    Realiza UPSERT em lote para EconomicIndicatorValue.
    Se o registro já existe (mesmo indicador, data, empresa), ele atualiza os valores.
    """
    if not data_to_insert_list:
        logger.info("batch_upsert_indicator_values: Nenhuma lista para inserir.")
        return 0

    table = EconomicIndicatorValue.__table__
    insert_stmt = pg_insert(table).values(data_to_insert_list)

    # Lógica de UPSERT: Se o registro já existe, ATUALIZE os valores.
    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=['indicator_id', 'effective_date', 'company_id', 'segment_id'],
        set_={
            'value_numeric': insert_stmt.excluded.value_numeric,
            'value_text': insert_stmt.excluded.value_text,
            'collection_timestamp': datetime.now(timezone.utc)
        }
    )
    
    result = session.execute(upsert_stmt)
    logger.info(f"{result.rowcount} registros de valores de indicadores foram inseridos/atualizados na sessão.")
    return result.rowcount


def get_assets_by_source(source_name: str) -> List[Dict[str, any]]:
    """
    Busca no banco de dados todos os ativos (empresas) associados a uma fonte de dados específica.

    Args:
        source_name: O nome da fonte (ex: 'YFinance', 'Fundamentus').

    Returns:
        Uma lista de dicionários, cada um representando um ativo.
    """
    settings.logger.info(f"Buscando ativos para a fonte: '{source_name}'")
    session = get_db_session()
    try:
        # Assumindo que a tabela 'Company' tem uma coluna 'source'
        # e que queremos o ticker e o company_id.
        stmt = select(
            Company.company_id,
            Company.ticker,
            Company.company_name,
            Company.source
        ).where(Company.source == source_name)
        
        results = session.execute(stmt).mappings().all()
        
        assets_list = [dict(row) for row in results]
        
        if not assets_list:
            settings.logger.warning(f"Nenhum ativo encontrado para a fonte '{source_name}' no banco de dados.")
        else:
            settings.logger.info(f"{len(assets_list)} ativos encontrados para a fonte '{source_name}'.")
            
        return assets_list
    except Exception as e:
        settings.logger.error(f"Erro ao buscar ativos por fonte '{source_name}': {e}", exc_info=True)
        return []
    finally:
        session.close()

def get_all_tickers(session: Session) -> List[str]:
    """
    Busca e retorna uma lista de todos os tickers únicos da tabela Companies,
    usando a sessão fornecida.
    """
    logger.info("Buscando todos os tickers da tabela Companies.")
    try:
        # Seleciona apenas a coluna 'ticker' da tabela Company
        stmt = select(Company.ticker)
        results = session.execute(stmt).scalars().all()
        
        logger.info(f"Encontrados {len(results)} tickers no total.")
        return results
    except Exception as e:
        logger.error(f"Erro ao buscar todos os tickers: {e}", exc_info=True)
        return []

def get_or_create_data_source(session: Session, source_name: str) -> int:
    """
    Busca ou cria uma fonte de dados pelo nome e retorna seu ID,
    sem commitar a transação.
    """
    if not source_name:
        logger.error("get_or_create_data_source chamado com nome de fonte vazio.")
        return None

    source = session.query(EconomicDataSource).filter_by(name=source_name).first()
    
    if source:
        logger.debug(f"Fonte de dados encontrada: '{source_name}' (ID: {source.econ_data_source_id})")
        return source.econ_data_source_id
    else:
        logger.info(f"Fonte de dados '{source_name}' não encontrada. Criando nova.")
        new_source = EconomicDataSource(name=source_name)
        session.add(new_source)
        session.flush()  # Usa flush para obter o ID do novo objeto sem commitar a transação inteira
        logger.info(f"Nova fonte de dados preparada para inserção: '{source_name}' (ID: {new_source.econ_data_source_id})")
        return new_source.econ_data_source_id
    
def get_articles_pending_extraction(session: Session, limit: int = 20) -> list[NewsArticle]:
    """
    Busca no banco de dados uma lista de artigos cujo texto completo ainda não foi extraído,
    incluindo aqueles que estão prontos para retentativa.
    """
    settings.logger.info(f"Buscando até {limit} artigos pendentes ou para retentativa de extração...")

    articles = session.query(NewsArticle).filter(
        or_(
            NewsArticle.processing_status == 'pending_full_text_fetch',
            (NewsArticle.processing_status == 'pending_extraction_retry') & (NewsArticle.next_retry_at <= datetime.now())
        )
    ).order_by(NewsArticle.next_retry_at.asc().nulls_first(), NewsArticle.collection_date.asc()).limit(limit).all()

    settings.logger.info(f"Encontrados {len(articles)} artigos para extração/retentativa.")
    return articles
def update_article_with_full_text(session: Session, article_id: int, text_content: str | None, new_status: str):
    """
    Atualiza um artigo específico no banco de dados com o texto completo extraído
    e atualiza seu status de processamento.
    """
    # Esta função foi simplificada, pois a ferramenta agora manipula o objeto diretamente.
    # No entanto, a deixaremos aqui caso seja útil para outros módulos.
    # A lógica principal de atualização agora está na própria ferramenta.
    pass

# Em src/database/db_utils.py

def get_sources_pending_craap_analysis(session: Session, limit: int = 20) -> list[NewsSource]:
    """ Busca fontes de notícias que ainda não foram analisadas pelo CRAAP. """
    return session.query(NewsSource)\
        .filter(NewsSource.craap_status == 'pending_craap_analysis')\
        .limit(limit)\
        .all()

def update_source_craap_analysis(session: Session, source_id: int, score: float, analysis_json: dict):
    """ Atualiza uma fonte com o resultado da análise CRAAP. """
    source = session.query(NewsSource).filter(NewsSource.news_source_id == source_id).first()
    if source:
        source.base_credibility_score = score
        source.craap_analysis_json = analysis_json
        source.craap_status = 'craap_analysis_complete'
        # O commit será feito pelo script que chama a função
        return True
    return False

def get_or_create_sector(session: Session, sector_name: str) -> EconomicSector:
    """Busca ou cria um Setor Econômico e retorna o objeto."""
    sector = session.query(EconomicSector).filter_by(name=sector_name).first()
    if not sector:
        sector = EconomicSector(name=sector_name)
        session.add(sector)
        session.flush() # Aplica a transação para obter o ID do novo setor
        settings.logger.info(f"Criado novo Setor: '{sector_name}'")
    return sector

def get_or_create_subsector(session: Session, subsector_name: str, sector_id: int) -> Subsector:
    """Busca ou cria um Subsetor, vinculado a um Setor, e retorna o objeto."""
    subsector = session.query(Subsector).filter_by(name=subsector_name, economic_sector_id=sector_id).first()
    if not subsector:
        subsector = Subsector(name=subsector_name, economic_sector_id=sector_id)
        session.add(subsector)
        session.flush()
        settings.logger.info(f"  Criado novo Subsetor: '{subsector_name}'")
    return subsector

def get_or_create_segment(session: Session, segment_name: str, subsector_id: int) -> Segment:
    """Busca ou cria um Segmento, vinculado a um Subsetor, e retorna o objeto."""
    segment = session.query(Segment).filter_by(name=segment_name, subsector_id=subsector_id).first()
    if not segment:
        segment = Segment(name=segment_name, subsector_id=subsector_id)
        session.add(segment)
        session.flush()
        settings.logger.info(f"    Criado novo Segmento: '{segment_name}'")
    return segment

def get_articles_pending_analysis(session: Session, limit: int = 50) -> list[dict]:
    """
    Busca artigos que já tiveram seu conteúdo extraído e estão prontos para a análise de IA.
    """
    try:
        articles = (
            session.query(NewsArticle)
            .filter(NewsArticle.processing_status == 'pending_llm_analysis')
            .filter(NewsArticle.article_text_content != None)
            .limit(limit)
            .all()
        )
        settings.logger.info(f"Encontrados {len(articles)} artigos para análise.")
        # CORREÇÃO: Usando a coluna correta 'news_article_id'
        return [
            {"article_id": article.news_article_id, "text": article.article_text_content}
            for article in articles
        ]
    except Exception as e:
        settings.logger.error(f"Erro ao buscar artigos para análise: {e}", exc_info=True)
        return []

def update_article_with_analysis(article_id: int, analysis_dict: dict): # <-- MUDANÇA: Recebe um dicionário
    """
    Atualiza um artigo com o dicionário de análise e muda seu status.
    """
    with get_db_session() as session:
        try:
            article = session.query(NewsArticle).filter(NewsArticle.news_article_id == article_id).first()
            if article:
                # MUDANÇA: Salva o dicionário diretamente. SQLAlchemy/PostgreSQL cuidam da serialização.
                article.llm_analysis_json = analysis_dict 
                article.processing_status = 'analysis_complete'
                session.commit()
                settings.logger.info(f"Análise do artigo {article_id} salva com sucesso no banco de dados.")
            else:
                settings.logger.warning(f"Artigo com ID {article_id} não encontrado para salvar a análise.")
        except Exception as e:
            session.rollback()
            settings.logger.error(f"Erro ao salvar análise para o artigo {article_id}: {e}", exc_info=True)