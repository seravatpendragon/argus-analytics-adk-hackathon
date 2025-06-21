# src/agents/agente_gerenciador_analise_llm_adk/agent.py (Versão Corrigida para Separar JSONs)

import os
import sys
import json
import asyncio
import traceback
from pathlib import Path
from typing import Optional

# Bloco de import padrão
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())

from config import settings
from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.genai.types import Content, Part
from src.agents.agent_utils import run_agent_and_get_final_response
from src.utils.parser_utils import parse_llm_json_response
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner

# Importe TODOS os sub-agentes especialistas
from src.agents.analistas.sub_agentes_analise.sub_agente_quantitativo_adk.agent import SubAgenteQuantitativo_ADK
from src.agents.analistas.sub_agentes_analise.sub_agente_resumo_adk.agent import SubAgenteResumo_ADK
from src.agents.analistas.sub_agentes_analise.sub_agente_sentimento_adk.agent import SubAgenteSentimento_ADK
from src.agents.analistas.sub_agentes_analise.sub_agente_identificador_entidade_adk.agent import SubAgenteIdentificadorEntidades_ADK
from src.agents.analistas.sub_agentes_analise.sub_agente_stakeholders_adk.agent import SubAgenteStakeholders_ADK
from src.agents.analistas.sub_agentes_analise.sub_agente_impacto_maslow_adk.agent import SubAgenteImpactoMaslow_ADK

# Importar a classe ConflictDetector
from src.data_processing.conflict_detector import ConflictDetector

# Importar o AgenteAuditorQualidade_ADK
from src.agents.auditores.agente_auditor_qualidade_adk.agent import AgenteAuditorQualidade_ADK


class AgenteGerenciadorAnalise(BaseAgent):
    """
    Um agente procedural que orquestra uma equipe de sub-agentes de análise
    em um fluxo de enriquecimento de duas etapas para máxima eficiência de custo e robustez.
    Inclui uma etapa de auditoria de qualidade, retornando dois JSONs distintos:
    um para a análise principal e outro para os resultados da auditoria de conflitos.
    """
    auditor_agent: Optional[BaseAgent] = None 

    def __init__(self, name: str = "agente_gerenciador_analise_v2", description: str = "Gerente que orquestra uma equipe de sub-agentes para analisar o conteúdo de um artigo e garante sua qualidade."):
        super().__init__(name=name, description=description)
        self.auditor_agent = AgenteAuditorQualidade_ADK 

    async def _run_async_impl(self, context):
        # A entrada para o Gerenciador é o texto puro do artigo
        text_to_analyze = context.user_content.parts[0].text
        
        yield Event(author=self.name, content=Content(parts=[Part(text="Iniciando análise 360° com fluxo otimizado e robusto...")]))

        # --- ETAPA 1: Análise Primária em Paralelo ---
        settings.logger.info("Gerente: Iniciando Etapa 1 (Quant, Entidades, Resumo).")
        
        # <<< CORREÇÃO AQUI: Criar um Content object para CADA chamada de sub-agente da Etapa 1 >>>
        message_for_sub_agents_etapa1 = Content(role='user', parts=[Part(text=text_to_analyze)])

        tasks_etapa1 = [
            run_agent_and_get_final_response(SubAgenteQuantitativo_ADK, message_for_sub_agents_etapa1, "analise_quantitativa"),
            run_agent_and_get_final_response(SubAgenteIdentificadorEntidades_ADK, message_for_sub_agents_etapa1, "analise_entidades"),
            run_agent_and_get_final_response(SubAgenteResumo_ADK, message_for_sub_agents_etapa1, "analise_resumo")
        ]
        results1_raw = await asyncio.gather(*tasks_etapa1, return_exceptions=True)
        
        # Função auxiliar para processar resultados e capturar exceções (já existente)
        def process_result(result, agent_name):
            if isinstance(result, Exception):
                error_msg = f"Erro no sub-agente '{agent_name}': {result.__class__.__name__} - {result}"
                settings.logger.error(f"{error_msg}\n{traceback.format_exc()}")
                return {"erro": error_msg}
            
            raw_response_text = result # 'result' aqui é o texto bruto retornado por run_agent_and_get_final_response

            # <<< ADICIONAR ESTA LINHA DE LOG >>>
            settings.logger.info(f"Sub-agente '{agent_name}' respondeu (texto bruto antes do parse): {raw_response_text[:500]}...") # Loga os primeiros 500 caracteres

            parsed_json = parse_llm_json_response(raw_response_text) # Passa o texto bruto para parser
            if not parsed_json:
                settings.logger.warning(f"Resposta inválida ou vazia do agente '{agent_name}'.")
                return {"erro": f"Resposta inválida ou vazia do agente '{agent_name}'"}
            return parsed_json

        quant_res = process_result(results1_raw[0], "Quantitativo")
        entidades_res = process_result(results1_raw[1], "Entidades")
        resumo_res = process_result(results1_raw[2], "Resumo")
        
        yield Event(author=self.name, content=Content(parts=[Part(text="Etapa 1 concluída. Verificando integridade para a Etapa 2.")]))

        # --- ETAPA 2: Análise de Contexto em Paralelo (Condicional) ---
        if "erro" in resumo_res or "erro" in entidades_res:
            settings.logger.warning("Gerente: Pulando Etapa 2 devido a falhas na Etapa 1 (resumo ou entidades).")
            sentimento_res = {"erro": "Pulado devido à falha na geração do resumo ou entidades."}
            stakeholders_res = {"erro": "Pulado devido à falha na geração do resumo ou entidades."}
            maslow_res = {"erro": "Pulado devido à falha na geração do resumo ou entidades."}
        else:
            settings.logger.info("Gerente: Iniciando Etapa 2 (Sentimento, Stakeholders, Maslow) com texto otimizado.")
            
            summary_text = resumo_res.get("summary", "")
            identified_entities = entidades_res.get("entidades_identificadas", [])
            dominant_context = entidades_res.get("foco_principal_sugerido", "")

            texto_otimizado_para_etapa2 = json.dumps({
                "resumo": summary_text,
                "entidades_identificadas": identified_entities,
                "contexto_dominante": dominant_context
            }, ensure_ascii=False)

            # <<< CORREÇÃO AQUI: Criar um Content object para cada chamada de sub-agente da Etapa 2 >>>
            message_for_sub_agents_etapa2 = Content(role='user', parts=[Part(text=texto_otimizado_para_etapa2)])

            tasks_etapa2 = [
                run_agent_and_get_final_response(SubAgenteSentimento_ADK, message_for_sub_agents_etapa2, "analise_sentimento"),
                run_agent_and_get_final_response(SubAgenteStakeholders_ADK, message_for_sub_agents_etapa2, "analise_stakeholders"),
                run_agent_and_get_final_response(SubAgenteImpactoMaslow_ADK, message_for_sub_agents_etapa2, "analise_impacto_maslow")
            ]
            results2_raw = await asyncio.gather(*tasks_etapa2, return_exceptions=True)

            sentimento_res = process_result(results2_raw[0], "Sentimento")
            stakeholders_res = process_result(results2_raw[1], "Stakeholders")
            maslow_res = process_result(results2_raw[2], "Maslow")

        yield Event(author=self.name, content=Content(parts=[Part(text="Etapa 2 concluída. Consolidando resultados iniciais.")]))

        # --- Consolidação da Análise Principal (llm_analysis_json) ---
        current_llm_analysis_json = {
            "analise_quantitativa": quant_res,
            "analise_resumo": resumo_res,
            "analise_entidades": entidades_res,
            "analise_sentimento": sentimento_res,
            "analise_stakeholders": stakeholders_res,
            "analise_impacto_maslow": maslow_res
        }
        
        # --- ETAPA 3: Ciclo de Auditoria de Qualidade (conflict_analysis_json) ---
        settings.logger.info("Gerente: Iniciando ciclo de auditoria de qualidade (consistência interna do JSON).")
        audit_needed = True
        audit_attempts = 0
        MAX_AUDIT_ATTEMPTS = 2 

        INTERNAL_CONFIDENCE_THRESHOLD_FOR_AUDITOR = 85 

        current_conflict_analysis_json = {} # Garante inicialização


        
        while audit_needed and audit_attempts < MAX_AUDIT_ATTEMPTS:
            audit_attempts += 1
            settings.logger.info(f"Gerente: Executando auditoria da análise (tentativa {audit_attempts}).")

            detector = ConflictDetector(analysis_data=current_llm_analysis_json)
            audit_result = detector.run() 

            current_conflict_analysis_json = audit_result 
            confidence_score = audit_result.get("confidence_score")
            conflicts = audit_result.get("conflicts", [])
            
            settings.logger.info(f"Auditoria (tentativa {audit_attempts}): Score={confidence_score}, Conflitos={conflicts}")

            # <<< AQUI É ONDE VOCÊ DEVE ADICIONAR A LÓGICA DE LOOP PARA FALHAS DE INTEGRIDADE >>>
            integrity_failures = [c for c in conflicts if "Falha de Integridade" in c]
            
            # Se houver falhas de integridade, o artigo é reenviado para reanálise LLM
            # O controle do MAX_LLM_ANALYSIS_RETRIES é feito no db_utils.py
            if integrity_failures:
                settings.logger.warning(f"Gerente: Detectada(s) Falha(s) de Integridade ({len(integrity_failures)} conflitos). Sinalizando para reanálise LLM.")
                audit_needed = False # Sinaliza para sair do loop de auditoria interna
                self._final_processing_status = 'pending_llm_analysis' # Define o status final para o pipeline principal
                current_conflict_analysis_json["final_status_auditor"] = "Reenviado para Reanálise LLM (Falha de Integridade)"
                current_conflict_analysis_json["audited_flag"] = False # Não foi auditado até o fim neste ciclo
                # Note: Não há 'return' aqui. O loop 'while' será encerrado por 'audit_needed=False',
                # e o código continuará para a construção do 'final_agent_output' após o loop.
            # <<< FIM DA LÓGICA DE LOOP PARA FALHAS DE INTEGRIDADE >>>

            # A partir daqui, a lógica original que decide chamar o Auditor ou aprovar.
            # Este 'elif' só será avaliado se a condição 'if integrity_failures:' for Falsa.
            elif confidence_score is not None and confidence_score < INTERNAL_CONFIDENCE_THRESHOLD_FOR_AUDITOR and conflicts:
                settings.logger.warning(f"Análise requer correção do Agente Auditor. Score: {confidence_score}. Conflitos: {conflicts}")
                
                prompt_para_auditor = (
                    f"--- CONFLITOS DETECTADOS ---\n"
                    f"{json.dumps(conflicts, indent=2, ensure_ascii=False)}\n\n"
                    f"--- JSON ORIGINAL PARA REVISÃO ---\n"
                    f"{json.dumps(current_llm_analysis_json, indent=2, ensure_ascii=False)}"
                )
                
                message_to_auditor = Content(role='user', parts=[Part(text=prompt_para_auditor)])
                
                settings.logger.info(f"Gerente: Chamando AgenteAuditorQualidade_ADK para correção do JSON.")
                
                try:
                    auditor_output_text = await run_agent_and_get_final_response(
                            self.auditor_agent, 
                            message_to_auditor, 
                            f"auditor_call_{audit_attempts}" 
                        )
                    
                    try:
                        auditor_response_json = json.loads(auditor_output_text.strip().removeprefix("```json").removesuffix("```"))
                        
                        corrected_analysis = auditor_response_json.get("corrected_analysis_json", {})
                        updated_audit = auditor_response_json.get("updated_audit_json", {})

                        auditor_decision_status = updated_audit.get("status_auditoria")
                        
                        if auditor_decision_status == "rejeitado":
                            settings.logger.error(f"Agente Auditor rejeitou a análise. Justificativa: {updated_audit.get('justificativa_auditoria', 'Sem justificativa.')}")
                            current_llm_analysis_json = current_llm_analysis_json # Mantém o original
                            current_conflict_analysis_json = updated_audit 
                            audit_needed = False 
                            self._final_processing_status = 'analysis_rejected' 
                        elif auditor_decision_status == "corrigido":
                            settings.logger.info("Agente Auditor retornou um JSON corrigido. Reavaliando...")
                            current_llm_analysis_json.update(corrected_analysis) 
                            current_conflict_analysis_json = updated_audit 
                            audit_needed = False 
                            self._final_processing_status = 'analysis_complete' 
                        else:
                            settings.logger.error(f"Agente Auditor retornou status de auditoria inesperado: {auditor_decision_status}. Presumindo falha.")
                            current_conflict_analysis_json = updated_audit 
                            self._final_processing_status = 'analysis_failed' 
                            audit_needed = False

                    except json.JSONDecodeError as e:
                        settings.logger.error(f"Agente Auditor retornou JSON inválido ou texto inesperado: {auditor_output_text}. Erro: {e}")
                        current_conflict_analysis_json["error_auditor_output"] = f"Agente Auditor retornou formato inválido: {auditor_output_text}"
                        self._final_processing_status = 'analysis_failed'
                        audit_needed = False
                except Exception as e:
                    settings.logger.error(f"Erro ao chamar AgenteAuditorQualidade_ADK: {e}\n{traceback.format_exc()}")
                    current_conflict_analysis_json["error_invocation"] = f"Falha na invocação do Auditor: {e}"
                    self._final_processing_status = 'analysis_failed'
                    audit_needed = False
            else: # Se confidence_score >= LIMIAR (aprovado) OU score baixo mas sem conflitos para LLM Auditor
                settings.logger.info("Análise aprovada pela auditoria de consistência interna ou sem conflitos para acionar LLM.")
                audit_needed = False 
                self._final_processing_status = 'analysis_complete' 

            if audit_needed and audit_attempts == MAX_AUDIT_ATTEMPTS:
                settings.logger.warning(f"Limite de tentativas de auditoria ({MAX_AUDIT_ATTEMPTS}) atingido. Análise final com score de consistência interna: {confidence_score}.")
                self._final_processing_status = 'analysis_failed' 
                current_conflict_analysis_json["final_status_auditor"] = f"Limite de tentativas atingido. Último score de consistência: {confidence_score}"


        final_processing_status = getattr(self, '_final_processing_status', 'analysis_failed') # Fallback
        
        final_agent_output = {
            "llm_analysis_output": current_llm_analysis_json, 
            "conflict_analysis_output": current_conflict_analysis_json,
            "final_processing_status": final_processing_status 
        }
        
        settings.logger.info(f"Agente Gerenciador: Retornando output final para artigo {context.user_content.parts[0].text[:50]}...: {json.dumps(final_agent_output, indent=2, ensure_ascii=False)}")


        final_analysis_content = Content(
            role='model',
            parts=[Part(text=json.dumps(final_agent_output, indent=2, ensure_ascii=False))]
        )
        yield Event(author=self.name, content=final_analysis_content)

# Instância única do AgenteGerenciadorAnalise para exportação
AgenteGerenciadorAnalise_ADK = AgenteGerenciadorAnalise()
if __name__ == '__main__':
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    
    async def run_test_orchestration():
        runner = Runner(agent=AgenteGerenciadorAnalise_ADK, app_name="test_argus_analytics_manager", session_service=InMemorySessionService())
        user_id, session_id = "test_user", "test_session_manager_only"
        await runner.session_service.create_session(app_name=runner.app_name, user_id=user_id, session_id=session_id)

        sample_article_text = (
            "A presidente da Petrobras, Magda Chambriard, disse na 4ª feira (18.jun.2025) que ainda é cedo para considerar mudanças no preço dos combustíveis, a petrobras hoje necessita de mais ajuda do exeterior, por temos problemas com a fila de refinaria com a atual greve de caminhoneiros no Brasil. Já com base no conflito entre Israel e Irã no Oriente Médio. A região é estratégica para produção global de petróleo e gás. “Esse cenário tem apenas 5 dias. É bem recente. A Petrobras não faz movimentos abruptos. Aumento ou redução nos preços de combustíveis são feitos a partir de movimentos delicados. Só nos movimentamos quando identificamos tendências. Não queremos trazer para o Brasil a instabilidade e a volatilidade do sistema de precificação intern... Leia mais no texto original: (https://www.poder360.com.br/poder-energia/e-cedo-para-avaliar-impacto-do-conflito-israel-ira-diz-petrobras/) © 2025 Todos os direitos são reservados ao Poder360, conforme a Lei nº 9.610/98. A publicação, redistribuição, transmissão e reescrita sem autorização prévia são proibidas."
        )
        
        initial_input_message = Content(
            role='user', 
            parts=[Part(text=sample_article_text)]
        )
        
        print("\n--- INICIANDO TESTE DO AGENTE GERENCIADOR DE ANÁLISE (APENAS TEXTO DE ENTRADA) ---")
        async for event in runner.run_async(new_message=initial_input_message, user_id=user_id, session_id=session_id):
            if event.is_final_response():
                print("\n--- RESPOSTA FINAL DO AGENTE GERENCIADOR (JSON DE ANÁLISE INTERNA) ---")
                try:
                    final_analysis = json.loads(event.content.parts[0].text)
                    print(json.dumps(final_analysis, indent=2, ensure_ascii=False))
                except json.JSONDecodeError:
                    print("Resposta final não é um JSON válido:")
                    print(event.content.parts[0].text)
    
    asyncio.run(run_test_orchestration())
