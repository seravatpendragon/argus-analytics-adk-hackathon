# src/database/asset_loader.py
# -*- coding: utf-8 -*-

import pandas as pd
import os
import sys

# Adiciona o diretório raiz do projeto ao sys.path
project_root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root_path not in sys.path:
    sys.path.append(project_root_path)

try:
    from config import settings
    from src.database.db_utils import get_db_session # Usaremos a sessão do db_utils
    from src.database.create_db_tables import (
        EconomicSector, Subsector, Segment, Company,
        AnalyticalTheory, TheoryFrameworkDimension, CompanyMaslowProfile
    )
    from sqlalchemy.dialects.postgresql import insert as pg_insert
except ImportError as e:
    settings.logger.error(f"Erro em asset_loader.py ao importar: {e}")
    sys.exit(1)

# --- Funções Auxiliares Get-Or-Create (poderiam estar em db_utils.py) ---
def get_or_create_economic_sector(session, sector_name):
    instance = session.query(EconomicSector).filter_by(name=sector_name).first()
    if not instance:
        instance = EconomicSector(name=sector_name)
        session.add(instance)
        try:
            session.commit()
            settings.logger.info(f"Setor Econômico '{sector_name}' criado com ID: {instance.economic_sector_id}")
        except Exception as e:
            session.rollback()
            settings.logger.error(f"Erro ao criar Setor Econômico '{sector_name}': {e}. Tentando buscar novamente.")
            instance = session.query(EconomicSector).filter_by(name=sector_name).first()
            if not instance: raise
    return instance

def get_or_create_subsector(session, subsector_name, economic_sector_id):
    instance = session.query(Subsector).filter_by(name=subsector_name, economic_sector_id=economic_sector_id).first()
    if not instance:
        instance = Subsector(name=subsector_name, economic_sector_id=economic_sector_id)
        session.add(instance)
        try:
            session.commit()
            settings.logger.info(f"Subsetor '{subsector_name}' criado com ID: {instance.subsector_id}")
        except Exception as e:
            session.rollback()
            settings.logger.error(f"Erro ao criar Subsetor '{subsector_name}': {e}. Tentando buscar novamente.")
            instance = session.query(Subsector).filter_by(name=subsector_name, economic_sector_id=economic_sector_id).first()
            if not instance: raise
    return instance

def get_or_create_segment(session, segment_name, subsector_id):
    instance = session.query(Segment).filter_by(name=segment_name, subsector_id=subsector_id).first()
    if not instance:
        instance = Segment(name=segment_name, subsector_id=subsector_id)
        session.add(instance)
        try:
            session.commit()
            settings.logger.info(f"Segmento '{segment_name}' criado com ID: {instance.segment_id}")
        except Exception as e:
            session.rollback()
            settings.logger.error(f"Erro ao criar Segmento '{segment_name}': {e}. Tentando buscar novamente.")
            instance = session.query(Segment).filter_by(name=segment_name, subsector_id=subsector_id).first()
            if not instance: raise
    return instance

def get_or_create_company(session, ticker, company_name, segment_id, control_type, other_details=None):
    instance = session.query(Company).filter_by(ticker=ticker).first()
    if not instance:
        instance = Company(
            name=company_name,
            ticker=ticker,
            segment_id=segment_id,
            control_type=control_type,
            other_details_json=other_details
        )
        session.add(instance)
        try:
            session.commit()
            settings.logger.info(f"Empresa '{company_name}' ({ticker}) criada com ID: {instance.company_id}")
        except Exception as e:
            session.rollback()
            settings.logger.error(f"Erro ao criar Empresa '{company_name}' ({ticker}): {e}. Tentando buscar novamente.")
            instance = session.query(Company).filter_by(ticker=ticker).first()
            if not instance: raise
    else:
        # Atualizar se necessário
        updated = False
        if instance.name != company_name: instance.name = company_name; updated = True
        if instance.segment_id != segment_id: instance.segment_id = segment_id; updated = True
        if instance.control_type != control_type: instance.control_type = control_type; updated = True
        if other_details and instance.other_details_json != other_details: instance.other_details_json = other_details; updated = True
        
        if updated:
            try:
                session.commit()
                settings.logger.info(f"Detalhes da empresa '{company_name}' ({ticker}) atualizados.")
            except Exception as e:
                session.rollback()
                settings.logger.error(f"Erro ao atualizar Empresa '{company_name}' ({ticker}): {e}.")
                # Recarregar a instância para ter o estado do BD
                session.expire(instance) 
                instance = session.query(Company).filter_by(ticker=ticker).first()


    return instance

def populate_company_maslow_profile(session, company_id, maslow_weights_map_from_csv, maslow_dimension_ids_map, justification_geral=None):
    """
    Popula CompanyMaslowProfile para uma empresa.
    maslow_weights_map_from_csv: {'Fisiológicas': 0.9, 'Segurança': 0.8, ...}
    maslow_dimension_ids_map: {'Fisiológicas': id1, 'Segurança': id2, ...}
    """
    
    data_to_upsert = []
    for maslow_level_name, weight in maslow_weights_map_from_csv.items():
        dimension_id = maslow_dimension_ids_map.get(maslow_level_name)
        if dimension_id is None:
            settings.logger.warning(f"Nível Maslow '{maslow_level_name}' não encontrado em maslow_dimension_ids_map para empresa ID {company_id}. Pulando.")
            continue
        if weight is None or pd.isna(weight): # Lida com valores vazios no CSV para pesos
            settings.logger.info(f"Peso Maslow para '{maslow_level_name}' não fornecido para empresa ID {company_id}. Pulando este nível.")
            continue

        data_to_upsert.append({
            "company_id": company_id,
            "maslow_dimension_id": dimension_id,
            "weight": float(weight),
            "justification": justification_geral # Pode ser mais específico se o CSV tiver justificativas por nível
        })

    if not data_to_upsert:
        settings.logger.info(f"Nenhum dado de perfil Maslow para inserir/atualizar para empresa ID {company_id}.")
        return

    # Lógica de UPSERT para CompanyMaslowProfile
    # A PK é (company_id, maslow_dimension_id)
    table = CompanyMaslowProfile.__table__
    stmt = pg_insert(table).values(data_to_upsert)
    
    # Colunas a serem atualizadas em caso de conflito (na PK)
    update_columns = {
        "weight": stmt.excluded.weight,
        "justification": stmt.excluded.justification
    }

    stmt = stmt.on_conflict_do_update(
        index_elements=['company_id', 'maslow_dimension_id'], # Os componentes da PK
        set_=update_columns
    )

    try:
        session.execute(stmt)
        session.commit()
        settings.logger.info(f"Perfil Maslow para empresa ID {company_id} processado ({len(data_to_upsert)} níveis).")
    except Exception as e:
        session.rollback()
        settings.logger.error(f"Erro durante o upsert em CompanyMaslowProfile para empresa ID {company_id}: {e}")
        # Não levanta exceção aqui para permitir que o loop continue para outras empresas,
        # mas o erro será logado. Dependendo da criticidade, você pode querer levantar.

# --- Função Principal de Carga ---
def load_assets_from_csv(csv_filepath):
    if not os.path.exists(csv_filepath):
        settings.logger.error(f"Arquivo CSV de ativos não encontrado: {csv_filepath}")
        return

    df_assets = pd.read_csv(csv_filepath)
    session = get_db_session()

    # Buscar os IDs das dimensões de Maslow uma vez
    maslow_theory = session.query(AnalyticalTheory).filter_by(theory_name="Hierarquia de Maslow").first()
    if not maslow_theory:
        settings.logger.error("Teoria 'Hierarquia de Maslow' não encontrada no banco de dados. Execute seed_metadata.py primeiro.")
        session.close()
        return
    
    maslow_dimensions_db = session.query(TheoryFrameworkDimension.dimension_id, TheoryFrameworkDimension.dimension_name)\
                                .filter_by(theory_id=maslow_theory.theory_id).all()
    
    maslow_dimension_ids_map = {name: id for id, name in maslow_dimensions_db}
    
    # Mapeamento dos nomes das colunas do CSV para os nomes padrão dos níveis de Maslow
    # Isso torna o script mais robusto a pequenas variações nos nomes das colunas do CSV
    # E garante que usemos os nomes corretos ao buscar no maslow_dimension_ids_map
    csv_maslow_column_map = {
        "MaslowFisiologicasPeso": "Fisiológicas",
        "MaslowSegurancaPeso": "Segurança",
        "MaslowSociaisPeso": "Sociais",
        "MaslowEstimaPeso": "Estima",
        "MaslowAutorrealizacaoPeso": "Autorrealização"
    }


    try:
        for index, row in df_assets.iterrows():
            settings.logger.info(f"Processando linha {index+1} do CSV: Ticker {row['Ticker']}")
            sector_obj = get_or_create_economic_sector(session, row["Setor Economico B3"])
            subsector_obj = get_or_create_subsector(session, row["Subsetor B3"], sector_obj.economic_sector_id)
            segment_obj = get_or_create_segment(session, row["Segmento B3"], subsector_obj.subsector_id)
            
            company_obj = get_or_create_company(
                session,
                ticker=row["Ticker"],
                company_name=row["Empresa"],
                segment_id=segment_obj.segment_id,
                control_type=row["Tipo de Controle"]
            )

            # Popular CompanyMaslowProfile
            maslow_weights_from_csv = {}
            for csv_col_name, maslow_level_name in csv_maslow_column_map.items():
                if csv_col_name in row:
                    maslow_weights_from_csv[maslow_level_name] = row[csv_col_name]
                else:
                    settings.logger.warning(f"Coluna Maslow '{csv_col_name}' não encontrada no CSV para o ticker {row['Ticker']}. Nível '{maslow_level_name}' não será populado.")
            
            justificativa_geral = row.get("MaslowJustificativaGeral") # Pega a justificativa se existir

            if company_obj and maslow_weights_from_csv:
                populate_company_maslow_profile(
                    session, 
                    company_obj.company_id, 
                    maslow_weights_from_csv, 
                    maslow_dimension_ids_map,
                    justificativa_geral
                )
        
        settings.logger.info(f"Carga de ativos do MVP a partir de '{os.path.basename(csv_filepath)}' concluída.")

    except Exception as e:
        session.rollback() # Garante rollback em caso de erro no loop
        settings.logger.error(f"Erro geral durante a carga de ativos do CSV: {e}", exc_info=True)
    finally:
        session.close()

if __name__ == "__main__":
    # Define o caminho para o CSV de ativos a partir do settings.py
    ativos_csv_path = settings.ATIVOS_MVP_CSV_PATH
    
    # Exemplo de como criar um CSV de teste se ele não existir
    # No seu ambiente real, você criará este CSV manualmente com os dados corretos.
    if not os.path.exists(ativos_csv_path):
        settings.logger.warning(f"Arquivo {ativos_csv_path} não encontrado. Criando um exemplo com PETR4.")
        os.makedirs(os.path.dirname(ativos_csv_path), exist_ok=True) # Garante que o diretório exista
        example_data = [{
            "Ticker": "PETR4", "Empresa": "Petróleo Brasileiro S.A. - Petrobras",
            "Setor Economico B3": "Petróleo, Gás e Biocombustíveis",
            "Subsetor B3": "Petróleo, Gás e Biocombustíveis",
            "Segmento B3": "Exploração, Refino e Distribuição",
            "Tipo de Controle": "Capital Misto - Controle Estatal Federal",
            "MaslowFisiologicasPeso": 0.9, "MaslowSegurancaPeso": 0.8,
            "MaslowSociaisPeso": 0.2, "MaslowEstimaPeso": 0.3,
            "MaslowAutorrealizacaoPeso": 0.4,
            "MaslowJustificativaGeral": "Foco em energia e segurança energética."
        }]
        pd.DataFrame(example_data).to_csv(ativos_csv_path, index=False)
        settings.logger.info(f"Arquivo de exemplo {ativos_csv_path} criado. Edite-o com seus ativos e perfis Maslow.")
    
    load_assets_from_csv(ativos_csv_path)