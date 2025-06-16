import os
import sys
from pathlib import Path
import asyncio
import json


# Bloco de import padrão...
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())


from config import settings
from google.adk.agents import LlmAgent
from google.adk.tools import agent_tool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

# Importe os sub-agentes que serão as ferramentas
from src.agents.analistas.sub_agentes_analise.sub_agente_quantitativo_adk.agent import SubAgenteQuantitativo_ADK
from src.agents.analistas.sub_agentes_analise.sub_agente_resumo_adk.agent import SubAgenteResumo_ADK
from src.agents.analistas.sub_agentes_analise.sub_agente_sentimento_adk.agent import SubAgenteSentimento_ADK
from src.agents.analistas.sub_agentes_analise.sub_agente_identificador_entidade_adk.agent import SubAgenteIdentificadorEntidades_ADK
from src.agents.analistas.sub_agentes_analise.sub_agente_impacto_maslow_adk.agent import SubAgenteImpactoMaslow_ADK
from src.agents.analistas.sub_agentes_analise.sub_agente_stakeholders_adk.agent import SubAgenteStakeholders_ADK
from . import prompt as agent_prompt

# --- Definição do Agente Gerente ---
profile = settings.AGENT_PROFILES.get("orquestrador")

lista_de_ferramentas = [
    agent_tool.AgentTool(agent=SubAgenteQuantitativo_ADK),
    agent_tool.AgentTool(agent=SubAgenteResumo_ADK),
    agent_tool.AgentTool(agent=SubAgenteSentimento_ADK),
    agent_tool.AgentTool(agent=SubAgenteIdentificadorEntidades_ADK),
    agent_tool.AgentTool(agent=SubAgenteStakeholders_ADK), 
    agent_tool.AgentTool(agent=SubAgenteImpactoMaslow_ADK)
]

AgenteGerenciadorAnalise_ADK = LlmAgent(
    name="agente_orquestrador_análise",
    model=profile.get("model_name"),
    generate_content_config=profile.get("generate_content_config"),
    instruction=agent_prompt.PROMPT,
    description="Agente inteligente que analisa um pedido e aciona os agentes coletores corretos em paralelo.",
    tools=lista_de_ferramentas,
    
)

settings.logger.info(f"Agente '{AgenteGerenciadorAnalise_ADK.name}' carregado com {len(AgenteGerenciadorAnalise_ADK.tools)} sub-agentes-ferramenta.")

# --- Bloco de Teste Standalone ---
if __name__ == '__main__':
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    
    async def run_test():
        runner = Runner(agent=AgenteGerenciadorAnalise_ADK, app_name="test_app_gerente_analise", session_service=InMemorySessionService())
        user_id, session_id = "test_user_gerente", "test_session_gerente"
        
        await runner.session_service.create_session(
            app_name=runner.app_name, user_id=user_id, session_id=session_id
        )
        
        # Texto de exemplo para o teste completo
        texto_exemplo = (
            "As ações da Petrobras fecharam o pregão em alta de 2,46%. O avanço veio após Israel lançar ataques contra o Irã, o que provocou um salto do preço do petróleo. "
            "A AIE está monitorando os estoques, mas a OPEP criticou a declaração, afirmando que gera volatilidade desnecessária."
        )
        
        message = Content(role='user', parts=[Part(text=texto_exemplo)])
        
        print(f"\n--- ENVIANDO TEXTO PARA O GERENTE DE ANÁLISE ---")
        async for event in runner.run_async(new_message=message, user_id=user_id, session_id=session_id):
            if event.is_final_response():
                print("\n--- RESPOSTA FINAL (JSON CONSOLIDADO) ---")
                try:
                    final_json = json.loads(event.content.parts[0].text)
                    print(json.dumps(final_json, indent=2, ensure_ascii=False))
                except json.JSONDecodeError:
                    print(event.content.parts[0].text)

    asyncio.run(run_test())