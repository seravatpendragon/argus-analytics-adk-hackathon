import os
import sys
import json
import asyncio
from pathlib import Path

# Bloco de import padrão
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())

from config import settings
from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.genai.types import Content, Part
from src.agents.agent_utils import run_agent_and_get_final_response
from src.utils.parser_utils import parse_llm_json_response

# Importe TODOS os sub-agentes especialistas que serão orquestrados
from src.agents.analistas.sub_agentes_analise.sub_agente_quantitativo_adk.agent import SubAgenteQuantitativo_ADK
from src.agents.analistas.sub_agentes_analise.sub_agente_resumo_adk.agent import SubAgenteResumo_ADK
from src.agents.analistas.sub_agentes_analise.sub_agente_sentimento_adk.agent import SubAgenteSentimento_ADK
from src.agents.analistas.sub_agentes_analise.sub_agente_identificador_entidade_adk.agent import SubAgenteIdentificadorEntidades_ADK
from src.agents.analistas.sub_agentes_analise.sub_agente_stakeholders_adk.agent import SubAgenteStakeholders_ADK
from src.agents.analistas.sub_agentes_analise.sub_agente_impacto_maslow_adk.agent import SubAgenteImpactoMaslow_ADK

class AgenteGerenciadorAnalise(BaseAgent):
    """
    Um agente procedural que orquestra uma equipe de sub-agentes de análise
    em um fluxo de enriquecimento de duas etapas para máxima eficiência de custo.
    """
    def __init__(self, name: str = "agente_gerenciador_analise_v2", description: str = "Gerente que orquestra uma equipe de sub-agentes para analisar o conteúdo de um artigo."):
        super().__init__(name=name, description=description)

    async def _run_async_impl(self, context):
        """
        Executa a lógica procedural da "linha de montagem de inteligência".
        """
        text_to_analyze = context.user_content.parts[0].text
        yield Event(author=self.name, content=Content(parts=[Part(text="Iniciando análise 360° com fluxo otimizado...")]))

        # --- ETAPA 1: Análise Primária em Paralelo (usando texto completo) ---
        settings.logger.info("Gerente: Iniciando Etapa 1 (Quant, Entidades, Resumo).")
        tasks_etapa1 = [
            run_agent_and_get_final_response(SubAgenteQuantitativo_ADK, text_to_analyze, "quant"),
            run_agent_and_get_final_response(SubAgenteIdentificadorEntidades_ADK, text_to_analyze, "entid"),
            run_agent_and_get_final_response(SubAgenteResumo_ADK, text_to_analyze, "resumo")
        ]
        results1_raw = await asyncio.gather(*tasks_etapa1, return_exceptions=True)
        
        quant_res = parse_llm_json_response(results1_raw[0]) or {}
        entidades_res = parse_llm_json_response(results1_raw[1]) or {}
        resumo_res = parse_llm_json_response(results1_raw[2]) or {}
        
        yield Event(author=self.name, content=Content(parts=[Part(text="Etapa 1 concluída. Preparando para Etapa 2.")]))

        # --- ETAPA 2: Análise de Contexto em Paralelo (usando dados da Etapa 1 para otimização) ---
        settings.logger.info("Gerente: Iniciando Etapa 2 (Sentimento, Stakeholders, Maslow) com texto otimizado.")
        
        texto_otimizado_para_etapa2 = json.dumps({
            "resumo": resumo_res.get("summary", ""),
            "entidades_identificadas": entidades_res.get("entidades_identificadas", []),
            "contexto_dominante": entidades_res.get("contexto_dominante", "")
        })

        tasks_etapa2 = [
            run_agent_and_get_final_response(SubAgenteSentimento_ADK, texto_otimizado_para_etapa2, "sentim"),
            run_agent_and_get_final_response(SubAgenteStakeholders_ADK, texto_otimizado_para_etapa2, "stake"),
            run_agent_and_get_final_response(SubAgenteImpactoMaslow_ADK, texto_otimizado_para_etapa2, "maslow")
        ]
        results2_raw = await asyncio.gather(*tasks_etapa2, return_exceptions=True)

        sentimento_res = parse_llm_json_response(results2_raw[0]) or {}
        stakeholders_res = parse_llm_json_response(results2_raw[1]) or {}
        maslow_res = parse_llm_json_response(results2_raw[2]) or {}

        yield Event(author=self.name, content=Content(parts=[Part(text="Etapa 2 concluída. Consolidando resultados.")]))

        # --- ETAPA 3: Consolidação Final em Python ---
        final_analysis = {
            "analise_quantitativa": quant_res,
            "analise_resumo": resumo_res,
            "analise_entidades": entidades_res,
            "analise_sentimento": sentimento_res,
            "analise_stakeholders": stakeholders_res,
            "analise_impacto_maslow": maslow_res
        }
        
        yield Event(author=self.name, content=Content(parts=[Part(text=json.dumps(final_analysis, ensure_ascii=False))]))

AgenteGerenciadorAnalise_ADK = AgenteGerenciadorAnalise()
