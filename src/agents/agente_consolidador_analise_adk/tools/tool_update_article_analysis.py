# src/agents/agente_consolidador_analise_adk/tools/tool_update_article_analysis.py

import logging
from typing import Dict, Any, Optional
import json

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
            self.llm_analysis_json = kwargs.get("llm_analysis_json")
            self.processing_status = kwargs.get("processing_status")
            self.article_type = kwargs.get("article_type") # Para simular atualização

        def __repr__(self):
            return f"<MockNewsArticle(id={self.news_article_id}, headline='{self.headline[:30]}...')>"

    _mock_articles_in_db_for_update = {} # Dicionário para simular artigos no DB
    # Preencher com alguns artigos mock para teste de atualização
    _mock_articles_in_db_for_update[11645] = MockNewsArticle(
        news_article_id=11645,
        headline="Notícia Teste 1: Petrobras e o mercado de petróleo",
        llm_analysis_json=None,
        processing_status="pending_llm_analysis",
        article_link="http://mock.com/article1", # Adicionado para evitar erro de modelo
        article_type="Notícia de Mídia"
    )
    _mock_articles_in_db_for_update[11646] = MockNewsArticle(
        news_article_id=11646,
        headline="Documento CVM: Nova diretoria da PETR4 anunciada",
        llm_analysis_json=None,
        processing_status="pending_llm_analysis",
        article_link="http://mock.com/cvm_doc1", # Adicionado para evitar erro de modelo
        article_type="Documento Regulatório CVM"
    )

    class MockDBSession:
        def query(self, model):
            if model == NewsArticle:
                return MockQuery(model)
            return None

        def commit(self):
            logger.info("MOCK DB: Commit simulado para atualização.")

        def rollback(self):
            logger.warning("MOCK DB: Rollback simulado para atualização.")

        def close(self):
            pass

    class MockQuery:
        def __init__(self, model):
            self.model = model
            self._filters = []

        def filter(self, *args):
            self._filters.extend(args)
            return self

        def first(self):
            # Simula a busca de um artigo pelo ID
            for f in self._filters:
                attr_name = f.left.name if hasattr(f.left, 'name') else None
                if attr_name == "news_article_id":
                    article_id = f.right
                    return _mock_articles_in_db_for_update.get(article_id)
            return None

    def get_db_session():
        return MockDBSession()

    NewsArticle = MockNewsArticle # Atribui o mock à variável real


logger = logging.getLogger(__name__)

def tool_update_article_analysis(
    news_article_id: int,
    llm_analysis_json: Dict[str, Any],
    suggested_article_type: Optional[str] = None, # Para atualizar o tipo do artigo se houver
    tool_context: Any = None # ToolContext é opcional para esta ferramenta
) -> Dict[str, Any]:
    """
    Atualiza um artigo no banco de dados com os resultados da análise LLM.

    Args:
        news_article_id (int): O ID do artigo a ser atualizado.
        llm_analysis_json (Dict[str, Any]): O dicionário JSON consolidado com todos os resultados da análise LLM.
        suggested_article_type (Optional[str]): O tipo de artigo refinado sugerido pelo LLM.
        tool_context (Any): O contexto da ferramenta (opcional, injetado pelo ADK).

    Returns:
        Dict[str, Any]: Um dicionário com 'status' ('success' ou 'error') e uma mensagem.
    """
    session = get_db_session()
    
    try:
        article = session.query(NewsArticle).filter_by(news_article_id=news_article_id).first()

        if not article:
            session.rollback()
            logger.error(f"Artigo com ID {news_article_id} não encontrado para atualização.")
            return {"status": "error", "message": f"Artigo ID {news_article_id} não encontrado."}

        article.llm_analysis_json = llm_analysis_json
        article.processing_status = 'llm_analysis_complete' # Marca como concluído

        if suggested_article_type:
            article.article_type = suggested_article_type # Atualiza o tipo se fornecido

        session.commit()
        logger.info(f"Artigo ID {news_article_id} atualizado com sucesso com análise LLM.")
        return {"status": "success", "message": f"Artigo ID {news_article_id} atualizado."}

    except Exception as e:
        session.rollback()
        logger.error(f"Erro ao atualizar artigo ID {news_article_id} com análise LLM: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

    finally:
        session.close()