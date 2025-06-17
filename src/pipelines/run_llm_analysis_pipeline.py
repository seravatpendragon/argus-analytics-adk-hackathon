import os
import asyncio
import hashlib
import numpy as np
from diskcache import Cache
from vertexai.language_models import TextEmbeddingModel

# Imports internos
from config import settings
from src.agents.agent_utils import run_agent_and_get_final_response
from src.database.db_utils import (
    get_articles_pending_analysis,
    get_db_session,
    update_article_with_analysis,
    find_similar_article,
    batch_update_precomputed_embeddings
)
from src.agents.analistas.agente_gerenciador_analise_adk.agent import AgenteGerenciadorAnalise_ADK
from src.agents.analistas.sub_agentes_analise.sub_agente_resumo_adk.agent import SubAgenteResumo_ADK
from src.utils.parser_utils import parse_llm_json_response

# --- CONFIGURAÇÕES ---
MAX_CONCURRENT_TASKS = 3
RAG_SIMILARITY_THRESHOLD = 0.98
MAX_TOKENS_BEFORE_COMPRESSION = 1500
MAX_COMPRESSION_DEPTH = 3

settings.logger.info("Inicializando modelos e cache...")
embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-005")
CACHE_DIR = settings.BASE_DIR / ".analysis_cache"
cache = Cache(CACHE_DIR)

def get_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

def count_tokens(text: str) -> int:
    """Estimativa de tokens baseada em heurística (4 caracteres por token)"""
    return len(text) // 4  # Aproximação conservadora

def generate_embedding(text: str) -> list[float]:
    embeddings = embedding_model.get_embeddings([text])
    return embeddings[0].values

async def compress_text(text: str, article_id: int, depth=0) -> str:
    """Compressão recursiva com limite de profundidade"""
    if depth >= MAX_COMPRESSION_DEPTH:
        settings.logger.warning(f"Max compression depth reached for article {article_id}")
        return text
        
    token_count = count_tokens(text)
    if token_count <= MAX_TOKENS_BEFORE_COMPRESSION:
        return text
        
    try:
        settings.logger.info(f"Compressão (nível {depth+1}) para artigo {article_id}...")
        response = await run_agent_and_get_final_response(
            SubAgenteResumo_ADK, 
            text, 
            f"compress_{article_id}_l{depth}"
        )
        
        # Parse seguro do JSON
        summary_dict = parse_llm_json_response(response)
        if not summary_dict or "summary" not in summary_dict:
            raise ValueError("Resposta de compressão inválida")
            
        summary = summary_dict["summary"]
        return await compress_text(summary, article_id, depth+1)
        
    except Exception as e:
        settings.logger.error(f"Falha na compressão: {e}")
        return text

async def process_article_with_optimizations(article, semaphore: asyncio.Semaphore):
    async with semaphore:
        article_id = article['news_article_id']
        text = article['article_text_content']
        
        if not text or not article_id:
            settings.logger.error(f"Artigo {article_id} sem conteúdo")
            return None
            
        try:
            # 1. Verificação de Cache
            text_hash = get_text_hash(text)
            if text_hash in cache:
                settings.logger.info(f"Cache hit: Artigo {article_id}")
                update_article_with_analysis(article_id, cache[text_hash])
                return {"id": article_id, "cached": True}
            
            # 2. Compressão Adaptativa
            processed_text = text
            token_count = count_tokens(text)
            if token_count > MAX_TOKENS_BEFORE_COMPRESSION:
                settings.logger.info(f"Texto longo ({token_count} tokens estimados). Comprimindo artigo {article_id}...")
                processed_text = await compress_text(text, article_id)
                new_token_count = count_tokens(processed_text)
                settings.logger.info(f"Texto comprimido para {new_token_count} tokens estimados")
            
            # 3. Geração de Embedding
            embedding = await asyncio.to_thread(generate_embedding, processed_text)
            # Manter como lista de floats (não converter para numpy)
            
            # 4. Busca RAG
            similar = find_similar_article(embedding, RAG_SIMILARITY_THRESHOLD)
            if similar:
                settings.logger.info(f"RAG hit: Artigo {article_id} similar ao {similar['id']}")
                update_article_with_analysis(article_id, similar["analysis"])
                cache[text_hash] = similar["analysis"]
                return {"id": article_id, "embedding": embedding}
            
            # 5. Análise Completa
            settings.logger.info(f"Análise completa: Artigo {article_id}")
            response = await run_agent_and_get_final_response(
                AgenteGerenciadorAnalise_ADK,
                processed_text,
                f"full_analysis_{article_id}"
            )
            
            # Parse seguro do JSON
            analysis = parse_llm_json_response(response)
            if not analysis:
                raise ValueError("Resposta de análise inválida")
                
            update_article_with_analysis(article_id, analysis)
            cache[text_hash] = analysis
            return {"id": article_id, "embedding": embedding}
            
        except Exception as e:
            settings.logger.exception(f"Falha no artigo {article_id}: {e}")
            return None

async def main():
    settings.logger.info("--- INÍCIO DO PIPELINE OTIMIZADO ---")
    
    try:
        with get_db_session() as session:
            # Obter artigos como dicionários
            articles = get_articles_pending_analysis(session, limit=5)
        
        if not articles:
            settings.logger.info("Nenhum artigo pendente")
            return
            
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
        tasks = [process_article_with_optimizations(a, semaphore) for a in articles]
        
        results = []
        for task in asyncio.as_completed(tasks):
            try:
                result = await task
                if result:
                    results.append(result)
            except Exception as e:
                settings.logger.error(f"Erro em task: {e}")
        
        # Atualização em lote de embeddings
        embeddings_to_update = [
            (r["id"], r["embedding"]) 
            for r in results 
            if "embedding" in r
        ]
        
        if embeddings_to_update:
            settings.logger.info(f"Atualizando {len(embeddings_to_update)} embeddings...")
            batch_update_precomputed_embeddings(embeddings_to_update)
        
        # Métricas de desempenho
        success = len(results)
        cached = sum(1 for r in results if "cached" in r)
        rag_reused = sum(1 for r in results if "embedding" in r and "cached" not in r)
        
        settings.logger.info(
            f"RESUMO: Artigos={len(articles)} | "
            f"Sucessos={success} | "
            f"Cache={cached} | "
            f"RAG={rag_reused} | "
            f"Falhas={len(articles) - success}"
        )
    
    except Exception as e:
        settings.logger.critical(f"Falha catastrófica no pipeline: {e}")

if __name__ == "__main__":
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    asyncio.run(main())