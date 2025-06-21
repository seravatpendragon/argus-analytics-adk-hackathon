# src/pipelines/run_llm_analysis_pipeline.py

import sys
import codecs

from diskcache import Cache # Certifique-se de que codecs está importado
# Tenta forçar sys.stdout e sys.stderr para UTF-8, o mais cedo possível
try:
    if hasattr(sys.stdout, 'reconfigure'): # Python 3.7+
        sys.stdout.reconfigure(encoding='utf-8')
    else: # Versões mais antigas ou ambientes onde reconfigure não é aplicável
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)
except Exception:
    pass

import os
import asyncio
import time
import hashlib
from collections import deque
import traceback
from vertexai.language_models import TextEmbeddingModel # Importar aqui
import vertexai

# ... (seus outros imports permanecem os mesmos) ...
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
from google.genai.types import Content, Part
from config.settings import PROJECT_ID, LOCATION

# --- CLASSE DO RATE LIMITER (NOVA) ---
class AsyncRateLimiter:
    def __init__(self, rate_limit: int, period_seconds: int):
        self.rate_limit = rate_limit
        self.period_seconds = period_seconds
        self.timestamps = deque()
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            while True:
                now = time.monotonic()
                while self.timestamps and self.timestamps[0] <= now - self.period_seconds:
                    self.timestamps.popleft()
                if len(self.timestamps) < self.rate_limit:
                    self.timestamps.append(now)
                    break
                wait_time = self.timestamps[0] + self.period_seconds - now
                await asyncio.sleep(wait_time)


# --- CONFIGURAÇÕES ---
MAX_CONCURRENT_TASKS = 3
RAG_SIMILARITY_THRESHOLD = 0.98
MAX_TOKENS_BEFORE_COMPRESSION = 1500
MAX_COMPRESSION_DEPTH = 3
API_CALLS_PER_MINUTE = 5 
API_TIME_PERIOD_SECONDS = 60


settings.logger.info("Inicializando modelos e cache...")
try:
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    settings.logger.info(f"Vertex AI inicializado | Projeto: {PROJECT_ID} | Região: {LOCATION}")
except Exception as e:
    settings.logger.error(f"Falha na inicialização do Vertex AI: {str(e)}")
    # Não é necessário levantar exceção, mas sem isso o embedding não funcionará
    
# <<< INÍCIO DO BLOCO DE TRATAMENTO DE ERRO PARA EMBEDDING MODEL >>>
embedding_model = None # Inicializa como None
try:
    embedding_model = TextEmbeddingModel.from_pretrained(settings.TEXT_EMBBEDING) # Tenta carregar o modelo
    settings.logger.info("Modelo de embedding 'text-embedding-005' inicializado com sucesso.")
except Exception as e:
    settings.logger.warning(f"Não foi possível inicializar o modelo de embedding: {e}. O RAG não funcionará corretamente.")
    # Não levanta a exceção, apenas loga e continua com embedding_model como None
# <<< FIM DO BLOCO DE TRATAMENTO DE ERRO PARA EMBEDDING MODEL >>>

CACHE_DIR = settings.BASE_DIR / ".analysis_cache"
cache = Cache(CACHE_DIR)
rate_limiter = AsyncRateLimiter(API_CALLS_PER_MINUTE, API_TIME_PERIOD_SECONDS) 


def get_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

def count_tokens(text: str) -> int:
    return len(text) // 4

# <<< MODIFICAÇÃO NA FUNÇÃO generate_embedding >>>
def generate_embedding(text: str) -> list[float]:
    """Função síncrona para gerar embedding. Retorna um embedding dummy se o modelo não carregar."""
    if embedding_model is None:
        settings.logger.warning("Modelo de embedding não carregado. Retornando embedding dummy (zeros) para permitir continuidade.")
        return [0.0] * 768 
    
    try:
        # <<< AQUI ESTÁ A CORREÇÃO: REMOVER task_type >>>
        embeddings = embedding_model.get_embeddings(
            texts=[text] 
            # REMOVIDO: task_type="RETRIEVAL_DOCUMENT" - Conforme o erro indica, este argumento não é esperado
        )
        return embeddings[0].values
    except Exception as e:
        settings.logger.error(f"Erro CRÍTICO ao gerar embedding com modelo carregado: {str(e)}. Retornando embedding dummy para não travar o pipeline.")
        return [0.0] * 768 # Retorna um vetor dummy para permitir que o pipeline continue em caso de falha.



async def compress_text(text: str, article_id: int, depth=0) -> str:
    if depth >= MAX_COMPRESSION_DEPTH:
        settings.logger.warning(f"Max compression depth reached for article {article_id}")
        return text
    token_count = count_tokens(text)
    if token_count <= MAX_TOKENS_BEFORE_COMPRESSION:
        return text
    try:
        settings.logger.info(f"Compressão (nível {depth+1}) para artigo {article_id}...")
        await rate_limiter.acquire()
        message_to_sub_agent = Content(role='user', parts=[Part(text=text)]) # Passa Content
        response = await run_agent_and_get_final_response(SubAgenteResumo_ADK, message_to_sub_agent, f"compress_{article_id}_l{depth}")
        summary_dict = parse_llm_json_response(response)
        if not summary_dict or "summary" not in summary_dict:
            raise ValueError("Resposta de compressão inválida")
        summary = summary_dict["summary"]
        return await compress_text(summary, article_id, depth+1)
    except Exception as e:
        settings.logger.error(f"Falha na compressão: {e}")
        return text

# --- FUNÇÃO PRINCIPAL DE PROCESSAMENTO MODIFICADA ---
async def process_article_with_optimizations(article, semaphore: asyncio.Semaphore):
    def calculate_overall_confidence(llm_analysis_json: dict, conflict_analysis_json: dict, current_source_credibility: float) -> float:
        shannon_entropy = llm_analysis_json.get("analise_quantitativa", {}).get("shannon_relative_entropy", 0.0)
        relevance_score = llm_analysis_json.get("analise_entidades", {}).get("relevancia_mercado_financeiro", 0.0)
        
        internal_confidence_score = conflict_analysis_json.get("confidence_score", 0) / 100.0 

        overall_score = current_source_credibility * shannon_entropy * relevance_score * internal_confidence_score * 100
        return min(100, max(0, overall_score))

    async with semaphore:
        article_id = article.get('news_article_id')
        text = article.get('article_text_content')
        news_source_url = article.get('news_source_url', 'N/A')
        source_credibility = article.get('source_credibility', 0.5)
        
        if not text or not article_id:
            settings.logger.error(f"Artigo {article_id} sem conteúdo ou ID")
            return {"id": article_id, "status": "failed", "reason": "Missing content or ID"}
            
        try:
            # 1. Verificação de Cache
            text_hash = get_text_hash(text)
            if text_hash in cache:
                settings.logger.info(f"Cache hit: Artigo {article_id}")
                cached_analysis = cache[text_hash]
                
                cached_analysis["source_credibility"] = source_credibility
                llm_output_from_cache = cached_analysis.get("llm_analysis_output", {})
                conflict_output_from_cache = cached_analysis.get("conflict_analysis_output", {})

                cached_analysis["overall_confidence_score"] = calculate_overall_confidence(llm_output_from_cache, conflict_output_from_cache, source_credibility)
                cached_analysis["overall_confidence_justification"] = "Calculado com base na credibilidade da fonte, entropia de Shannon, relevância financeira e consistência interna da análise."
                
                update_article_with_analysis(article_id, cached_analysis) 
                return {"id": article_id, "status": cached_analysis.get("processing_status", "cached_complete")}
            
            # 2. Compressão Adaptativa
            processed_text = await compress_text(text, article_id)
            
            # 3. Geração de Embedding com Rate Limiter
            settings.logger.info(f"Aguardando permissão do Rate Limiter para embedding do artigo {article_id}...")
            await rate_limiter.acquire() 
            settings.logger.info(f"Permissão concedida. Gerando embedding para o artigo {article_id}.")
            embedding = await asyncio.to_thread(generate_embedding, processed_text)
            
            if not embedding: 
                settings.logger.warning(f"Artigo {article_id}: Embedding não pôde ser gerado ou retornou vazio. Pulando RAG.")
                # Se o embedding falhar, não podemos fazer RAG, mas podemos continuar com a análise LLM
                # Para hackathon, deixamos passar para a próxima etapa sem RAG hit
                pass # Não levanta erro, apenas não faz a busca RAG

            # 4. Busca RAG
            similar = None # Inicializa similar
            if embedding and len(embedding) == 768: # Só tenta RAG se o embedding for válido
                similar = find_similar_article(embedding, RAG_SIMILARITY_THRESHOLD)
            
            if similar:
                settings.logger.info(f"RAG hit: Artigo {article_id} similar ao {similar['id']}")
                rag_analysis = similar["analysis"]
                
                rag_analysis["source_credibility"] = source_credibility

                llm_output_from_rag = rag_analysis.get("llm_analysis_output", {})
                conflict_output_from_rag = rag_analysis.get("conflict_analysis_output", {})
                rag_analysis["overall_confidence_score"] = calculate_overall_confidence(llm_output_from_rag, conflict_output_from_rag, source_credibility)
                rag_analysis["overall_confidence_justification"] = "Calculado com base na credibilidade da fonte, entropia de Shannon, relevância financeira e consistência interna da análise."

                update_article_with_analysis(article_id, rag_analysis)
                cache[text_hash] = rag_analysis
                return {"id": article_id, "embedding": embedding, "status": rag_analysis.get("processing_status", "rag_complete")}
            
            # 5. Análise Completa (inclui orquestração e auditoria interna)
            settings.logger.info(f"Iniciando análise completa e auditoria interna para o Artigo {article_id}.")
            
            settings.logger.warning(f"Pausa de seguran├ºa de {API_TIME_PERIOD_SECONDS * 0.5}s antes da an├ílise completa do artigo {article_id} para respeitar LLM Rate Limit externo.")
            await asyncio.sleep(API_TIME_PERIOD_SECONDS * 0.5) 
            
            # Passa Content object para o Agente Gerenciador
            message_to_manager_agent = Content(role='user', parts=[Part(text=processed_text)])
            response = await run_agent_and_get_final_response(
                AgenteGerenciadorAnalise_ADK,
                message_to_manager_agent, 
                f"full_analysis_{article_id}"
            )
            
            parsed_agent_response = parse_llm_json_response(response)
            
            if not parsed_agent_response or "llm_analysis_output" not in parsed_agent_response or "conflict_analysis_output" not in parsed_agent_response or "final_processing_status" not in parsed_agent_response:
                raise ValueError("Resposta de an├ílise inv├ílida ou incompleta do Agente Gerenciador (n├úo cont├®m os JSONs e/ou status esperados).")

            llm_analysis_output = parsed_agent_response["llm_analysis_output"]
            conflict_analysis_output = parsed_agent_response["conflict_analysis_output"]
            final_article_status = parsed_agent_response["final_processing_status"] 
            
            overall_confidence_score = calculate_overall_confidence(llm_analysis_output, conflict_analysis_output, source_credibility)

            data_to_persist = {
                "llm_analysis_output": llm_analysis_output,
                "conflict_analysis_output": conflict_analysis_output,
                "source_credibility": source_credibility,
                "overall_confidence_score": overall_confidence_score,
                "processing_status": final_article_status
            }

            update_article_with_analysis(article_id, data_to_persist)
            cache[text_hash] = data_to_persist 
            return {"id": article_id, "embedding": embedding, "status": final_article_status}

        except Exception as e:
            settings.logger.exception(f"Falha no processamento completo do artigo {article_id}: {e}")
            return {"id": article_id, "status": "analysis_failed", "reason": str(e)}


async def main():
    settings.logger.info("--- IN├ìCIO DO PIPELINE OTIMIZADO ---")
    
    start_time = time.time()
    total_processed_count = 0
    total_success_complete = 0
    total_rejected = 0
    total_failed = 0
    total_cached = 0
    total_rag_hit = 0
    
    while True:
        try:
            with get_db_session() as session:
                articles = get_articles_pending_analysis(session, limit=3000) 
            
            if not articles:
                settings.logger.info("Nenhum artigo pendente")
                break
                
            settings.logger.info(f"Processando {len(articles)} artigos com concorr├¬ncia m├íxima de {MAX_CONCURRENT_TASKS} tarefas.")
            
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
            tasks = [process_article_with_optimizations(a, semaphore) for a in articles]
            
            results = []
            for task in asyncio.as_completed(tasks):
                try:
                    result = await task
                    if result:
                        results.append(result)
                    total_processed_count += 1
                    if total_processed_count % 10 == 0:
                        elapsed_time = time.time() - start_time
                        articles_per_minute = (total_processed_count / elapsed_time) * 60 if elapsed_time > 0 else 0
                        settings.logger.info(f"Progresso: {total_processed_count} artigos processados. (Velocidade: {articles_per_minute:.2f} art/min)")

                except Exception as e:
                    settings.logger.error(f"Erro irrecuper├ível em uma task do as_completed: {e}")
            
            embeddings_to_update = [(r["id"], r["embedding"]) for r in results if r.get("embedding")]
            
            if embeddings_to_update:
                settings.logger.info(f"Atualizando {len(embeddings_to_update)} embeddings no banco de dados...")
                batch_update_precomputed_embeddings(embeddings_to_update)
                
            for r in results:
                if r['status'] == 'analysis_complete':
                    total_success_complete += 1
                elif r['status'] == 'analysis_rejected':
                    total_rejected += 1
                elif r['status'] == 'analysis_failed':
                    total_failed += 1
                elif r['status'] == 'cached':
                    total_cached += 1
                elif r['status'] == 'rag_hit':
                    total_rag_hit += 1

            settings.logger.info(
                f"RESUMO FINAL: Processados={total_processed_count} | "
                f"An├ílise Completa={total_success_complete} | "
                f"Rejeitados={total_rejected} | "
                f"Falhas na An├ílise={total_failed} | "
                f"Do Cache={total_cached} | "
                f"Do RAG={total_rag_hit}"
            )
        
        except Exception as e:
            settings.logger.critical(f"Falha catastr├│fica no pipeline: {e}\n{traceback.format_exc()}")


if __name__ == "__main__":
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    asyncio.run(main())