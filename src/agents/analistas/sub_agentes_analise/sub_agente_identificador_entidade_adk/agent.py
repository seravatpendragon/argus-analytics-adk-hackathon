import os
import sys
from pathlib import Path
import asyncio
import json

# Bloco de import padrão
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
except NameError:
    PROJECT_ROOT = Path(os.getcwd())

from config import settings
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from . import prompt as agent_prompt

# --- Definição do Agente ---
# Usando o perfil "analista_rapido" para otimizar custo e velocidade
profile = settings.AGENT_PROFILES.get("analista_rapido")

SubAgenteIdentificadorEntidades_ADK = LlmAgent(
    name="sub_agente_identificador_entidades",
    model=profile.get("model_name"),
    generate_content_config=profile.get("generate_content_config"),
    planner=profile.get("planner"),
    instruction=agent_prompt.PROMPT,
    description="Agente especialista que identifica empresas, organizações e pessoas em um texto e associa tickers de ações quando aplicável."
)

settings.logger.info(f"Agente '{SubAgenteIdentificadorEntidades_ADK.name}' carregado.")

# --- Bloco de Teste Standalone ---
if __name__ == '__main__':
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
    
    async def run_test():
        runner = Runner(agent=SubAgenteIdentificadorEntidades_ADK, app_name="test_app_entidades", session_service=InMemorySessionService())
        user_id, session_id = "test_user_entid", "test_session_entid"
        
        await runner.session_service.create_session(
            app_name=runner.app_name, user_id=user_id, session_id=session_id
        )
        
        texto_exemplo = (
            "As ações da Petrobras fecharam o pregão desta sexta-feira (13) em alta de 2,46%. O avanço veio após Israel lançar ataques contra o Irã, o que provocou um salto do preço do petróleo no mercado internacional e elevou os temores de interrupção no fornecimento global. Os preços do petróleo avançaram mais de 8% na sessão. ▶️ O barril tipo Brent (referência global) fechou com uma alta de 8,28% — um acréscimo de cerca de US$ 5,74 —, cotado a US$ 75,10. Mais cedo, chegou a US$ 78,50, o maior valor desde 27 de janeiro. ▶️ O petróleo WTI (referência nos EUA) fechou com um avanço de 8,69% — um acréscimo de US$ 5,91— e era negociado a US$ 73,95. Ele também atingiu uma máxima de US$ 77,62, o maior preço desde 21 de janeiro. Os ganhos desta sexta-feira estiveram entre os maiores movimentos intradiários (que acontecem no mesmo dia) para ambos os contratos desde 2022, quando a invasão da Ucrânia pela Rússia provocou uma disparada nos preços da energia. Nesta sexta, o diretor-executivo da Agência Internacional de Energia, Fatih Birol, publicou no X que está 'monitorando ativamente o impacto dos confrontos entre Israel e o Irã nos mercados de petróleo' e destacou que 'o sistema de segurança petrolífera da AIE tem mais de 1,2 bilhão de barris de estoques de emergência'. No entanto, o secretário-geral da Organização dos Países Exportadores de Petróleo (OPEP) criticou a declaração, dizendo que ela 'dispara alarmes falsos e projeta uma sensação de medo no mercado, ao repetir a necessidade desnecessária de potencialmente usar estoques de emergência de petróleo'. 'Avaliações semelhantes feitas em casos anteriores, mais recentemente em 2022, contribuíram para uma maior volatilidade do mercado e levaram a liberações prematuras de estoques que, em última análise, se mostraram desnecessárias', afirmou Haitham Al Ghais. A Companhia Nacional Iraniana de Refino e Distribuição de Petróleo informou que suas instalações de refino e armazenamento não foram danificadas e seguem operando normalmente. Por que os ataques afetam os preços do petróleo? Israel afirmou ter atacado instalações nucleares, fábricas de mísseis balísticos e comandantes militares iranianos, no início de uma operação que, segundo o governo, será prolongada para impedir que Teerã desenvolva uma arma nuclear. O Irã prometeu uma resposta severa. O presidente dos EUA, Donald Trump, pediu que o Irã aceite um acordo sobre seu programa nuclear, a fim de evitar 'os próximos ataques já planejados'. A Companhia Nacional Iraniana de Refino e Distribuição de Petróleo informou que suas instalações de refino e armazenamento não foram danificadas e seguem operando normalmente. Mas a principal preocupação é se os recentes acontecimentos afetarão o Estreito de Ormuz, por onde transita cerca de um quinto do consumo global de petróleo. Essa importante hidrovia já vinha sendo considerada vulnerável devido à crescente instabilidade regional, mas até o momento não foi afetada. O fluxo de petróleo na região também segue inalterado. No pior cenário, analistas do JPMorgan afirmaram na quinta-feira que o fechamento do estreito ou uma retaliação por parte dos principais produtores de petróleo da região poderia elevar os preços para a faixa de US$ 120 a US$ 130 por barril — quase o dobro da previsão atual. O aumento de US$ 10 por barril nos últimos três dias ainda não reflete qualquer queda na produção de petróleo iraniana, tampouco uma escalada que envolva interrupções no fluxo de energia pelo Estreito de Ormuz, afirmou o analista do Barclays, Amarpreet Singh, em nota. 'A questão principal agora é se essa alta do petróleo durará mais do que o fim de semana ou uma semana. Nosso sinal é que há uma probabilidade menor de uma guerra total, e a alta do preço do petróleo provavelmente encontrará resistência', disse Janiv Shah, analista da Rystad."
        )
        
        message = Content(role='user', parts=[Part(text=texto_exemplo)])
        
        print(f"\n--- ENVIANDO TEXTO PARA O AGENTE IDENTIFICADOR DE ENTIDADES ---")
        async for event in runner.run_async(new_message=message, user_id=user_id, session_id=session_id):
            if event.is_final_response():
                print("\n--- RESPOSTA FINAL (JSON de entidades) ---")
                try:
                    final_json = json.loads(event.content.parts[0].text)
                    print(json.dumps(final_json, indent=2, ensure_ascii=False))
                except json.JSONDecodeError:
                    print(event.content.parts[0].text)

    asyncio.run(run_test())