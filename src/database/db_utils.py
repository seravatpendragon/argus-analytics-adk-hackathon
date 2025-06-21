# src/database/db_utils.py
# -*- coding: utf-8 -*-

import json
import re
import sys
import os
import traceback
from venv import logger
import numpy as np
from sqlalchemy import and_, bindparam, create_engine, or_, select, func, text, update
from sqlalchemy.orm import sessionmaker, Session, joinedload
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects import postgresql
from datetime import date, datetime, timedelta, timezone
import pandas as pd # Adicionado para o caso de uso de get_latest_effective_date

from typing import Any, List, Dict, Optional

import vertexai
from vertexai.language_models import TextEmbeddingModel


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

# Inicializa o modelo aqui ou de forma global para reutilização
try:
    vertexai.init(project=settings.PROJECT_ID, location=settings.LOCATION)
    embedding_model_for_db = TextEmbeddingModel.from_pretrained(settings.TEXT_EMBBEDING)

except Exception as e:
    settings.logger.warning(f"Não foi possível inicializar o modelo de embedding no db_utils: {e}")
    embedding_model_for_db = None

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
            Company.name,
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

def get_articles_pending_analysis(session: Session, limit: int = 100):
    """
    Busca artigos que precisam de análise LLM completa, incluindo dados da fonte.
    """
    now = datetime.now(settings.TIMEZONE)
    articles_data = (
        session.query(NewsArticle)
        .options(joinedload(NewsArticle.news_source)) 
        .filter(
            # CORRIGIDO: Agora buscando artigos com status 'pending_llm_analysis'
            NewsArticle.processing_status == 'pending_llm_analysis', 
            (NewsArticle.next_retry_at.is_(None)) | (NewsArticle.next_retry_at <= now)
        )
        .limit(limit)
        .all()
    )

    result_list = []
    for article in articles_data:
        source_credibility = article.news_source.base_credibility_score if article.news_source else 0.5
        news_source_url = article.news_source.url_base if article.news_source and article.news_source.url_base else article.article_link 
        news_source_name = article.news_source.name if article.news_source else "Desconhecida"

        result_list.append({
            "news_article_id": article.news_article_id,
            "headline": article.headline,
            "article_link": article.article_link,
            "publication_date": article.publication_date.isoformat() if article.publication_date else None,
            "article_text_content": article.article_text_content,
            "news_source_url": news_source_url,      
            "source_credibility": source_credibility, 
            "news_source_name": news_source_name      
        })
    return result_list

def update_article_with_analysis(article_id: int, analysis_results: dict):
    """
    Atualiza um artigo com os resultados da análise LLM e os scores de confiança.
    analysis_results deve conter:
    - 'llm_analysis_output': O JSON principal da análise do LLM.
    - 'conflict_analysis_output': O JSON de resultado do ConflictDetector.
    - 'source_credibility': O score de credibilidade da fonte.
    - 'overall_confidence_score': O score de confiança geral calculado.
    - 'processing_status': O status final do processamento (ex: 'analysis_complete', 'analysis_rejected', 'pending_llm_analysis', 'analysis_failed').
    """
    with get_db_session() as session:
        article = session.query(NewsArticle).filter(NewsArticle.news_article_id == article_id).first()
        if not article:
            settings.logger.error(f"Artigo com ID {article_id} não encontrado para atualização.")
            return

        try:
            # 1. Atualiza os JSONs e scores
            article.llm_analysis_json = analysis_results.get("llm_analysis_output")
            article.conflict_analysis_json = analysis_results.get("conflict_analysis_output")
            article.source_credibility = analysis_results.get("source_credibility")
            article.overall_confidence_score = analysis_results.get("overall_confidence_score")
            
            # 2. Determina o novo status de processamento e lógica de retentativa
            new_processing_status = analysis_results.get("processing_status", 'analysis_failed') # Default para falha
            
            # Lógica para artigos que são reenviados para 'pending_llm_analysis'
            if new_processing_status == 'pending_llm_analysis':
                article.retries_count = (article.retries_count or 0) + 1 # Incrementa
                # Cálculo de delay para retentativa exponencial
                delay = settings.BASE_RETRY_DELAY_SECONDS * (2 ** (article.retries_count - 1)) # -1 porque a primeira retentativa é a 2a tentativa
                article.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                settings.logger.info(f"Artigo {article_id} agendado para reanálise LLM. Tentativa: {article.retries_count}. Próxima em {delay}s.")
                
                # Se atingiu o máximo de retentativas para análise LLM, marca como falha final
                if article.retries_count >= settings.MAX_LLM_ANALYSIS_RETRIES:
                    new_processing_status = 'analysis_failed_max_retries' # Novo status de falha final
                    settings.logger.error(f"Artigo {article_id} atingiu o máximo de retentativas de reanálise LLM ({settings.MAX_LLM_ANALYSIS_RETRIES}).")
                    article.next_retry_at = None # Não agendar mais retentativas
            else:
                # Se o status é final ('analysis_complete', 'analysis_rejected', 'analysis_failed'), reseta contadores
                article.retries_count = 0
                article.next_retry_at = None

            article.processing_status = new_processing_status
            article.last_processed_at = datetime.now(settings.TIMEZONE)

            session.commit()
            settings.logger.info(f"Análise do artigo {article_id} salva com sucesso no banco de dados com status: {article.processing_status}.")
        except Exception as e:
            session.rollback()
            settings.logger.error(f"Erro ao salvar análise do artigo {article_id} no banco de dados: {e}", exc_info=True)

def get_analyses_for_topic(session: Session, topic: str, days_back: int = 7) -> list[dict]:
    """
    Busca análises completas (llm_analysis_json e conflict_analysis_json)
    para um tópico/empresa nos últimos dias.
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days_back)

    # Filtra por artigos completos e que contenham o tópico na manchete ou nas entidades
    # e cujo llm_analysis_json não seja nulo.
    query_results = (
        session.query(NewsArticle)
        .options(joinedload(NewsArticle.company_links)) # Para filtrar por empresa se necessário
        .filter(
                NewsArticle.processing_status == 'analysis_complete',
                NewsArticle.llm_analysis_json.isnot(None),
                NewsArticle.publication_date >= start_date,
                or_(
                    NewsArticle.headline.ilike(f'%{topic}%'), # Busca no título
                    # Busca por empresas relacionadas se 'topic' for um nome de empresa
                    # Supondo que 'Company' é importado e 'company_links' é um relacionamento
                    NewsArticle.company_links.any(Company.name.ilike(f'%{topic}%')),
                    # <<< AQUI ESTÁ A CORREÇÃO >>>
                    # Acessa 'foco_principal_sugerido' como TEXTO (->>)
                    NewsArticle.llm_analysis_json['analise_entidades'].op('->>')('foco_principal_sugerido').ilike(f'%{topic}%'),
                    # Acessa 'entidades_identificadas' como TEXTO (->>) e busca nele
                    # Isso converterá o array JSON em uma string '[{"tipo": ...}, {"tipo": ...}]'
                    # e fará a busca de substring nessa string.
                    NewsArticle.llm_analysis_json['analise_entidades'].op('->>')('entidades_identificadas').ilike(f'%{topic}%')
                )
            )
            .order_by(NewsArticle.publication_date.desc())
            .limit(100) 
            .all()
    )

    formatted_analyses = []
    for article in query_results:
        # Retorna o llm_analysis_json completo, o conflict_analysis_json,
        # e os scores de alto nível para o consolidador usar.
        formatted_analyses.append({
            "news_article_id": article.news_article_id,
            "headline": article.headline,
            "publication_date": article.publication_date.isoformat() if article.publication_date else None,
            "llm_analysis": article.llm_analysis_json, # O JSON completo da análise
            "conflict_analysis": article.conflict_analysis_json, # O JSON completo da auditoria
            "overall_confidence_score": article.overall_confidence_score,
            "source_credibility": article.source_credibility,
        })
    return formatted_analyses

def get_market_data_for_topic(session: Session, topic: str, days_back: int = 7, indicators: List[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Busca dados de mercado/macro para um tópico nos últimos dias.
    Esta é uma implementação de exemplo. Você precisará adaptá-la às suas tabelas reais.
    """
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days_back)
    
    # Dicionário para armazenar os dados por tipo de indicador
    all_market_data = {}

    # Exemplo (você precisará adaptar para suas tabelas FredData, BcbData, etc.)
    # Se você não tem tabelas separadas para isso, você precisaria criar ou
    # fazer essa busca de forma mais genérica, talvez baseada em 'tags' de notícias.

    # Exemplo para dados FRED (assumindo que você tem um modelo FredData e coluna 'topic_related')
    # if "FRED" in (indicators or ["FRED"]): # Ou se o tópico estiver em algum mapeamento Fred
    #     fred_data = session.query(FredData).filter(
    #         FredData.date >= start_date,
    #         FredData.topic_related == topic # Exemplo de como filtrar
    #     ).all()
    #     all_market_data['FRED_INDICATORS'] = [{"date": d.date.isoformat(), "value": d.value} for d in fred_data]
    
    # Para o hackathon, vamos simular buscando apenas Brent, pois é um bom indicador global
    # Assumindo que você tem uma tabela 'EiaBrentDaily' ou 'FredBrentDaily' com 'date' e 'value'
    try:
        from .create_db_tables import FredBrentDaily # Exemplo, ajuste o modelo real
        brent_data = session.query(FredBrentDaily).filter(
            FredBrentDaily.date >= start_date
        ).order_by(FredBrentDaily.date.desc()).limit(days_back).all() # Pega os últimos 'days_back' dias
        
        all_market_data['BRENT_OIL_DAILY'] = [{"date": d.date.isoformat(), "value": d.value} for d in brent_data]
        
    except ImportError:
        settings.logger.warning("Modelo FredBrentDaily não encontrado para buscar dados de Brent. Pule esta parte.")
    except Exception as e:
        settings.logger.error(f"Erro ao buscar dados de Brent: {e}")

    # Você expandiria isso para outras fontes (BCB, EIA, Fundamentus, etc.)
    # filtrando pelos IDs ou nomes de indicadores que o consolidador pode pedir.

    return all_market_data

def get_quantitative_data_for_topic(session: Session, topic_or_ticker: str, days_back: int = 7, specific_indicators: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Busca dados quantitativos (fundamentos da empresa, preços de commodities, indicadores macro)
    para um tópico/ticker nos últimos dias, considerando a frequência dos indicadores e nomes exatos.
    """
    end_date = datetime.now(timezone.utc).date() 
    start_date = end_date - timedelta(days=days_back)
    
    all_data = {
        "COMPANY_FUNDAMENTALS": {}, 
        "COMPANY_MARKET_DATA": {}, 
        "MACRO_COMMODITY_DATA": {}
    }

    # Contexto da empresa (ticker e nome)
    company_obj = session.query(Company).filter(
        or_(
            Company.ticker.ilike(topic_or_ticker), 
            Company.name.ilike(f'%{topic_or_ticker}%')
        )
    ).first()

    if company_obj: # company_obj não é None
        # <<< ADICIONAR ESTES LOGS PARA DEPURAR O company_obj >>>
        logger.info(f"DB_UTILS: Empresa encontrada: ID={company_obj.company_id}, Ticker={company_obj.ticker}")
        if hasattr(company_obj, 'name'):
            logger.info(f"DB_UTILS: company_obj TEM o atributo 'company_name'. Valor: {company_obj.name}")
        else:
            logger.error(f"DB_UTILS: company_obj NÃO TEM o atributo 'company_name'. Atributos disponíveis: {company_obj.__dict__.keys()}")
        
        # Esta linha ainda causará o erro se 'company_name' não estiver acessível,
        # mas os logs acima nos darão a informação antes do crash.
        all_data['COMPANY_FUNDAMENTALS_CONTEXT'] = {
            "company_name": company_obj.name, 
            "ticker": company_obj.ticker
        }

        # --- Buscar FUNDAMENTOS ESTÁTICOS ---
        fundamental_metrics_names = [
            "P/L", "P/VP", "EV/EBITDA", "Dividend Yield", "ROE", "ROIC", 
            "Margem líquida", "Margem bruta", "Margem EBIT",
            "Liquidez corrente", "Dívida bruta/Patrim", "Dívida líquida/EBITDA",
            "Ativo", "Ativo Circulante", "Dívida Bruta", "Dívida Líquida", 
            "Patrimônio Líquido", "Receita Líquida", "EBIT", "Lucro Líquido"
        ]
        
        # <<< ADICIONAR ESTE LOG >>>
        logger.info(f"DB_UTILS: Buscando metadados para FUNDAMENTOS da empresa '{company_obj.ticker}': {fundamental_metrics_names}")
        
        fundamental_indicators = session.query(EconomicIndicator).filter(
            EconomicIndicator.name.in_(fundamental_metrics_names),
            EconomicIndicator.indicator_type.like('Fundamental%') 
        ).all()
        
        for ind in fundamental_indicators:
            # Para fundamentos, pegamos o último valor disponível (não filtrado por data)
            latest_value = session.query(EconomicIndicatorValue).filter(
                EconomicIndicatorValue.indicator_id == ind.indicator_id,
                EconomicIndicatorValue.company_id == company_obj.company_id,
            ).order_by(EconomicIndicatorValue.effective_date.desc()).first()
            
            if latest_value and latest_value.value_numeric is not None:
                all_data['COMPANY_FUNDAMENTALS'][ind.name] = {
                    "value": latest_value.value_numeric,
                    "unit": ind.unit,
                    "date": latest_value.effective_date.isoformat()
                }
            else:
                logger.debug(f"Fundamento '{ind.name}' para {company_obj.ticker} não encontrado ou nulo.")


        # --- Buscar DADOS DE MERCADO DA EMPRESA (Preço Atual, Beta) ---
        company_market_metrics_names = [
            f"{company_obj.ticker} Preço Fechamento", 
            f"{company_obj.ticker} Beta",
            f"{company_obj.ticker} Preço Máximo", 
            f"{company_obj.ticker} Preço Mínimo",
            f"{company_obj.ticker} Preço Abertura",
            f"{company_obj.ticker} Volume",
            f"{company_obj.ticker} Valor de Mercado"
        ]
        
        # <<< ADICIONAR ESTE LOG >>>
        logger.info(f"DB_UTILS: Buscando metadados para MÉTRICAS DE MERCADO da empresa '{company_obj.ticker}': {company_market_metrics_names}")

        market_indicators_company_query = session.query(EconomicIndicator).filter(
            EconomicIndicator.name.in_(company_market_metrics_names)
        ).all()

        for ind in market_indicators_company_query:
            # Para preço atual e beta, queremos o ABSOLUTO mais recente até a end_date
            # Removemos o filtro 'effective_date >= start_date' para pegar o último disponível
            latest_value = session.query(EconomicIndicatorValue).filter(
                EconomicIndicatorValue.indicator_id == ind.indicator_id,
                EconomicIndicatorValue.company_id == company_obj.company_id,
                EconomicIndicatorValue.effective_date <= end_date # Pega o mais recente até hoje
            ).order_by(EconomicIndicatorValue.effective_date.desc()).first()
            
            if latest_value and latest_value.value_numeric is not None:
                # ... (o resto do código para popular all_data['COMPANY_MARKET_DATA'] permanece o mesmo) ...
                standard_name = ind.name.replace(f"{company_obj.ticker} ", "").replace("Preço Fechamento", "Current_Price").replace("Preço Máximo", "High_Price").replace("Preço Mínimo", "Low_Price").replace("Preço Abertura", "Open_Price").replace("Valor de Mercado", "Market_Cap").replace("Volume", "Volume")
                all_data['COMPANY_MARKET_DATA'][standard_name] = {
                    "value": latest_value.value_numeric,
                    "unit": ind.unit,
                    "date": latest_value.effective_date.isoformat()
                }
            else:
                logger.debug(f"Métrica de mercado '{ind.name}' para {company_obj.ticker} não encontrada ou nula. Company ID: {company_obj.company_id}.")


    # 2. Buscar dados de indicadores macroeconômicos e de commodities
    # Usar os nomes exatos do seu output (ex: "Ibovespa (^BVSP) Fechamento")
    macro_commodity_indicator_names_to_fetch = specific_indicators or [
        "EIA Preço Petróleo Brent Spot (Diário)",
        "FRED US 10-Year Treasury Constant Maturity Rate (Daily)", 
        "Ibovespa (^BVSP) Fechamento", 
        "FRED CBOE Crude Oil ETF Volatility Index (OVX)", 
        "BCB Selic Meta Definida Copom", 
        "BCB IPCA Variação Mensal", 
        "PIM-PF - Indústria Geral (Tabela 8888)", 
        "PNAD Contínua - Taxa de Desocupação (Tabela 6381)", 
        "PMC - Receita Nominal Varejo (Tabela 8880)", 
        "IPP - Indústria Geral (SIDRA 6903)", 
        "FRED WTI Crude Oil Spot Price (Diário)", 
        "FRED Trade Weighted US Dollar Index: Broad, Goods and Services (Daily)", 
        "BCB Câmbio USD PTAX", 
        "BCB IBC-Br dessazonalizado (Índice)", 
        "BCB Inadimplência PF (Rec. Livres)", 
        "BCB Inadimplência PJ (Rec. Livres)", 
        "BCB Saldo Total Crédito PF", 
        "BCB Saldo Total Crédito PJ", 
        "BCB Dívida Líquida Setor Público (% PIB)", 
        "BCB Dívida Bruta Governo Geral (% PIB)", 
        "BCB Resultado Nominal Setor Público (% PIB)", 
        "BCB Juros Nominais Setor Público (Acum. 12m)", 
        "BCB PIB Nominal (Acumulado 12 meses)", 
    ]
    
    # <<< ADICIONAR ESTE LOG >>>
    logger.info(f"DB_UTILS: Buscando metadados para indicadores macro/commodities: {macro_commodity_indicator_names_to_fetch}")
    
    indicator_metadata_map = {ind.name: ind for ind in session.query(EconomicIndicator).filter(EconomicIndicator.name.in_(macro_commodity_indicator_names_to_fetch)).all()}

    for indicator_name in macro_commodity_indicator_names_to_fetch:
        indicator_obj = indicator_metadata_map.get(indicator_name)
        if not indicator_obj:
            logger.warning(f"Metadados para o indicador '{indicator_name}' não encontrados em EconomicIndicators. Pulando.")
            continue

        query = session.query(EconomicIndicatorValue).filter(
            EconomicIndicatorValue.indicator_id == indicator_obj.indicator_id,
            EconomicIndicatorValue.effective_date <= end_date, # Sempre pega até a data final
            EconomicIndicatorValue.company_id.is_(None), # Dados gerais
            EconomicIndicatorValue.segment_id.is_(None)  # Dados gerais
        ).order_by(EconomicIndicatorValue.effective_date.desc())

        latest_value_in_period = None

        if indicator_obj.frequency in ['D', 'W']: # Diário ou Semanal: prioriza no período
            value_in_period = query.filter(EconomicIndicatorValue.effective_date >= start_date).first()
            if value_in_period:
                latest_value_in_period = value_in_period
            else:
                latest_value_in_period = query.first() # Pega o mais recente absoluto se não houver no período
                if latest_value_in_period:
                    logger.info(f"Indicador '{indicator_name}': Não encontrado no período de {days_back} dias. Usando valor mais recente de {latest_value_in_period.effective_date.isoformat()}.")
        else: # Mensal, Trimestral, Anual: pega o último valor absoluto até a end_date
            latest_value_in_period = query.first()
            
        if latest_value_in_period and latest_value_in_period.value_numeric is not None:
            all_data['MACRO_COMMODITY_DATA'][indicator_name] = {
                "value": latest_value_in_period.value_numeric,
                "unit": indicator_obj.unit,
                "date": latest_value_in_period.effective_date.isoformat(),
                "frequency": indicator_obj.frequency 
            }
        else:
            logger.debug(f"Indicador macro/commodity '{indicator_name}' não encontrado ou nulo no período.")
    
    return all_data


def update_article_embedding(article_id: int, text: str):
    """
    Gera e salva o embedding de um texto de artigo na linha correspondente do banco de dados.
    """
    if not embedding_model_for_db:
        settings.logger.error("Modelo de embedding não inicializado. Pulando salvamento de embedding.")
        return

    with get_db_session() as session:
        try:
            article = session.query(NewsArticle).filter(NewsArticle.news_article_id == article_id).first()
            if article:
                # Gera o embedding a partir do texto original
                embedding = embedding_model_for_db.get_embeddings([text])[0].values
                article.embedding = embedding # Salva na coluna 'embedding'
                session.commit()
                settings.logger.info(f"Embedding salvo com sucesso para o artigo {article_id}.")
            else:
                settings.logger.warning(f"Artigo {article_id} não encontrado para salvar embedding.")
        except Exception as e:
            session.rollback()
            settings.logger.error(f"Erro ao salvar embedding para o artigo {article_id}: {e}", exc_info=True)


def find_similar_article(embedding: list[float], threshold: float) -> dict:
    """Busca artigos similares usando pgvector e cosine similarity"""
    from sqlalchemy import text
    import numpy as np
    
    # Converter para array numpy e depois para string formatada
    embedding_array = np.array(embedding, dtype=np.float32)
    embedding_str = "[" + ",".join(str(x) for x in embedding_array) + "]"
    
    max_distance = 1 - threshold
    
    with get_db_session() as session:
        query = text("""
            SELECT news_article_id, llm_analysis_json 
            FROM "NewsArticles"
            WHERE (embedding <=> CAST(:embedding AS vector)) < :max_distance
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT 1
        """)
        
        result = session.execute(
            query,
            {"embedding": embedding_str, "max_distance": max_distance}
        ).fetchone()
        
        if result:
            return {
                "id": result[0],
                "analysis": result[1]
            }
        return None


def batch_update_precomputed_embeddings(embeddings_batch: list[tuple[int, list[float]]]):
    """Atualiza embeddings em lote quando já calculados"""
    from sqlalchemy import text, bindparam
    
    if not embeddings_batch:
        return

    settings.logger.info(f"Salvando {len(embeddings_batch)} embeddings pré-calculados...")
    
    with get_db_session() as session:
        try:
            # Usar bindparam para tratamento seguro de tipos
            update_query = text("""
                UPDATE "NewsArticles"
                SET embedding = CAST(:embedding AS vector)
                WHERE news_article_id = :article_id
            """)
            
            params = []
            for article_id, embedding in embeddings_batch:
                # Converter embedding para string formatada 
                embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                params.append({
                    "article_id": article_id,
                    "embedding": embedding_str
                })
            
            session.execute(
                update_query,
                params
            )
            session.commit()
            settings.logger.info("Embeddings pré-calculados salvos com sucesso!")
            
        except Exception as e:
            session.rollback()
            settings.logger.error(f"Erro ao salvar embeddings pré-calculados: {e}")
            raise

def get_all_analyzed_articles(session: Session, limit: int = 5000) -> list[dict]:
    """
    Busca artigos analisados, incluindo o base_credibility_score da fonte relacionada.
    """
    settings.logger.info(f"Buscando até {limit} artigos com status 'analysis_complete'...")
    try:
        query = (
            session.query(NewsArticle)
            .options(joinedload(NewsArticle.news_source))
            .filter(
                NewsArticle.processing_status == 'analysis_complete',
                NewsArticle.llm_analysis_json.isnot(None)
            )
            .order_by(NewsArticle.publication_date.desc())
            .limit(limit)
        )
        analyzed_articles = query.all()
        
        settings.logger.info(f"Encontrados {len(analyzed_articles)} artigos analisados.")
        
        results = []
        for article in analyzed_articles:
            # Pega o score de credibilidade diretamente da coluna. Se não existir, default é 0.5.
            base_credibility = article.news_source.base_credibility_score if article.news_source else 0.5

            results.append({
                "news_article_id": article.news_article_id,
                "title": article.headline,
                "url": article.article_link,
                "published_at": article.publication_date,
                "llm_analysis": article.llm_analysis_json,
                # Passa o valor numérico diretamente para o handler
                "source_base_credibility": base_credibility
            })
        return results

    except Exception as e:
        settings.logger.error(f"Erro ao buscar artigos analisados: {e}")
        settings.logger.error(traceback.format_exc())
        return []
