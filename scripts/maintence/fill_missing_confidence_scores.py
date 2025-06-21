# scripts/maintenance/fill_missing_confidence_scores.py (Atualizado com logging aprimorado)

import os
import sys
import asyncio
import time
import json
from pathlib import Path
from datetime import datetime
import traceback

# Adiciona o root do projeto ao path para permitir imports
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent 
    if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path.cwd()
    if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from src.database.db_utils import get_db_session
from src.database.create_db_tables import NewsArticle, NewsSource
from sqlalchemy.orm import joinedload
from src.data_processing.conflict_detector import ConflictDetector 

# --- CONFIGURAÇÕES DO SCRIPT ---
BATCH_SIZE = 100000 # Quantidade de artigos a processar por vez
SLEEP_BETWEEN_BATCHES_SECONDS = 5 # Pausa entre cada lote

# --- FUNÇÃO AUXILIAR PARA CALCULAR OVERALL CONFIDENCE ---
def calculate_overall_confidence(llm_analysis_json: dict, conflict_analysis_json: dict, current_source_credibility: float) -> float:
    shannon_entropy = llm_analysis_json.get("analise_quantitativa", {}).get("shannon_relative_entropy", 0.0)
    relevance_score = llm_analysis_json.get("analise_entidades", {}).get("relevancia_mercado_financeiro", 0.0)
    
    internal_confidence_score = conflict_analysis_json.get("confidence_score", 0) / 100.0 

    overall_score = current_source_credibility * shannon_entropy * relevance_score * internal_confidence_score * 100
    return min(100, max(0, overall_score))

async def fill_missing_scores_for_article(article_id: int):
    """
    Recarrega um artigo, garante que o source_credibility e conflict_analysis_json
    estejam preenchidos/recalculados, e recalcula o overall_confidence_score.
    """
    
    try:
        with get_db_session() as session: 
            article_obj = (
                session.query(NewsArticle)
                .options(joinedload(NewsArticle.news_source))
                .filter(NewsArticle.news_article_id == article_id)
                .first()
            )
            
            if not article_obj:
                settings.logger.error(f"Artigo com ID {article_id} não encontrado na sessão de preenchimento. Pode ter sido excluído.")
                return {"id": article_id, "status": "not_found"}

            source_credibility = article_obj.news_source.base_credibility_score if article_obj.news_source else 0.5
            
            llm_analysis_json_from_db = article_obj.llm_analysis_json
            conflict_analysis_json_from_db = article_obj.conflict_analysis_json

            if not llm_analysis_json_from_db:
                settings.logger.warning(f"Artigo {article_id} sem llm_analysis_json. Pulando preenchimento de scores.")
                return {"id": article_id, "status": "skipped_no_llm_json"}

            # Flag para saber se houve alguma alteração que justifique o commit
            changed = False

            # 1. Garantir que o source_credibility da coluna do artigo esteja preenchido
            if article_obj.source_credibility is None or article_obj.source_credibility != source_credibility: 
                article_obj.source_credibility = source_credibility
                settings.logger.info(f"Artigo {article_id}: Preenchido/Atualizado source_credibility com {source_credibility}.")
                changed = True

            # 2. Garantir que conflict_analysis_json tenha um confidence_score. Se não tiver, recalcular com ConflictDetector.
            current_conflict_json = conflict_analysis_json_from_db if conflict_analysis_json_from_db else {}
            
            if "confidence_score" not in current_conflict_json or current_conflict_json["confidence_score"] is None:
                settings.logger.info(f"Artigo {article_id}: confidence_score ausente em conflict_analysis_json. Recalculando com ConflictDetector.")
                try:
                    detector = ConflictDetector(llm_analysis_json_from_db)
                    audit_result = detector.run() 
                    current_conflict_json = audit_result 
                    settings.logger.info(f"Artigo {article_id}: Recalculado confidence_score para {current_conflict_json.get('confidence_score')}.")
                    changed = True
                except Exception as e:
                    settings.logger.warning(f"Artigo {article_id}: Falha ao recalcular confidence_score com ConflictDetector: {e}. Defaulting to 0.")
                    current_conflict_json["confidence_score"] = 0 
                    current_conflict_json["conflicts"] = current_conflict_json.get("conflicts", []) + ["Erro ao recalcular confiança interna durante preenchimento"]
                    current_conflict_json["audited_by"] = current_conflict_json.get("audited_by", "ConflictDetector_Fallback")
                    current_conflict_json["audit_timestamp"] = current_conflict_json.get("audit_timestamp", datetime.now().isoformat())
                    changed = True
            
            # Se o JSON de conflito na coluna do DB for diferente do que temos agora, atualiza
            if article_obj.conflict_analysis_json != current_conflict_json:
                article_obj.conflict_analysis_json = current_conflict_json
                changed = True

            # 3. Calcular e preencher overall_confidence_score
            new_overall_score = calculate_overall_confidence(llm_analysis_json_from_db, current_conflict_json, source_credibility)
            
            if abs((article_obj.overall_confidence_score if article_obj.overall_confidence_score is not None else -1) - new_overall_score) > 0.01:
                article_obj.overall_confidence_score = new_overall_score
                settings.logger.info(f"Artigo {article_id}: overall_confidence_score atualizado para {new_overall_score:.2f}.")
                changed = True
            
            if changed:
                session.add(article_obj)
                session.commit()
                return {"id": article_id, "status": "filled_scores", "overall_confidence": new_overall_score}
            else:
                settings.logger.info(f"Artigo {article_id}: Nenhum preenchimento ou recalculo necessário. Pulado.")
                return {"id": article_id, "status": "skipped_no_change"}

    except Exception as e:
        settings.logger.error(f"Erro ao preencher scores para o artigo {article_id}: {e}", exc_info=True)
        return {"id": article_id, "status": "fill_failed", "error": str(e)}

async def main():
    settings.logger.info("--- INICIANDO SCRIPT DE PREENCHIMENTO/RECALCULO DE SCORES E CONFIANÇA GERAL ---")
    
    total_processed_articles_overall = 0 
    total_updated_correctly_overall = 0 
    total_skipped_no_change_overall = 0
    total_failed_overall = 0 
    
    current_batch_number = 1 

    while True:
        articles_to_process_ids = []
        with get_db_session() as session_for_ids: 
            articles_to_process_objs = (
                session_for_ids.query(NewsArticle.news_article_id)
                .filter(
                    NewsArticle.processing_status == 'analysis_complete',
                    NewsArticle.llm_analysis_json.isnot(None) # Garante que já tem uma análise principal
                )
                .order_by(NewsArticle.news_article_id) # Opcional: Para processar em ordem de ID
                .limit(BATCH_SIZE)
                .all()
            )
            articles_to_process_ids = [art.news_article_id for art in articles_to_process_objs]

        if not articles_to_process_ids:
            settings.logger.info(f"Fim dos artigos. Nenhum novo artigo encontrado para preenchimento/recalculo de scores. Processo concluído após {current_batch_number - 1} batches.")
            break 

        settings.logger.info(f"--- Processando Batch {current_batch_number} ---")
        # Log de artigos encontrados para este batch
        settings.logger.info(f"Artigos encontrados para este batch ({len(articles_to_process_ids)} IDs): {articles_to_process_ids}")
        
        tasks = []
        for article_id in articles_to_process_ids:
            tasks.append(fill_missing_scores_for_article(article_id))
        
        results = await asyncio.gather(*tasks)
        
        processed_in_batch = 0
        updated_in_batch = 0
        skipped_in_batch = 0
        failed_in_batch = 0

        for result in results:
            processed_in_batch += 1
            if result.get("status") == "filled_scores":
                updated_in_batch += 1
                settings.logger.info(f"Artigo {result['id']} ATUALIZADO/RECALCULADO. Novo overall_confidence_score: {result.get('overall_confidence'):.2f}")
            elif result.get("status") == "skipped_no_change":
                skipped_in_batch += 1
                settings.logger.info(f"Artigo {result['id']} PULADO (sem mudanças).")
            else: # Covers "fill_failed", "not_found", "skipped_no_llm_json"
                failed_in_batch += 1
                settings.logger.error(f"Artigo {result['id']} FALHOU ou foi pulado (Motivo: {result.get('status')}). Detalhes: {result.get('error', result.get('message', 'N/A'))}")

        total_processed_articles_overall += processed_in_batch
        total_updated_correctly_overall += updated_in_batch
        total_skipped_no_change_overall += skipped_in_batch
        total_failed_overall += failed_in_batch

        settings.logger.info(f"Resumo do Batch {current_batch_number}: Processados={processed_in_batch} | Atualizados={updated_in_batch} | Pulados={skipped_in_batch} | Falhas={failed_in_batch}")
        
        current_batch_number += 1
        await asyncio.sleep(SLEEP_BETWEEN_BATCHES_SECONDS) 

    settings.logger.info(f"--- SCRIPT DE PREENCHIMENTO/RECALCULO CONCLUÍDO ---")
    settings.logger.info(f"RESUMO FINAL: Total de artigos processados: {total_processed_articles_overall}.")
    settings.logger.info(f"Total de artigos com scores recalculados/preenchidos: {total_updated_correctly_overall}.")
    settings.logger.info(f"Total de artigos pulados (sem mudanças): {total_skipped_no_change_overall}.")
    settings.logger.info(f"Total de artigos que falharam ou foram pulados (outros motivos): {total_failed_overall}.")
if __name__ == "__main__":
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    asyncio.run(main())