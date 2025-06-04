# src/agents/agente_gerenciador_analise_llm_adk/tools/tool_fetch_pending_articles.py

import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session as DBSession # Renomear para evitar conflito com Session do ADK

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
            self.article_text_content = kwargs.get("article_text_content")
            self.summary = kwargs.get("summary")
            self.processing_status = kwargs.get("processing_status")

        def __repr__(self):
            return f"<MockNewsArticle(id={self.news_article_id}, headline='{self.headline[:30]}...')>"

    _mock_articles_in_db = [
        MockNewsArticle(
            news_article_id=1,
            headline="Notícia Teste 1: Petrobras e o mercado de petróleo",
            article_link="http://mock.com/article1",
            article_text_content="O preço do petróleo subiu hoje, impactando as ações da Petrobras. Analistas preveem volatilidade.",
            summary="Preço do petróleo e ações da Petrobras.",
            processing_status="pending_llm_analysis"
        ),
        MockNewsArticle(
            news_article_id=2,
            headline="Documento CVM: Nova diretoria da PETR4 anunciada",
            article_link="http://mock.com/cvm_doc1",
            article_text_content="A Petrobras anunciou mudanças em sua diretoria executiva, com foco em governança corporativa e sustentabilidade.",
            summary="Mudanças na diretoria da Petrobras.",
            processing_status="pending_llm_analysis"
        ),
        MockNewsArticle(
            news_article_id=3,
            headline="Notícia Teste 3: Desempenho da PETR4 no último trimestre",
            article_link="http://mock.com/article3",
            article_text_content="Resultados financeiros da Petrobras superam expectativas no último trimestre, impulsionados pela produção do pré-sal.",
            summary="Resultados trimestrais da Petrobras.",
            processing_status="pending_llm_analysis"
        ),
        MockNewsArticle( # Artigo já analisado, não deve ser retornado
            news_article_id=4,
            headline="Notícia Teste 4: Já analisada",
            article_link="http://mock.com/article4",
            article_text_content="Este artigo já foi processado.",
            summary="Já processado.",
            processing_status="llm_analysis_complete"
        )
    ]

    class MockDBSession:
        def query(self, model):
            if model == NewsArticle:
                return MockQuery(model)
            return None # Ou levantar erro para outros modelos

        def close(self):
            pass # No-op para mock

    class MockQuery:
        def __init__(self, model):
            self.model = model
            self._filters = []

        def filter(self, *args):
            self._filters.extend(args)
            return self

        def all(self):
            results = []
            for article in _mock_articles_in_db:
                match = True
                for f in self._filters:
                    # Simplesmente verifica se o atributo existe e corresponde ao valor
                    # Isso é uma simulação bem básica de filter_by
                    attr_name = f.left.name if hasattr(f.left, 'name') else None
                    if attr_name and hasattr(article, attr_name) and getattr(article, attr_name) != f.right:
                        match = False
                        break
                if match:
                    results.append(article)
            return results
        
        def first(self):
            # Para simular .first() no mock
            results = self.all()
            return results[0] if results else None

    def get_db_session():
        return MockDBSession()

    NewsArticle = MockNewsArticle # Atribui o mock à variável real para uso abaixo


logger = logging.getLogger(__name__)

def tool_fetch_pending_articles(limit: int = 5) -> Dict[str, Any]:
    """
    Busca artigos da tabela NewsArticles que estão com status 'pending_llm_analysis'.

    Args:
        limit (int): O número máximo de artigos a serem buscados.

    Returns:
        Dict[str, Any]: Um dicionário com 'status' ('success' ou 'error') e uma lista
                        de dicionários de artigos ('articles_data').
    """
    session = get_db_session()
    articles_data: List[Dict[str, Any]] = []
    
    try:
        # Busca artigos com status 'pending_llm_analysis'
        articles = session.query(NewsArticle).filter(
            NewsArticle.processing_status == 'pending_llm_analysis'
        ).limit(limit).all()

        for article in articles:
            # Converte o objeto ORM para um dicionário para passar entre agentes
            # Inclui apenas os campos relevantes para a análise LLM
            articles_data.append({
                "news_article_id": article.news_article_id,
                "headline": article.headline,
                "article_link": article.article_link,
                "article_text_content": article.article_text_content,
                "summary": article.summary,
                "processing_status": article.processing_status
                # Adicione outros campos se os sub-agentes de análise precisarem
            })
        
        logger.info(f"Ferramenta fetch_pending_articles: Encontrados {len(articles_data)} artigos pendentes.")
        return {"status": "success", "articles_data": articles_data}

    except Exception as e:
        logger.error(f"Erro ao buscar artigos pendentes: {e}", exc_info=True)
        return {"status": "error", "message": str(e), "articles_data": []}
    finally:
        session.close()