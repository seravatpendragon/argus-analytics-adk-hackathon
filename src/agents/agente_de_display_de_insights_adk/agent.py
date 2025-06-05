# src/agents/agente_de_display_de_insights_adk/tools/tool_fetch_analyzed_articles.py

from datetime import datetime, timedelta
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session as DBSession # Renomear para evitar conflito com Session do ADK
import json # Para lidar com o JSON do DB

# --- IMPORTAÇÕES REAIS ---
try:
    from src.database.db_utils import get_db_session
    from src.database.create_db_tables import NewsArticle # Importa o modelo NewsArticle
    _USING_MOCK_DB = False
except ImportError as e:
    logging.error(f"Não foi possível importar utilidades reais do banco de dados: {e}. O teste usará mocks.")
    _USING_MOCK_DB = True

# --- MOCK DB para testes standalone ---
if _USING_MOCK_DB:
    class MockNewsArticle:
        def __init__(self, **kwargs):
            self.news_article_id = kwargs.get("news_article_id")
            self.headline = kwargs.get("headline")
            self.article_link = kwargs.get("article_link")
            self.llm_analysis_json = kwargs.get("llm_analysis_json")
            self.processing_status = kwargs.get("processing_status")
            self.article_type = kwargs.get("article_type")
            self.summary = kwargs.get("summary")
            self.publication_date = kwargs.get("publication_date")

        def __repr__(self):
            return f"<MockNewsArticle(id={self.news_article_id}, headline='{self.headline[:30]}...')>"

    _mock_analyzed_articles_in_db = [
        MockNewsArticle(
            news_article_id=1,
            headline="Mock Notícia Analisada 1: PETR4 e Descoberta",
            article_link="http://mock.com/analyzed/article1",
            summary="Descoberta de novo campo de petróleo.",
            publication_date=datetime.now(),
            llm_analysis_json={
                "sentiment_analysis": {"sentiment_petr4": "positivo", "score": 0.8},
                "relevance_type_analysis": {"relevance_petr4": "Alta", "suggested_article_type": "Operacional"},
                "stakeholders_analysis": {"stakeholders": ["Investidores"]},
                "maslow_analysis": {"maslow_impact_primary": "Segurança"}
            },
            processing_status="llm_analysis_complete",
            article_type="Operacional"
        ),
        MockNewsArticle(
            news_article_id=2,
            headline="Mock Documento Analisado 2: Acordo PETR4",
            article_link="http://mock.com/analyzed/doc2",
            summary="Acordo de parceria estratégica.",
            publication_date=datetime.now() - timedelta(days=1),
            llm_analysis_json={
                "sentiment_analysis": {"sentiment_petr4": "neutro", "score": 0.5},
                "relevance_type_analysis": {"relevance_petr4": "Média", "suggested_article_type": "Comunicado"},
                "stakeholders_analysis": {"stakeholders": ["Parceiros"]},
                "maslow_analysis": {"maslow_impact_primary": "Sociais"}
            },
            processing_status="llm_analysis_complete",
            article_type="Comunicado"
        ),
        MockNewsArticle(
            news_article_id=3,
            headline="Mock Notícia Analisada 3: Balanço PETR4",
            article_link="http://mock.com/analyzed/article3",
            summary="Balanço do primeiro trimestre.",
            publication_date=datetime.now() - timedelta(days=2),
            llm_analysis_json={
                "sentiment_analysis": {"sentiment_petr4": "positivo", "score": 0.7},
                "relevance_type_analysis": {"relevance_petr4": "Alta", "suggested_article_type": "Resultados Trimestrais"},
                "stakeholders_analysis": {"stakeholders": ["Investidores Institucionais"]},
                "maslow_analysis": {"maslow_impact_primary": "Estima"}
            },
            processing_status="llm_analysis_complete",
            article_type="Resultados Trimestrais"
        )
    ]

    class MockDBSession:
        def query(self, model):
            if model == NewsArticle:
                return MockQuery(model)
            return None

        def close(self):
            pass

    class MockQuery:
        def __init__(self, model):
            self.model = model
            self._filters = []
            self._limit = None
            self._order_by = None

        def filter(self, *args):
            self._filters.extend(args)
            return self

        def limit(self, value: int):
            self._limit = value
            return self

        def order_by(self, *args):
            self._order_by = args # Simplesmente armazena, não implementa lógica de ordenação complexa
            return self

        def all(self):
            results = []
            for article in _mock_analyzed_articles_in_db:
                match = True
                for f in self._filters:
                    attr_name = f.left.name if hasattr(f.left, 'name') else None
                    if attr_name and hasattr(article, attr_name) and getattr(article, attr_name) != f.right:
                        match = False
                        break
                if match:
                    results.append(article)
            
            # Simula limite
            if self._limit:
                results = results[:self._limit]
            
            # Simula ordenação (muito básica, apenas para garantir que o mock não quebre)
            if self._order_by and results:
                # Tenta ordenar pelo primeiro order_by se for um atributo simples
                first_order_by = self._order_by[0]
                if hasattr(first_order_by, 'name'):
                    sort_key = first_order_by.name
                    reverse = first_order_by.desc() if hasattr(first_order_by, 'desc') else False
                    results.sort(key=lambda x: getattr(x, sort_key, None), reverse=reverse)

            return results
        
    def get_db_session():
        return MockDBSession()

    NewsArticle = MockNewsArticle # Atribui o mock à variável real


logger = logging.getLogger(__name__)

def tool_fetch_analyzed_articles(limit: int = 5) -> Dict[str, Any]:
    """
    Busca artigos da tabela NewsArticles que já foram analisados por LLMs.

    Args:
        limit (int): O número máximo de artigos a serem buscados.

    Returns:
        Dict[str, Any]: Um dicionário com 'status' ('success' ou 'error') e uma lista
                        de dicionários de artigos analisados ('analyzed_articles_data').
    """
    session = get_db_session()
    articles_data: List[Dict[str, Any]] = []
    
    try:
        # Busca artigos com status 'llm_analysis_complete'
        articles = session.query(NewsArticle).filter(
            NewsArticle.processing_status == 'llm_analysis_complete'
        ).order_by(NewsArticle.publication_date.desc()).limit(limit).all() # Ordena pela data de publicação mais recente

        for article in articles:
            # Converte o objeto ORM para um dicionário
            articles_data.append({
                "news_article_id": article.news_article_id,
                "headline": article.headline,
                "article_link": article.article_link,
                "summary": article.summary,
                "publication_date": article.publication_date.isoformat() if article.publication_date else None,
                "article_type": article.article_type,
                "llm_analysis_json": article.llm_analysis_json # Inclui o JSON completo da análise
            })
        
        logger.info(f"Ferramenta fetch_analyzed_articles: Encontrados {len(articles_data)} artigos analisados.")
        return {"status": "success", "analyzed_articles_data": articles_data}

    except Exception as e:
        logger.error(f"Erro ao buscar artigos analisados: {e}", exc_info=True)
        return {"status": "error", "message": str(e), "analyzed_articles_data": []}
    finally:
        session.close()