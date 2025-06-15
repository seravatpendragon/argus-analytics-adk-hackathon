import asyncio
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from typing import Optional

async def run_agent_and_get_final_response(agent, user_prompt: str, user_id_prefix: str = "user") -> Optional[str]:
    """
    Executa um agente com um prompt e retorna apenas a string de texto da resposta final.
    Lida com a criação de runner e sessão internamente.
    """
    runner = Runner(agent=agent, app_name=f"app_{agent.name}", session_service=InMemorySessionService())
    session_id = f"session_{user_id_prefix}_{asyncio.get_running_loop().time()}"

    await runner.session_service.create_session(
        app_name=runner.app_name, user_id=user_id_prefix, session_id=session_id
    )

    message = Content(role='user', parts=[Part(text=user_prompt)])

    final_response = None
    async for event in runner.run_async(new_message=message, user_id=user_id_prefix, session_id=session_id):
        if event.is_final_response() and event.content and event.content.parts:
            final_response = event.content.parts[0].text

    return final_response