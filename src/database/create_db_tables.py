import sys
import os
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, ForeignKey, UniqueConstraint, DateTime, Date, Boolean, Enum as SQLAlchemyEnum, text # Adicione 'text' aqui
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import JSONB 
from sqlalchemy.types import JSON 
from pgvector.sqlalchemy import Vector

# Adiciona o diretório raiz do projeto ao sys.path
# Isso permite que o script encontre o módulo config.settings
# Ajuste a quantidade de '..' conforme a profundidade do seu script em relação à raiz
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(project_root)

try:
    from config import settings
except ImportError:
    print("Erro: Não foi possível importar 'settings' do módulo 'config'.")
    print(f"Verifique se o caminho do projeto ({project_root}) está correto e se config/settings.py existe.")
    sys.exit(1)

Base = declarative_base()

# --- I. Tabelas Centrais (Core Data) ---

class EconomicSector(Base):
    __tablename__ = "EconomicSectors"
    economic_sector_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    subsectors = relationship("Subsector", back_populates="economic_sector")

class Subsector(Base):
    __tablename__ = "Subsectors"
    subsector_id = Column(Integer, primary_key=True, autoincrement=True)
    economic_sector_id = Column(Integer, ForeignKey("EconomicSectors.economic_sector_id"), nullable=False)
    name = Column(String, nullable=False)
    economic_sector = relationship("EconomicSector", back_populates="subsectors")
    segments = relationship("Segment", back_populates="subsector")
    __table_args__ = (UniqueConstraint("economic_sector_id", "name", name="uq_subsector_economic_sector_name"),)

class Segment(Base):
    __tablename__ = "Segments"
    segment_id = Column(Integer, primary_key=True, autoincrement=True)
    subsector_id = Column(Integer, ForeignKey("Subsectors.subsector_id"), nullable=False)
    name = Column(String, nullable=False)
    subsector = relationship("Subsector", back_populates="segments")
    companies = relationship("Company", back_populates="segment")
    news_links = relationship("NewsArticleSegmentLink", back_populates="segment")
    # Para Maslow
    maslow_profiles = relationship("SegmentMaslowProfile", back_populates="segment")
    economic_indicator_values = relationship("EconomicIndicatorValue", back_populates="segment")
    behavioral_simulations = relationship("BehavioralSimulation", back_populates="target_segment")
    __table_args__ = (UniqueConstraint("subsector_id", "name", name="uq_segment_subsector_name"),)

class Company(Base):
    __tablename__ = "Companies"
    company_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    ticker = Column(String, unique=True, nullable=False)
    cvm_code = Column(String(50), unique=True, nullable=True)
    segment_id = Column(Integer, ForeignKey("Segments.segment_id"), nullable=False)
    control_type = Column(String, nullable=True)
    other_details_json = Column(JSON, nullable=True) # Usar JSONB se for PostgreSQL
    segment = relationship("Segment", back_populates="companies")
    news_links = relationship("NewsArticleCompanyLink", back_populates="company")
    economic_indicator_values = relationship("EconomicIndicatorValue", back_populates="company")
    # Para Maslow
    maslow_profile = relationship("CompanyMaslowProfile", back_populates="company")
    # Para Teorias Genéricas
    theory_analyses = relationship("CompanyAnalysisData", back_populates="company")
    behavioral_simulations = relationship("BehavioralSimulation", back_populates="target_company")
    network_analyses_as_focus = relationship("NetworkAnalysisComputation", foreign_keys="[NetworkAnalysisComputation.focus_company_id]", back_populates="focus_company_obj")
    network_entity_link = relationship("NetworkEntity", foreign_keys="[NetworkEntity.company_id]", back_populates="company_obj", uselist=False)


class NewsSource(Base):
    __tablename__ = "NewsSources"
    news_source_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    base_credibility_score = Column(Float, nullable=True) 
    craap_analysis_json = Column(JSON, nullable=True)
    url_base = Column(String, nullable=True)
    craap_status = Column(String(50), nullable=False, default='pending_craap_analysis')
    articles = relationship("NewsArticle", back_populates="news_source")

class NewsArticle(Base):
    __tablename__ = "NewsArticles"
    news_article_id = Column(Integer, primary_key=True, autoincrement=True)
    headline = Column(Text, nullable=False)
    article_link = Column(String, unique=True, nullable=False)
    publication_date = Column(DateTime(timezone=True), nullable=True)
    collection_date = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    news_source_id = Column(Integer, ForeignKey("NewsSources.news_source_id"), nullable=False)
    article_text_content = Column(Text, nullable=True) 
    article_type = Column(String, nullable=True) 
    llm_analysis_json = Column(JSON, nullable=True) # Agora reservado para os resultados da análise do LLM
    embedding = Column(Vector(768), nullable=True) 
    # NOVAS COLUNAS ADICIONADAS:
    summary = Column(Text, nullable=True)
    processing_status = Column(String(50), nullable=True, default='pending_full_text_fetch')
    last_processed_at = Column(DateTime(timezone=True), nullable=True)
    source_feed_name = Column(String(255), nullable=True)
    source_feed_url = Column(Text, nullable=True)
    original_url = Column(Text, nullable=True) # Para armazenar a URL original (ex: do Google)
    is_redirected = Column(Boolean, default=False) # Para sabermos se o link foi resolvido
    # NOVOS CAMPOS PARA O MECANISMO DE RETENTATIVA:
    retries_count = Column(Integer, default=0, nullable=False) # Contagem de tentativas
    next_retry_at = Column(DateTime(timezone=True), nullable=True) # Próxima data de retentativa
    news_source = relationship("NewsSource", back_populates="articles")
    company_links = relationship("NewsArticleCompanyLink", back_populates="news_article")
    segment_links = relationship("NewsArticleSegmentLink", back_populates="news_article")

class NewsArticleCompanyLink(Base):
    __tablename__ = "NewsArticleCompanyLink"
    news_article_id = Column(Integer, ForeignKey("NewsArticles.news_article_id"), primary_key=True)
    company_id = Column(Integer, ForeignKey("Companies.company_id"), primary_key=True)
    news_article = relationship("NewsArticle", back_populates="company_links")
    company = relationship("Company", back_populates="news_links")

class NewsArticleSegmentLink(Base):
    __tablename__ = "NewsArticleSegmentLink"
    news_article_id = Column(Integer, ForeignKey("NewsArticles.news_article_id"), primary_key=True)
    segment_id = Column(Integer, ForeignKey("Segments.segment_id"), primary_key=True)
    news_article = relationship("NewsArticle", back_populates="segment_links")
    segment = relationship("Segment", back_populates="news_links")

class EconomicDataSource(Base):
    __tablename__ = "EconomicDataSources"
    econ_data_source_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    api_endpoint = Column(String, nullable=True)
    indicators = relationship("EconomicIndicator", back_populates="economic_data_source")

class EconomicIndicator(Base):
    __tablename__ = "EconomicIndicators"
    indicator_id = Column(Integer, primary_key=True, autoincrement=True)
    econ_data_source_id = Column(Integer, ForeignKey("EconomicDataSources.econ_data_source_id"), nullable=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    indicator_type = Column(String, nullable=True)
    frequency = Column(String, nullable=True)
    unit = Column(String, nullable=True)
    economic_data_source = relationship("EconomicDataSource", back_populates="indicators")
    values = relationship("EconomicIndicatorValue", back_populates="indicator")
    __table_args__ = (UniqueConstraint("name", "indicator_type", name="uq_economicindicator_name_type"),)

class EconomicIndicatorValue(Base):
    __tablename__ = "EconomicIndicatorValues"
    value_id = Column(Integer, primary_key=True, autoincrement=True)
    indicator_id = Column(Integer, ForeignKey("EconomicIndicators.indicator_id"), nullable=False)
    company_id = Column(Integer, ForeignKey("Companies.company_id"), nullable=True, default=None)
    segment_id = Column(Integer, ForeignKey("Segments.segment_id"), nullable=True, default=None)
    effective_date = Column(Date, nullable=False)
    value_numeric = Column(Float, nullable=True)
    value_text = Column(Text, nullable=True)
    collection_timestamp = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    indicator = relationship("EconomicIndicator", back_populates="values")
    company = relationship("Company", back_populates="economic_indicator_values")
    segment = relationship("Segment", back_populates="economic_indicator_values")
    __table_args__ = (
        UniqueConstraint("indicator_id", "effective_date", "company_id", "segment_id", name="uq_economicindicatorvalue_indicator_date_company_segment"),
    )

# --- II. Framework de Teorias Analíticas (Modular) ---

class AnalyticalTheory(Base):
    __tablename__ = "AnalyticalTheories"
    theory_id = Column(Integer, primary_key=True, autoincrement=True)
    theory_name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    dimensions = relationship("TheoryFrameworkDimension", back_populates="theory")

class TheoryFrameworkDimension(Base):
    __tablename__ = "TheoryFrameworkDimensions"
    dimension_id = Column(Integer, primary_key=True, autoincrement=True)
    theory_id = Column(Integer, ForeignKey("AnalyticalTheories.theory_id"), nullable=False)
    dimension_name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    expected_data_schema_json = Column(JSON, nullable=True) # Usar JSONB se for PostgreSQL
    theory = relationship("AnalyticalTheory", back_populates="dimensions")
    # Relações para tabelas específicas de teorias
    segment_maslow_profiles = relationship("SegmentMaslowProfile", back_populates="maslow_dimension")
    company_maslow_profiles = relationship("CompanyMaslowProfile", back_populates="maslow_dimension")
    company_analyses = relationship("CompanyAnalysisData", back_populates="dimension")
    behavioral_simulations = relationship("BehavioralSimulation", back_populates="simulation_model_dimension")
    __table_args__ = (UniqueConstraint("theory_id", "dimension_name", name="uq_theoryframeworkdimension_theory_name"),)

class CompanyAnalysisData(Base):
    __tablename__ = "CompanyAnalysisData"
    company_analysis_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("Companies.company_id"), nullable=False)
    dimension_id = Column(Integer, ForeignKey("TheoryFrameworkDimensions.dimension_id"), nullable=False)
    analysis_date = Column(Date, nullable=False)
    assessment_data_json = Column(JSON, nullable=True) # Usar JSONB se for PostgreSQL
    source_references_json = Column(JSON, nullable=True) # Usar JSONB se for PostgreSQL
    analyst_notes = Column(Text, nullable=True)
    company = relationship("Company", back_populates="theory_analyses")
    dimension = relationship("TheoryFrameworkDimension", back_populates="company_analyses")
    __table_args__ = (UniqueConstraint("company_id", "dimension_id", "analysis_date", name="uq_companyanalysisdata_company_dimension_date"),)

# --- III. Tabelas Específicas para Módulos Teóricos (Foco Fase 0: Maslow) ---

class SegmentMaslowProfile(Base):
    __tablename__ = "SegmentMaslowProfile"
    segment_id = Column(Integer, ForeignKey("Segments.segment_id"), primary_key=True)
    maslow_dimension_id = Column(Integer, ForeignKey("TheoryFrameworkDimensions.dimension_id"), primary_key=True) # FK para a dimensão Maslow
    weight = Column(Float, nullable=False) # CHECK constraint pode ser adicionada a nível de BD
    justification = Column(Text, nullable=True)
    segment = relationship("Segment", back_populates="maslow_profiles")
    maslow_dimension = relationship("TheoryFrameworkDimension", back_populates="segment_maslow_profiles")

class CompanyMaslowProfile(Base): # Nome sugerido
    __tablename__ = "CompanyMaslowProfile"
    company_id = Column(Integer, ForeignKey("Companies.company_id"), primary_key=True)
    maslow_dimension_id = Column(Integer, ForeignKey("TheoryFrameworkDimensions.dimension_id"), primary_key=True) # FK para o nível de Maslow
    weight = Column(Float, nullable=False) # Armazena o peso/nota de 0.0 a 1.0
    justification = Column(Text, nullable=True) # Justificativa para o peso, se necessário
    company = relationship("Company", back_populates="maslow_profile") # Ajustar em Company
    maslow_dimension = relationship("TheoryFrameworkDimension", back_populates="company_maslow_profiles") # Ajustar em TheoryFrameworkDimension

# --- Tabelas para Fases Futuras (Estrutura Básica) ---

class BehavioralSimulation(Base):
    __tablename__ = "BehavioralSimulations"
    simulation_id = Column(Integer, primary_key=True, autoincrement=True)
    simulation_run_datetime = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    simulation_model_dimension_id = Column(Integer, ForeignKey("TheoryFrameworkDimensions.dimension_id"), nullable=False)
    target_company_id = Column(Integer, ForeignKey("Companies.company_id"), nullable=True)
    target_segment_id = Column(Integer, ForeignKey("Segments.segment_id"), nullable=True)
    market_context_description = Column(Text, nullable=True)
    simulation_name = Column(String, nullable=True)
    input_parameters_json = Column(JSON, nullable=True) # Usar JSONB se for PostgreSQL
    simulation_results_json = Column(JSON, nullable=True) # Usar JSONB se for PostgreSQL
    analyst_notes = Column(Text, nullable=True)
    simulation_model_dimension = relationship("TheoryFrameworkDimension", back_populates="behavioral_simulations")
    target_company = relationship("Company", back_populates="behavioral_simulations")
    target_segment = relationship("Segment", back_populates="behavioral_simulations")

class NetworkEntity(Base):
    __tablename__ = "NetworkEntities"
    entity_id = Column(Integer, primary_key=True, autoincrement=True) # Pode ser UUID se preferir
    entity_type = Column(String, nullable=False)
    company_id = Column(Integer, ForeignKey("Companies.company_id"), nullable=True)
    entity_name = Column(String, nullable=False)
    metadata_json = Column(JSON, nullable=True) # Usar JSONB se for PostgreSQL
    company_obj = relationship("Company", back_populates="network_entity_link")
    # Relações como source ou target
    relationships_as_source = relationship("NetworkRelationship", foreign_keys="[NetworkRelationship.source_entity_id]", back_populates="source_entity")
    relationships_as_target = relationship("NetworkRelationship", foreign_keys="[NetworkRelationship.target_entity_id]", back_populates="target_entity")
    network_analyses_as_focus = relationship("NetworkAnalysisComputation", foreign_keys="[NetworkAnalysisComputation.focus_entity_id]", back_populates="focus_entity_obj")


class NetworkRelationship(Base):
    __tablename__ = "NetworkRelationships"
    relationship_id = Column(Integer, primary_key=True, autoincrement=True) # Pode ser UUID
    source_entity_id = Column(Integer, ForeignKey("NetworkEntities.entity_id"), nullable=False)
    target_entity_id = Column(Integer, ForeignKey("NetworkEntities.entity_id"), nullable=False)
    relationship_type = Column(String, nullable=False)
    weight = Column(Float, nullable=True)
    direction = Column(String, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    metadata_json = Column(JSON, nullable=True) # Usar JSONB se for PostgreSQL
    source_entity = relationship("NetworkEntity", foreign_keys=[source_entity_id], back_populates="relationships_as_source")
    target_entity = relationship("NetworkEntity", foreign_keys=[target_entity_id], back_populates="relationships_as_target")

class NetworkAnalysisComputation(Base):
    __tablename__ = "NetworkAnalysisComputations"
    analysis_id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_datetime = Column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    network_analysis_type = Column(String, nullable=False)
    focus_company_id = Column(Integer, ForeignKey("Companies.company_id"), nullable=True)
    focus_entity_id = Column(Integer, ForeignKey("NetworkEntities.entity_id"), nullable=True)
    input_parameters_json = Column(JSON, nullable=True) # Usar JSONB se for PostgreSQL
    results_json = Column(JSON, nullable=False) # Usar JSONB se for PostgreSQL
    analyst_notes = Column(Text, nullable=True)
    focus_company_obj = relationship("Company", foreign_keys=[focus_company_id], back_populates="network_analyses_as_focus")
    focus_entity_obj = relationship("NetworkEntity", foreign_keys=[focus_entity_id], back_populates="network_analyses_as_focus")


def create_tables(engine_to_use):
    """Cria todas as tabelas definidas no metadado do Base."""
    Base.metadata.create_all(engine_to_use)
    print("Tabelas criadas (ou já existentes e verificadas) com sucesso!")

def main():
    """Função principal para configurar o motor e criar as tabelas."""
    if not settings.ACTIVE_DATABASE_URL:
        settings.logger.error("Erro: ACTIVE_DATABASE_URL não está configurada em config/settings.py.")
        settings.logger.error("Defina DATABASE_URL_POSTGRES e configure ACTIVE_DATABASE_URL.")
        return

    db_url_for_engine = settings.ACTIVE_DATABASE_URL
    settings.logger.info(f"Usando URL de banco de dados configurada: {settings.ACTIVE_DATABASE_URL.split('@')[-1] if '@' in settings.ACTIVE_DATABASE_URL else settings.ACTIVE_DATABASE_URL}")

    # Lógica para garantir que o diretório exista APENAS para bancos de dados baseados em arquivo
    # (ex: SQLite ou um arquivo DuckDB local que não seja :memory:)
    # Uma heurística comum é que URLs de rede contêm "://"
    is_likely_file_based_db = "://" not in settings.ACTIVE_DATABASE_URL

    if is_likely_file_based_db:
        db_file_path = settings.ACTIVE_DATABASE_URL # Assume que é um caminho de arquivo
        settings.logger.info(f"Detectado banco de dados baseado em arquivo: {db_file_path}")
        
        # Constrói o caminho absoluto se for relativo
        if not os.path.isabs(db_file_path):
            # Lembre-se que project_root foi definido no início do script
            db_file_path = os.path.join(project_root, db_file_path)
            settings.logger.info(f"Caminho absoluto para o arquivo do banco de dados: {db_file_path}")
        
        db_dir = os.path.dirname(db_file_path)
        if db_dir: # Garante que db_dir não seja uma string vazia (caso o path seja só o nome do arquivo)
            if not os.path.exists(db_dir):
                try:
                    os.makedirs(db_dir)
                    settings.logger.info(f"Diretório criado para o arquivo do banco de dados: {db_dir}")
                except OSError as e:
                    settings.logger.error(f"Erro ao criar diretório {db_dir}: {e}")
                    return
        # A URL para create_engine (db_url_for_engine) já deve estar formatada corretamente
        # (ex: "sqlite:///caminho/completo/arquivo.db" ou "duckdb:///caminho/completo/arquivo.duckdb")
        # Se ACTIVE_DATABASE_URL for apenas "data/meu.db", você precisaria prefixá-la aqui
        # Ex: if not db_url_for_engine.startswith("sqlite:///"): db_url_for_engine = f"sqlite:///{db_file_path}"
        # No seu caso, como é PostgreSQL, este bloco será pulado.

    # Criar o engine usando a URL original e as opções do settings.py
    engine = create_engine(db_url_for_engine, **settings.SQLALCHEMY_ENGINE_OPTIONS)
    
    try:
        # Testar a conexão
        with engine.connect() as connection:
            settings.logger.info("Conexão com o banco de dados estabelecida com sucesso.")
        
        # Criar as tabelas
        create_tables(engine) # Esta é a sua função que chama Base.metadata.create_all(engine)

    except Exception as e:
        settings.logger.error(f"Erro ao conectar ou criar tabelas: {e}")
        settings.logger.error("Verifique se o servidor de banco de dados PostgreSQL está rodando e se a URL de conexão está correta em config/settings.py.")
        settings.logger.error(f"URL utilizada para o engine: {db_url_for_engine.split('@')[0] if '@' in db_url_for_engine else db_url_for_engine}") # Loga sem user:pass

if __name__ == "__main__":
    main()