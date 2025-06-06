# src/agents/sub_agente_resumo_adk/agent.py

import os
import sys
from pathlib import Path
import json
import asyncio 
import logging 

# --- Configuração de Caminhos para Imports do Projeto ---
try:
    CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = CURRENT_SCRIPT_DIR.parent.parent.parent 
    if str(PROJECT_ROOT) not in sys.path:
        sys.sys.path.insert(0, str(PROJECT_ROOT))
    
    src_path = PROJECT_ROOT / "src"
    if str(src_path) not in sys.path:
        sys.sys.path.insert(0, str(src_path))

except Exception as e:
    print(f"ERRO CRÍTICO (pré-logger): Falha na configuração inicial do sys.path em {__file__}: {e}", file=sys.stderr)
    sys.exit(1)

# --- Importações de Módulos ---
try:
    from config import settings
    from google.adk.agents import Agent
    # from google.adk.tools import FunctionTool # Remova se não houver ferramentas neste agente
    from google.adk.sessions import InMemorySessionService 
    from google.adk.runners import Runner 
    from google.genai import types 

    from . import prompt as agente_prompt

except ImportError as e:
    # Logger fallback aqui, pois o logger principal pode não ter sido totalmente inicializado.
    print(f"ERRO CRÍTICO (ImportError em {Path(__file__).name}): {e}", file=sys.stderr)
    print(f"sys.path atual: {sys.path}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"ERRO INESPERADO durante imports iniciais em {Path(__file__).name}: {e}", file=sys.stderr)
    sys.exit(1)

# --- Definição do Agente (AGORA DENTRO DE UMA FUNÇÃO) ---
# O agente não será instanciado no top-level do módulo.
# Ele será criado apenas quando esta função for chamada.
def get_agent_instance():
    # Definição do Modelo LLM a ser usado por este agente 
    MODELO_LLM_AGENTE = "gemini-2.0-flash-001" 
    
    # Obtenha o logger localmente dentro da função de inicialização do agente.
    _local_logger = logging.getLogger(__name__) 
    _local_logger.info("Modelo LLM para o agente {}: {}".format(Path(__file__).name, MODELO_LLM_AGENTE))

    # Lista de ferramentas para este agente. Adapte conforme necessário.
    _agent_tools = [] # Por padrão, vazio.

    # Adapte o 'name', 'description' e 'instruction' para este agente.
    _agent_instance = Agent(
        name="sub_agente_resumo_adk_v1", # EX: "sub_agente_resumo_adk_v1"
        model=MODELO_LLM_AGENTE, 
        description=(
            "Sub-agente especializado em gerar um resumo conciso e estruturado de notícias financeiras."
        ),
        instruction=agente_prompt.PROMPT,
        tools=_agent_tools, # Use a lista de ferramentas definida
        # output_schema=... # Se o agente DEVE retornar JSON com um esquema específico
    )
    
    _local_logger.info("Definição do Agente {} carregada com sucesso em {}.".format(_agent_instance.name, Path(__file__).name))
    
    return _agent_instance

# A variável global que o script principal irá importar
# Esta linha AGORA armazena a instância do Agente retornada pela função
SubAgenteResumo_ADK = get_agent_instance()


# --- Bloco de Teste Standalone (para executar apenas este arquivo agent.py) ---
# Este bloco SÓ é executado se o arquivo for chamado diretamente (python agent.py).
if __name__ == '__main__':
    # Obtenha o logger para o teste standalone
    _main_logger = logging.getLogger(__name__)

    _main_logger.info(f"--- Teste Standalone da Definição e Fluxo Simulado do Agente: {SubAgenteResumo_ADK.name} ---")
    _main_logger.info(f"  Modelo Configurado: {SubAgenteResumo_ADK.model}") 

    async def run_mock_agent_test():
        session_service = InMemorySessionService()
        session_id = "mock_session_test"
        await session_service.create_session(app_name="mock_app", user_id="mock_user", session_id=session_id)
        
        mock_runner = Runner(
            agent=SubAgenteResumo_ADK,
            app_name="mock_app",
            session_service=session_service
        )

        # Exemplo de input (o mesmo formato que virá do run_llm_analysis_pipeline_test.py)
        # Lembre-se que o prompt foi ajustado para esperar "Contexto da Notícia" no texto
        text_content_with_context = """
        Contexto da Notícia: A notícia é predominantemente sobre: EMPRESA. A entidade/tema principal é 'Petrobras'. O identificador padronizado é 'PETR4-SA'.

        Texto Original para Análise:
        A Petrobras (PETR4) anunciou hoje a descoberta de um novo campo de petróleo na Bacia de Campos, com potencial estimado de 500 milhões de barris. A empresa prevê que a produção neste novo campo comece em 2028, contribuindo significativamente para as metas de produção de longo prazo. Apesar da notícia positiva, as ações caíram levemente devido a uma preocupação macroeconômica global.
        """
        llm_input_content = types.Content(role='user', parts=[types.Part(text=text_content_with_context)])
        
        _main_logger.info(f"\nSimulando chamada ao agente {SubAgenteResumo_ADK.name}...")
        events = mock_runner.run_async(user_id="mock_user", session_id=session_id, new_message=llm_input_content)
        
        async for event in events:
            if event.is_final_response() and event.content and event.content.parts and event.content.parts[0].text:
                generated_output_str = event.content.parts[0].text.strip()
                _main_logger.info(f"  JSON de saída gerado pelo Agente:\n{generated_output_str}")
                try:
                    parsed_output = json.loads(generated_output_str)
                    _main_logger.info(f"  Saída JSON PARSEADA com sucesso: {parsed_output}")
                except json.JSONDecodeError as e:
                    _main_logger.error(f"  Erro ao parsear JSON de saída do agente: {e}. Conteúdo: {generated_output_str[:100]}...")
            elif hasattr(event, 'tool_code') and event.tool_code:
                _main_logger.warning(f"  Agente gerou tool_code inesperado: {event.tool_code[:100]}...")
            elif hasattr(event, 'tool_response') and event.tool_response:
                _main_logger.info(f"  Agente recebeu resposta de ferramenta: {event.tool_response.name} - {event.tool_response.response}")

    try:
        asyncio.run(run_mock_agent_test())
    except RuntimeError as e:
        if "cannot run an event loop while another event loop is running" in str(e):
            _main_logger.warning("Detectado ambiente com loop de eventos já em execução (ex: Jupyter/Colab).")
        else:
            raise e
    except Exception as e:
        _main_logger.critical(f"Erro fatal durante o teste standalone do agente: {e}", exc_info=True)

    _main_logger.info(f"\n--- Fim do Teste Standalone do Agente {SubAgenteResumo_ADK.name} ---")