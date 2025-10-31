import json
import os
from collections.abc import AsyncGenerator
from uuid import UUID

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks
from mem0 import AsyncMemory
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.memory import custom_config
from app.models import Message as MessageModel


memory_local = AsyncMemory(config=custom_config)

load_dotenv()


async def stream_llm_response(
    message: str,
    username: str,
    conversation_id: UUID,
    history: list,
    background_tasks: BackgroundTasks,
    db: AsyncSession,
) -> AsyncGenerator[str]:
    """Стрим с сохранением через BackgroundTasks"""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
        "Content-Type": "application/json",
    }

    messages = history + [{"role": "user", "content": message}]
    payload = {
        "model": os.getenv("MODEL"),
        "messages": messages,
        "stream": True,
    }

    chunks = []  # Накапливаем chunks

    async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break

                    try:
                        data_obj = json.loads(data)
                        content = data_obj["choices"][0]["delta"].get("content")
                        if content:
                            chunks.append(content)
                            yield content  # Отправляем клиенту
                    except json.JSONDecodeError:
                        pass

    # После завершения стрима добавляем задачу сохранения
    full_response = "".join(chunks)
    background_tasks.add_task(save_message_to_db, db, conversation_id, full_response)

    # формируем сообщение для передачи его в mem0ai
    messages_for_mem0ai = [
        {"role": "assistant", "content": message},
        {"role": "user", "content": full_response},
    ]

    # Передаём сообщение на извлечение фактов в mem0ao
    background_tasks.add_task(memory_local.add, messages_for_mem0ai, user_id=username, run_id=str(conversation_id))


async def save_message_to_db(db: AsyncSession, conversation_id: UUID, content: str) -> None:
    """Сохранение сообщения в БД"""
    assistant_message = MessageModel(
        conversation_id=conversation_id, role="assistant", content=content, model=os.getenv("MODEL")
    )
    db.add(assistant_message)
    await db.commit()
