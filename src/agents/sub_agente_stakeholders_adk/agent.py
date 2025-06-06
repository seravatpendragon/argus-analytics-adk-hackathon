# src/agents/sub_agente_stakeholders_adk/agent.py

import os
import sys
from pathlib import Path
import json
from datetime import datetime
from typing import List
import logging

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent # Sobe 3 níveis
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

try:
    from config import settings
    from google.adk.agents import Agent
    from google.genai import types # Para configurar output_schema
    from pydantic import BaseModel, Field # Para definir o schema de saída
    
    # Importa o prompt local
    from . import prompt as agente_prompt

    # Fallback do logger se settings.logger não estiver disponível
    if not hasattr(settings, 'logger'):
        import logging
        log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
        logging.basicConfig(level=logging.INFO, format=log_format)
        settings.logger = logging.getLogger("sub_agente_stakeholders_adk_fb_logger")
        settings.logger.info("Logger fallback inicializado em agent.py.")
    settings.logger.info("Módulos do projeto e ADK importados com sucesso para SubAgenteStakeholders_ADK.")
except ImportError as e:
    settings.logger.error(f"Erro CRÍTICO em agent.py (SubAgenteStakeholders_ADK) ao importar módulos: {e}")
    settings.logger.error(f"PROJECT_ROOT calculado: {PROJECT_ROOT}")
    settings.logger.error(f"sys.path atual: {sys.path}")
    sys.exit(1)
except Exception as e:
    settings.logger.error(f"Erro INESPERADO durante imports iniciais em agent.py (SubAgenteStakeholders_ADK): {e}")
    sys.exit(1)

# --- Definição do Modelo LLM a ser usado por este agente ---
MODELO_LLM_AGENTE = "gemini-2.0-flash-001" 
settings.logger.info(f"Modelo LLM para SubAgenteStakeholders_ADK: {MODELO_LLM_AGENTE}")

# --- Definição do Schema de Saída para o LLM (para garantir JSON estruturado) ---
class StakeholdersOutput(BaseModel):
    stakeholders: List[str] = Field(description="Uma lista dos 1-3 stakeholders principais identificados (ex: 'Investidores Institucionais', 'Reguladores/Governo').")
    impacto_no_stakeholder_primario: str = Field(description="A natureza do impacto no stakeholder mais relevante ('Positivo', 'Negativo', 'Neutro' ou 'Misto').")
    justificativa_impacto_stakeholder: str = Field(description="Uma breve explicação (1-2 frases) do impacto no stakeholder primário, citando elementos da notícia.")

# --- Definição do Agente ---
SubAgenteStakeholders_ADK = Agent(
    name="sub_agente_stakeholders_adk_v1",
    model=MODELO_LLM_AGENTE,
    description=(
        "Sub-agente especializado em identificar os stakeholders principais mencionados ou afetados por um texto."
    ),
    instruction=agente_prompt.PROMPT,
    output_schema=StakeholdersOutput, # Garante que a saída do LLM seja um JSON conforme o schema
    output_key="stakeholders_analysis_result", # Salva o resultado no estado da sessão
)

if __name__ == '__main__':
    # Este bloco é para um teste muito básico da definição do agente e uma simulação
    # de como o agente usaria sua ferramenta, sem usar o ADK Runner.
    # Para testar um LlmAgent, você precisaria de um Runner e SessionService reais.
    # Este teste apenas verifica se o agente foi definido corretamente.
    
    settings.logger.info(f"--- Teste Standalone da Definição do Agente: {SubAgenteStakeholders_ADK.name} ---")
    settings.logger.info(f"  Modelo Configurado: {SubAgenteStakeholders_ADK.model}")
    settings.logger.info(f"  Schema de Saída Configurado: {SubAgenteStakeholders_ADK.output_schema.__name__}")
    settings.logger.info(f"  Output Key Configurado: {SubAgenteStakeholders_ADK.output_key}")

    settings.logger.info("\nEste teste standalone apenas verifica a definição do agente.")
    settings.logger.info("Para testar a funcionalidade real (chamada ao LLM), você precisaria de um ADK Runner e SessionService.")
    settings.logger.info("Isso será feito na fase de integração com o Agente Gerenciador de Análise LLM.")

    settings.logger.info("\n--- Fim do Teste Standalone do Sub-Agente de Stakeholders ---")