# src/agents/agent_utils.py (VERSÃO MAIS ROBUSTA DE run_agent_and_get_final_response)

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from config import settings
import asyncio 

async def run_agent_and_get_final_response(agent_instance, new_message: Content, session_id: str) -> str:
    """
    Executa um agente, espera por sua resposta final e retorna o texto dessa resposta.
    Consome todos os eventos intermediários.
    """
    user_id_prefix = "system_user" 
    runner = Runner(agent=agent_instance, app_name=agent_instance.name, session_service=InMemorySessionService())
    
    await runner.session_service.create_session(app_name=runner.app_name, user_id=user_id_prefix, session_id=session_id)

    settings.logger.info(f"Chamando agente '{agent_instance.name}' (sessão: {session_id})...")
    
    final_response_text = None 
    received_final_event = False # Flag para saber se recebemos o Evento final

    try:
        async for event in runner.run_async(new_message=new_message, user_id=user_id_prefix, session_id=session_id):
            # Log de eventos intermediários, se desejar
            # if event.content and event.content.parts and not event.is_final_response():
            #     settings.logger.info(f"  Evento Intermediário de '{event.author}': {event.content.parts[0].text[:100]}...")

            if event.is_final_response():
                received_final_event = True
                if event.content and event.content.parts:
                    final_response_text = event.content.parts[0].text
                    # Não quebra o loop aqui, o runner pode enviar outros eventos de finalização
                    # Apenas pegamos o texto da resposta final.
                    
        # Após o loop, verificamos se a resposta final foi capturada
        if not received_final_event or final_response_text is None:
            settings.logger.error(f"Agente '{agent_instance.name}' (sessão: {session_id}) não retornou uma resposta marcada como final ou seu conteúdo estava vazio.")
            raise ValueError("Agente não retornou resposta final esperada.")
        
        return final_response_text

    except Exception as e:
        settings.logger.error(f"Erro ao executar agente '{agent_instance.name}' (sessão: {session_id}): {e}", exc_info=True)
        raise