# src/agents/agente_armazenador_artigo_adk/tools/_mock_db_setup.py

from datetime import datetime
import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# --- MOCKS PARA MODELOS SQLALCHEMY ---
# (Você deve substituir estes pelos seus modelos reais de src/database/models.py)

class MockColumn:
    def __init__(self, *args, **kwargs):
        pass

class MockInteger(MockColumn): pass
class MockText(MockColumn): pass
class MockString(MockColumn): pass
class MockDateTime(MockColumn): pass
class MockJSON(MockColumn): pass
class MockForeignKey(MockColumn): pass

class MockBase:
    def __init__(self):
        pass

    def __repr__(self):
        return f"<{self.__class__.__name__} Mock Object>"

class MockNewsArticle(MockBase):
    __tablename__ = "NewsArticles" # Para referência
    news_article_id: int = 1 # ID mock
    headline: str
    article_link: str
    publication_date: datetime
    collection_date: datetime
    news_source_id: int
    article_text_content: str | None = None
    article_type: str | None = None
    llm_analysis_json: dict | None = None
    summary: str | None = None
    processing_status: str | None = None
    source_feed_name: str | None = None
    source_feed_url: str | None = None

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.collection_date = datetime.now() # Mock automático

    def __repr__(self):
        return f"<MockNewsArticle(id={self.news_article_id}, headline='{self.headline[:30]}...')>"

class MockNewsSource(MockBase):
    __tablename__ = "NewsSources" # Para referência
    news_source_id: int
    source_name_curated: str
    base_credibility_score: str # Mantido como string para compatibilidade com o db_utils real

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.news_source_id = hash(self.source_name_curated) % 10000 # ID simples mock

    def __repr__(self):
        return f"<MockNewsSource(id={self.news_source_id}, name='{self.source_name_curated}')>"

class MockCompany(MockBase):
    company_id: int
    cvm_code: str
    company_name: str

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.company_id = hash(self.cvm_code) % 10000 # ID simples mock

    def __repr__(self):
        return f"<MockCompany(id={self.company_id}, name='{self.company_name}')>"

class MockNewsArticleCompanyLink(MockBase):
    news_article_company_link_id: int = 1
    news_article_id: int
    company_id: int

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.news_article_company_link_id = hash(f"{self.news_article_id}-{self.company_id}") % 10000

    def __repr__(self):
        return f"<MockNewsArticleCompanyLink(article_id={self.news_article_id}, company_id={self.company_id})>"

# --- MOCKS PARA UTILIDADES DE BANCO DE DADOS ---
# (Você deve substituir estes pelas suas funções reais de src/database/db_utils.py)

_mock_db_session_data = {
    "NewsArticles": [],
    "NewsSources": {}, # Usar dicionário para acesso rápido por source_name_curated
    "Companies": {} # Usar dicionário para acesso rápido por cvm_code
}

class MockDBSession:
    def add(self, instance):
        if isinstance(instance, MockNewsArticle):
            instance.news_article_id = len(_mock_db_session_data["NewsArticles"]) + 1 # Atribui um ID mock
            _mock_db_session_data["NewsArticles"].append(instance)
            logger.info(f"MOCK DB: Adicionado NewsArticle: {instance.headline[:50]}...")
        elif isinstance(instance, MockNewsSource):
            if instance.source_name_curated not in _mock_db_session_data["NewsSources"]:
                instance.news_source_id = len(_mock_db_session_data["NewsSources"]) + 1 # Atribui um ID mock
                _mock_db_session_data["NewsSources"][instance.source_name_curated] = instance
                logger.info(f"MOCK DB: Adicionado NewsSource: {instance.source_name_curated}")
        elif isinstance(instance, MockCompany): # Adicionado mock para Company
            if instance.cvm_code not in _mock_db_session_data["Companies"]:
                instance.company_id = len(_mock_db_session_data["Companies"]) + 1 # Atribui um ID mock
                _mock_db_session_data["Companies"][instance.cvm_code] = instance
                logger.info(f"MOCK DB: Adicionado Company: {instance.company_name}")
        elif isinstance(instance, MockNewsArticleCompanyLink):
            logger.info(f"MOCK DB: Adicionado NewsArticleCompanyLink para article_id {instance.news_article_id} e company_id {instance.company_id}")
        else:
            logger.warning(f"MOCK DB: Tentativa de adicionar tipo desconhecido: {type(instance)}")

    def flush(self):
        pass

    def commit(self):
        logger.info("MOCK DB: Commit simulado.")
        pass

    def rollback(self):
        logger.warning("MOCK DB: Rollback simulado.")
        pass

    def close(self):
        logger.info("MOCK DB: Sessão fechada simulada.")
        pass

    # Simula query para NewsSource
    def query_news_source(self, source_name_curated: str):
        return _mock_db_session_data["NewsSources"].get(source_name_curated)
    
    # Simula query para Company
    def query_company_by_cvm_code(self, cvm_code: str):
        return _mock_db_session_data["Companies"].get(cvm_code)

def mock_get_db_session():
    return MockDBSession()

def mock_get_or_create_news_source(session: MockDBSession, source_name_curated: str, default_credibility_score: float, loaded_credibility_data: list[Dict[str, Any]]) -> int:
    news_source = session.query_news_source(source_name_curated)
    if not news_source:
        # Tenta encontrar a credibilidade nos dados carregados
        credibility_info = next((item for item in loaded_credibility_data if item.get("source_name") == source_name_curated), None)
        score_to_use = str(credibility_info.get("overall_credibility_score", default_credibility_score)) if credibility_info else str(default_credibility_score)

        news_source = MockNewsSource(source_name_curated=source_name_curated, base_credibility_score=score_to_use)
        session.add(news_source)
    return news_source.news_source_id

def mock_get_company_by_cvm_code(session: MockDBSession, cvm_code: str, company_name: str | None = None) -> int:
    company = session.query_company_by_cvm_code(cvm_code)
    if not company:
        company = MockCompany(cvm_code=cvm_code, company_name=company_name or f"Empresa CVM {cvm_code}")
        session.add(company) # Adiciona ao mock
    return company.company_id

# Inicializa algumas empresas mock para teste
# Não é necessário fazer isso aqui se o add da sessão já lida com a criação
# _mock_db_session_data["Companies"]["9512"] = MockCompany(company_id=1, cvm_code="9512", company_name="PETRÓLEO BRASILEIRO S.A. - PETROBRAS")