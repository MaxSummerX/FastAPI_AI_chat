from fastapi import Depends
from mem0 import AsyncMemory
from sqlalchemy.ext.asyncio import AsyncSession

from app.depends.llm_depends import get_base_llm
from app.depends.mem0_depends import get_memory
from app.infrastructure.database.dependencies import get_db
from app.llms.openai import AsyncOpenAILLM
from app.services.message_service.service import MessageService


async def get_message_service(
    memory: AsyncMemory = Depends(get_memory),
    db: AsyncSession = Depends(get_db),
    llm_instance: AsyncOpenAILLM = Depends(get_base_llm),
) -> MessageService:
    return MessageService(memory=memory, db=db, llm=llm_instance)
