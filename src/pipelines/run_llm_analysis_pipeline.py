import os, sys, asyncio, json, hashlib
from pathlib import Path
from diskcache import Cache
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

# Bloco de import padrão ...
from config import settings
from src.agents.agent_utils import run_agent_and_get_final_response
from src.database.db_utils import batch_update_embeddings, get_articles_pending_analysis, get_db_session, update_article_with_analysis, update_article_embedding
from src.agents.analistas.agente_gerenciador_analise_adk.agent import AgenteGerenciadorAnalise_ADK
from src.agents.analistas.sub_agentes_analise.sub_agente_resumo_adk.agent import SubAgenteResumo_ADK
from src.utils.parser_utils import parse_llm_json_response

# Importa as bibliotecas corretas do Vertex AI
from vertexai.language_models import TextEmbeddingModel

# --- SETUP DA CAMADA DE OTIMIZAÇÃO ---
MAX_CONCURRENT_TASKS = 3
RAG_SIMILARITY_THRESHOLD = 0.98
MAX_TOKENS_BEFORE_COMPRESSION = 1000

settings.logger.info("Inicializando modelos de otimização e cache...")
embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-005")
CACHE_DIR = settings.BASE_DIR / ".analysis_cache"
cache = Cache(CACHE_DIR)

def get_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

async def compress_if_needed(text: str, article_id: int) -> str:
    """Verifica a contagem de tokens e comprime o texto se exceder o limite."""
    try:
        token_count = embedding_model.count_tokens(text).total_tokens
        if token_count > MAX_TOKENS_BEFORE_COMPRESSION:
            settings.logger.info(f"Artigo {article_id}: Texto longo detectado ({token_count} tokens). Aplicando compressão...")
            summary_response = await run_agent_and_get_final_response(SubAgenteResumo_ADK, text, f"compress_{article_id}")
            summary_dict = parse_llm_json_response(summary_response)
            if summary_dict and "summary" in summary_dict:
                compressed_text = summary_dict["summary"]
                new_token_count = embedding_model.count_tokens(compressed_text).total_tokens
                settings.logger.info(f"Artigo {article_id}: Texto comprimido para {new_token_count} tokens.")
                return compressed_text
    except Exception as e:
        settings.logger.error(f"Artigo {article_id}: Falha na contagem ou compressão de tokens: {e}")
    return text

async def process_article_with_optimizations(article: dict, semaphore: asyncio.Semaphore):
    """Orquestra a análise de um único artigo, aplicando Caching, RAG e Compressão."""
    async with semaphore:
        article_id, original_text = article.get("article_id"), article.get("text")
        if not all([article_id, original_text]): return False

        text_hash = get_text_hash(original_text)

        # 1. Tenta o Cache (a mais rápida)
        if text_hash in cache:
            settings.logger.info(f"CACHE HIT: Artigo {article_id}.")
            cached_analysis = cache[text_hash]
            update_article_with_analysis(article_id, cached_analysis)
            return True
        
        # A lógica RAG com pgvector precisará de uma função dedicada em db_utils
        # Por enquanto, focaremos no fluxo principal.

        # 2. Compressão Seletiva
        text_to_analyze = await compress_if_needed(original_text, article_id)
        
        # 3. Execução Completa da Análise
        settings.logger.info(f"CACHE/RAG MISS: Análise completa para o artigo {article_id}.")
        raw_response = await run_agent_and_get_final_response(AgenteGerenciadorAnalise_ADK, text_to_analyze, f"pipeline_{article_id}")
        
        if raw_response:
            analysis_dict = parse_llm_json_response(raw_response)
            if analysis_dict:
                update_article_with_analysis(article_id, analysis_dict)
                # MUDANÇA: Em vez de salvar o embedding, retorna os dados para o batch
                return {"id": article_id, "text": original_text}
        
            return None # Retorna None em caso de falha
        
        settings.logger.error(f"Falha total na análise do artigo {article_id}.")
        return False

async def main():
    """Função principal que busca artigos e dispara as análises em lote."""
    settings.logger.info("--- INICIANDO PIPELINE DE ANÁLISE OTIMIZADO ---")
    
    with get_db_session() as session:
        articles_to_analyze = get_articles_pending_analysis(session, limit=100)
    
    if not articles_to_analyze:
        print("Nenhum artigo novo para analisar.")
        return

    print(f"Encontrados {len(articles_to_analyze)} artigos. Iniciando com concorrência máxima de {MAX_CONCURRENT_TASKS}...")
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    tasks = [process_article_with_optimizations(article, semaphore) for article in articles_to_analyze]
    analysis_results = await asyncio.gather(*tasks)
    
    # Filtra apenas os que foram analisados com sucesso
    successfully_analyzed = [res for res in analysis_results if res is not None]
    
    sucessos = len(successfully_analyzed)
    falhas = len(articles_to_analyze) - sucessos
    print(f"\n--- RESUMO DA ANÁLISE --- \n✅ Sucessos: {sucessos}\n❌ Falhas: {falhas}")

    # --- NOVA ETAPA DE BATCHING DE EMBEDDINGS ---
    if successfully_analyzed:
        batch_update_embeddings(successfully_analyzed)
if __name__ == "__main__":
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    asyncio.run(main())