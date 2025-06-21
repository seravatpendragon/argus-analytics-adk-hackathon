# scripts/maintenance/reanalyze_low_confidence_articles.py

import os
import sys
import asyncio
import time
import json
from pathlib import Path
import traceback

from sqlalchemy import Float

# Adiciona o root do projeto ao path para permitir imports
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    # CORREÇÃO AQUI: Subir apenas dois níveis para o diretório raiz do projeto
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent 
    if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    # Fallback para o diretório de trabalho atual, menos ideal mas útil em alguns contextos
    PROJECT_ROOT = Path.cwd()
    if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from src.database.db_utils import get_db_session, update_article_with_analysis
from src.database.create_db_tables import NewsArticle, NewsSource 
from sqlalchemy.orm import joinedload
from src.agents.agent_utils import run_agent_and_get_final_response
# Verifique o caminho exato do AgenteGerenciadorAnalise_ADK
from src.agents.analistas.agente_gerenciador_analise_adk.agent import AgenteGerenciadorAnalise_ADK 
from src.data_processing.conflict_detector import ConflictDetector 
from src.utils.parser_utils import parse_llm_json_response
from google.genai.types import Content, Part

# --- CONFIGURAÇÕES DE REPROCESSAMENTO ---
# Limiar para reanalisar: se a confiança interna for MENOR que este valor
REANALYSIS_THRESHOLD = 85 
# Limite de artigos por execução
BATCH_SIZE = 5 
# Pausa entre cada artigo processado (para evitar sobrecarga de API)
SLEEP_BETWEEN_ARTICLES_SECONDS = 15 # Ajuste conforme seu rate limit de LLM
SLEEP_BETWEEN_BATCHES_SECONDS = 15

# --- FUNÇÃO AUXILIAR PARA CALCULAR OVERALL CONFIDENCE (MESMA DO PIPELINE PRINCIPAL) ---
def calculate_overall_confidence(llm_analysis_json: dict, conflict_analysis_json: dict, current_source_credibility: float) -> float:
    shannon_entropy = llm_analysis_json.get("analise_quantitativa", {}).get("shannon_relative_entropy", 0.0)
    relevance_score = llm_analysis_json.get("analise_entidades", {}).get("relevancia_mercado_financeiro", 0.0)
    
    internal_confidence_score = conflict_analysis_json.get("confidence_score", 0) / 100.0 

    overall_score = current_source_credibility * shannon_entropy * relevance_score * internal_confidence_score * 100
    return min(100, max(0, overall_score))

async def reanalyze_article(article_data: dict):
    article_id = article_data.get('news_article_id')
    text = article_data.get('article_text_content') # Esta é a string de texto
    source_credibility = article_data.get('source_credibility', 0.5)
    news_source_url = article_data.get('news_source_url', 'N/A')

    if not text:
        settings.logger.warning(f"Artigo {article_id} não possui conteúdo de texto para reanálise. Pulando.")
        return {"id": article_id, "status": "skipped_no_content"}

    settings.logger.info(f"Reanalisando artigo {article_id} (fonte: {news_source_url}, credibilidade: {source_credibility})...")
    
    try:
        # <<< AQUI ESTÁ A CORREÇÃO: ENCAPSULAR O TEXTO EM UM Content OBJECT >>>
        message_to_manager_agent = Content(role='user', parts=[Part(text=text)])
        
        response_event = await run_agent_and_get_final_response(
            AgenteGerenciadorAnalise_ADK,
            message_to_manager_agent, # Passa o objeto Content criado
            f"reanalysis_{article_id}"
        )
        
        parsed_agent_response = parse_llm_json_response(response_event)
        
        if not parsed_agent_response or "llm_analysis_output" not in parsed_agent_response or "conflict_analysis_output" not in parsed_agent_response or "final_processing_status" not in parsed_agent_response:
            raise ValueError("Resposta de análise inválida ou incompleta do Agente Gerenciador (não contém os dois JSONs e/ou status esperados).")

        llm_analysis_output = parsed_agent_response["llm_analysis_output"]
        conflict_analysis_output = parsed_agent_response["conflict_analysis_output"]
        final_processing_status = parsed_agent_response["final_processing_status"] 

        overall_confidence_score = calculate_overall_confidence(llm_analysis_output, conflict_analysis_output, source_credibility)

        data_to_persist = {
            "llm_analysis_output": llm_analysis_output,
            "conflict_analysis_output": conflict_analysis_output,
            "source_credibility": source_credibility,
            "overall_confidence_score": overall_confidence_score,
            "processing_status": final_processing_status
        }

        update_article_with_analysis(article_id, data_to_persist)
        settings.logger.info(f"Artigo {article_id} reanalisado e atualizado com sucesso. Novo overall_confidence_score: {overall_confidence_score:.2f}, Status: {final_processing_status}")
        return {"id": article_id, "status": final_processing_status, "new_confidence": overall_confidence_score}

    except Exception as e:
        settings.logger.error(f"Erro ao reanalisar o artigo {article_id}: {e}\n{traceback.format_exc()}")
        return {"id": article_id, "status": "reanalysis_failed", "error": str(e)}


async def main():
    settings.logger.info("--- INICIANDO SCRIPT DE REANÁLISE DE ARTIGOS COM BAIXA CONFIANÇA ---")
    
    total_processed_count = 0
    total_reanalyzed_success = 0
    total_reanalyzed_failed = 0
    
    current_batch_number = 1 

    while True:
        articles_to_process_objs = []
        with get_db_session() as session:
            articles_to_process_objs = (
                session.query(NewsArticle)
                .options(joinedload(NewsArticle.news_source)) 
                .filter(
                    NewsArticle.processing_status == 'analysis_complete', # Apenas artigos que já foram analisados
                    NewsArticle.llm_analysis_json.isnot(None), # Que tenham um JSON de análise principal
                    NewsArticle.conflict_analysis_json.isnot(None), # Que tenham um JSON de conflito (com score)
                    # AQUI ESTÁ A CORREÇÃO MAIS FIEL À SUA QUERY MANUAL
                    # Seleciona artigos cujo confidence_score no conflict_analysis_json é < REANALYSIS_THRESHOLD
                    NewsArticle.conflict_analysis_json.op('->>')('confidence_score').cast(Float) < REANALYSIS_THRESHOLD
                )
                .limit(BATCH_SIZE)
                .all()
            )
            
        if not articles_to_process_objs:
            settings.logger.info(f"Fim dos artigos. Nenhum novo artigo encontrado para reanálise. Processo concluído após {current_batch_number - 1} batches.")
            break 

        settings.logger.info(f"--- Processando Batch {current_batch_number} ---")
        # Log de artigos encontrados para este batch
        articles_in_batch_ids = [art.news_article_id for art in articles_to_process_objs]
        settings.logger.info(f"Artigos encontrados para este batch ({len(articles_in_batch_ids)} IDs): {articles_in_batch_ids}")
        
        tasks = []
        for article_obj in articles_to_process_objs: # Itera sobre os objetos, não IDs simples
            # Mapeia o objeto SQLAlchemy para o dicionário esperado pela função reanalyze_article
            source_credibility = article_obj.news_source.base_credibility_score if article_obj.news_source else 0.5
            news_source_url = article_obj.news_source.url_base if article_obj.news_source and article_obj.news_source.url_base else article_obj.article_link
            
            article_dict = {
                "news_article_id": article_obj.news_article_id,
                "article_text_content": article_obj.article_text_content, 
                "source_credibility": source_credibility,
                "news_source_url": news_source_url,
            }
            tasks.append(reanalyze_article(article_dict))
            
            await asyncio.sleep(SLEEP_BETWEEN_ARTICLES_SECONDS)

        results = await asyncio.gather(*tasks)
        
        for result in results:
            total_processed_count += 1
            if result.get("status") in ['analysis_complete', 'analysis_rejected']: # Sucesso na reanálise, mesmo se rejeitado
                total_reanalyzed_success += 1
            else:
                total_reanalyzed_failed += 1
                settings.logger.error(f"Artigo {result['id']} falhou na reanálise. Status: {result.get('status')}. Erro: {result.get('error', 'N/A')}")

        settings.logger.info(f"Resumo do Batch {current_batch_number}: Processados={len(results)} | Reanalisados (sucesso)={len([r for r in results if r.get('status') in ['analysis_complete', 'analysis_rejected']])} | Falhas={len([r for r in results if r.get('status') not in ['analysis_complete', 'analysis_rejected']])}")
        
        current_batch_number += 1
        await asyncio.sleep(SLEEP_BETWEEN_BATCHES_SECONDS) 

    settings.logger.info(f"--- SCRIPT DE REANÁLISE CONCLUÍDO ---")
    settings.logger.info(f"RESUMO FINAL: Total de artigos processados: {total_processed_count}.")
    settings.logger.info(f"Total de artigos reanalisados com sucesso: {total_reanalyzed_success}.")
    settings.logger.info(f"Total de artigos que falharam na reanálise: {total_reanalyzed_failed}.")

if __name__ == "__main__":
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    asyncio.run(main())