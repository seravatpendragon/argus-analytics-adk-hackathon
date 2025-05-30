# src/database/db_utils.py
# -*- coding: utf-8 -*-

import sys
import os
from sqlalchemy import create_engine, select, func, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects import postgresql
from datetime import date, datetime, timezone
import pandas as pd # Adicionado para o caso de uso de get_latest_effective_date

from typing import List, Dict # Para type hints (opcional, mas boa prática)

# Importe seu logger de settings e o modelo EconomicIndicatorValue
from config import settings
from .create_db_tables import EconomicIndicatorValue
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

# --- Funções Get-Or-Create para Entidades ---
# (Mantendo as funções get_or_create_economic_sector, get_or_create_subsector, 
#  get_or_create_segment, get_or_create_company como na sua versão funcional do asset_loader.py)
# ... COLE AQUI AS SUAS FUNÇÕES get_or_create_economic_sector, get_or_create_subsector, 
# ... get_or_create_segment, get_or_create_company que estavam funcionando no asset_loader.py ...
# ... Certifique-se que elas usem session.commit() após um session.add() de um novo objeto ...

def get_or_create_news_source(session: Session, 
                              source_domain: str, 
                              source_api_name: str | None, 
                              credibility_score: float | None) -> NewsSource | None:
    """
    Busca ou cria uma NewsSource pelo source_domain (url_base).
    Retorna o objeto NewsSource.
    """
    if not source_domain:
        settings.logger.warning("get_or_create_news_source: source_domain não fornecido.")
        return None

    # Remove "www." do início do domínio para consistência, se presente
    normalized_domain = source_domain.lower()
    if normalized_domain.startswith("www."):
        normalized_domain = normalized_domain[4:]

    news_source = session.query(NewsSource).filter(NewsSource.url_base == normalized_domain).first()

    if news_source:
        settings.logger.debug(f"NewsSource encontrada para '{normalized_domain}': ID {news_source.news_source_id}")
        # Opcional: Lógica para atualizar o credibility_score se necessário
        # if credibility_score is not None and news_source.base_credibility_score != credibility_score:
        #     news_source.base_credibility_score = credibility_score
        #     try:
        #         session.commit()
        #         settings.logger.info(f"Score de credibilidade atualizado para NewsSource ID {news_source.news_source_id}")
        #     except Exception as e:
        #         session.rollback()
        #         settings.logger.error(f"Erro ao atualizar score de credibilidade para NewsSource ID {news_source.news_source_id}: {e}")
        return news_source
    else:
        display_name = source_api_name if source_api_name and source_api_name.strip() else normalized_domain
        settings.logger.info(f"NewsSource não encontrada para '{normalized_domain}'. Criando nova com nome '{display_name}'.")

        new_source = NewsSource(
            name=display_name[:255], # Garante que não exceda o limite do campo VARCHAR se houver
            url_base=normalized_domain,
            base_credibility_score=credibility_score
        )
        session.add(new_source)
        try:
            session.commit() # Commit para persistir e obter o ID
            settings.logger.info(f"Nova NewsSource ID {new_source.news_source_id} criada para '{normalized_domain}'.")
            return new_source
        except IntegrityError: # Tratamento de race condition ou erro inesperado
            session.rollback()
            settings.logger.error(f"Erro de integridade ao criar NewsSource para '{normalized_domain}'. Tentando buscar novamente.")
            # Tenta buscar novamente caso outra transação tenha criado
            return session.query(NewsSource).filter(NewsSource.url_base == normalized_domain).first()
        except Exception as e:
            session.rollback()
            settings.logger.error(f"Erro ao criar NewsSource para '{normalized_domain}': {e}")
            return None
        
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
        settings.logger.info(f"Não encontrado. Criando novo: Nome='{search_name}', Tipo='{search_type}', Freq='{frequency}', Unidade='{unit}'")
        new_indicator = EconomicIndicator(name=search_name, indicator_type=search_type, frequency=frequency, unit=unit, econ_data_source_id=econ_data_source_id)
        session.add(new_indicator)
        try:
            session.commit()
            settings.logger.info(f"Novo indicador criado ID: {new_indicator.indicator_id} para Nome='{search_name}'")
            return new_indicator.indicator_id
        except Exception as e:
            session.rollback()
            settings.logger.error(f"Erro ao CRIAR indicador '{search_name}': {e}. Tentando buscar...")
            indicator = session.query(EconomicIndicator).filter_by(name=search_name, indicator_type=search_type).first()
            if indicator:
                settings.logger.info(f"Encontrado ID {indicator.indicator_id} para '{search_name}' pós-rollback.")
                return indicator.indicator_id
            settings.logger.critical(f"FALHA CRÍTICA ao criar/obter '{search_name}'.")
            return None

def get_or_create_news_source(session: Session, 
                              source_domain: str, 
                              source_api_name: str | None, # Nome vindo da API (ex: "Terra.com.br")
                              loaded_credibility_data: dict, # Dicionário carregado do fontes_credibilidade.json
                              default_unverified_score: float = 0.6) -> NewsSource | None:
    if not source_domain:
        settings.logger.warning("get_or_create_news_source: source_domain não fornecido.")
        return None

    normalized_domain = source_domain.lower()
    if normalized_domain.startswith("www."):
        normalized_domain = normalized_domain[4:]

    news_source = session.query(NewsSource).filter(NewsSource.url_base == normalized_domain).first()

    if news_source:
        settings.logger.debug(f"NewsSource encontrada para '{normalized_domain}': ID {news_source.news_source_id}")
        # Opcional: Atualizar se dados no JSON mudaram e são mais recentes?
        # credibility_info_json = loaded_credibility_data.get(normalized_domain)
        # if credibility_info_json and credibility_info_json.get('assessment_date') > news_source.assessment_date_db_field:
        #    news_source.base_credibility_score = credibility_info_json.get("overall_credibility_score")
        #    news_source.name = credibility_info_json.get("source_name", news_source.name)
        #    session.commit()
        return news_source
    else:
        # Fonte não existe no BD, vamos criar
        credibility_info_json = loaded_credibility_data.get(normalized_domain)
        display_name = source_api_name if source_api_name and source_api_name.strip() else normalized_domain
        score_to_assign = default_unverified_score
        assessment_dt = datetime.now(timezone.utc).date() # Data de hoje para assessment_date

        if credibility_info_json:
            # Encontrado no JSON de credibilidade, então é "verificado"
            display_name = credibility_info_json.get("source_name", display_name)
            score_to_assign = credibility_info_json.get("overall_credibility_score", default_unverified_score)
            try:
                assessment_dt_str = credibility_info_json.get("assessment_date")
                if assessment_dt_str:
                    assessment_dt = datetime.strptime(assessment_dt_str, "%Y-%m-%d").date()
            except ValueError:
                settings.logger.warning(f"Data de avaliação inválida para '{normalized_domain}' no JSON. Usando data atual.")
            settings.logger.info(f"Fonte '{normalized_domain}' encontrada no JSON de credibilidade. Score: {score_to_assign}")
        else:
            # Não encontrado no JSON de credibilidade - é uma fonte nova/desconhecida
            settings.logger.warning(
                f"Fonte desconhecida '{normalized_domain}' (API name: '{source_api_name}'). "
                f"Atribuindo score base {default_unverified_score}. Por favor, revise e adicione ao fontes_credibilidade.json."
            )
            # Você pode logar `normalized_domain` em um arquivo/tabela separada para revisão aqui.
            # Ex: log_unknown_source_for_review(normalized_domain, source_api_name)

        new_source = NewsSource(
            name=display_name[:255],
            url_base=normalized_domain,
            base_credibility_score=score_to_assign
            # Considere adicionar 'assessment_date' à sua tabela NewsSource se quiser rastrear no BD
            # assessment_date_db_field = assessment_dt
        )
        session.add(new_source)
        try:
            session.commit()
            settings.logger.info(f"Nova NewsSource ID {new_source.news_source_id} criada para '{normalized_domain}' com score {score_to_assign}.")
            return new_source
        # ... (resto do tratamento de erro como antes) ...
        except IntegrityError: 
            session.rollback()
            settings.logger.error(f"Erro de integridade ao criar NewsSource para '{normalized_domain}'. Tentando buscar novamente.")
            return session.query(NewsSource).filter(NewsSource.url_base == normalized_domain).first()
        except Exception as e:
            session.rollback()
            settings.logger.error(f"Erro ao criar NewsSource para '{normalized_domain}': {e}")
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