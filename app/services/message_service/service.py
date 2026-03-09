import asyncio
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from loguru import logger
from mem0 import AsyncMemory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.exceptions import LLMGenerationError, NotFoundError, PromptNotFoundError
from app.llms.openai import AsyncOpenAILLM
from app.llms.tools import (
    CREATE_DOCUMENT_TOOL,
    WEB_FETCH_TOOL,
    WEB_SEARCH_TOOL,
    make_create_file_tool,
    web_fetch,
    web_search,
)
from app.models import Conversation as ConversationModel
from app.models import Message as MessageModel
from app.models.prompts import Prompts as PromptModel
from app.prompts.prompts_base import START_PROMPT
from app.schemas.facts import FactSource
from app.schemas.messages import HistoryMessage


@dataclass
class StreamData:
    stream: AsyncIterator[str]
    result_awaitable: Awaitable[dict[str, Any]]
    conversation_id: UUID
    model: str
    history: list[dict]
    tools: dict[str, Callable[..., Any]]


def parse_facts_from_mem0(memory: dict) -> str:
    data = []

    # Добавляем факты
    if results := memory.get("results"):
        data.append("\n📝 Факты о пользователе:")
        for item in results:
            data.append(f" • {item['memory']} - {item['created_at'][:16]}")

    # Добавляем связи
    if relations := memory.get("relations"):
        data.append("\n🔗 Связи:")
        for relation in relations:
            source = relation["source"].replace("user_id:_", "User").replace("_", " ")
            dest = relation["destination"].replace("_", " ")
            rel_type = relation["relationship"].replace("_", " ")
            data.append(f"  • {source} → {rel_type} → {dest}")

    return "\n".join(data) if data else "Нет данных о пользователе"


def _handle_memory_result(ts: asyncio.Task) -> None:
    if ts.cancelled():
        logger.warning("Задача mem0ai отменена")
    elif ts.exception():
        logger.error(f"Ошибка mem0ai: {ts.exception()}", exc_info=ts.exception())
    else:
        logger.debug("mem0ai успешно сохранил память")


class MessageService:
    def __init__(
        self,
        memory: AsyncMemory,
        db: AsyncSession,
        llm: AsyncOpenAILLM,
    ):
        self.memory = memory
        self.db = db
        self.llm = llm

    async def stream(
        self,
        conversation_id: UUID,
        message: str,
        message_role: str,
        user_id: UUID,
        mem0ai_on: bool = False,
        mem0ai_save: bool = True,
        prompt_id: UUID | None = None,
        model: str | None = None,
        sliding_window: int = 10,
        memory_facts: int = 5,
    ) -> StreamData:
        """
        Подготовить данные для генерации поточного ответа.

        Выполняет всю логику с валидацией, сохранением сообщения и генерацией стрима.
        Возвращает словарь с данными для передачи в stream_generator.

        Дополнительно поддерживает:
        - Выборочное использование mem0ai
        - Кастомные промпты
        - Настройку контекста (sliding window, memory facts)

        Args:
            conversation_id: UUID беседы
            message: Сообщение пользователя
            message_role: Роль отправителя сообщения (user/assistant/system)
            mem0ai_on: Использовать ли mem0ai для извлечения и поиска релевантных фактов
            mem0ai_save: Сохранять ли сообщение в память mem0ai
            prompt_id: ID кастомного промпта (опционально)
            model: Название модели LLM (опционально)
            sliding_window: Количество сообщений для контекста LLM (1-1000)
            memory_facts: Количество релевантных фактов из памяти (1-100)
            user_id: ID аутентифицированного пользователя


        Returns:
            StreamData:
                - stream: AsyncIterator для стриминга
                - result_awaitable: Awaitable для получения результата
                - conversation_id: UUID беседы
                - model: Название модели
                - history: История сообщений для контекста
                - tools: Словарь с доступными инструментами

        Raises:
            NotFoundError: Если беседа не найдена
            PromptNotFoundError: Если промпт не найден или недоступен
            ValidationError: Если content сообщения пустой
            LLMGenerationError: При ошибке генерации ответа
        """
        tools: dict[str, Callable[..., Any]] = {
            "web_search": web_search,
            "web_fetch": web_fetch,
            "create_file": make_create_file_tool(user_id),
        }

        logger.info(f"Запрос на добавление стримингового ответа v2 в беседу {conversation_id} пользователем {user_id}")

        # Проверка существования беседы
        conversation_result = await self.db.scalars(
            select(ConversationModel).where(
                ConversationModel.id == conversation_id,
                ConversationModel.user_id == user_id,
                ConversationModel.is_archived.is_(False),
            )
        )
        conversation = conversation_result.first()

        if not conversation:
            raise NotFoundError(f"Conversation {conversation_id} не найден")

        # Сохраняем сообщение пользователя
        user_message = MessageModel(
            conversation_id=conversation_id, role=message_role, content=message, model=self.llm.config.model
        )
        self.db.add(user_message)
        await self.db.flush()  # Получаем ID сообщения для background task
        await self.db.commit()

        # Получаем промпт с улучшенными проверками
        if prompt_id:
            prompt_result = await self.db.scalars(
                select(PromptModel).where(
                    PromptModel.id == prompt_id,
                    PromptModel.user_id == user_id,
                    PromptModel.is_active.is_(True),
                )
            )

            prompt = prompt_result.first()
            logger.info(f"Поиск промпта: id={prompt_id}, найден={prompt is not None}")
            if not prompt:
                logger.warning(f"Промпт не найден: id={prompt_id}, пользователь={user_id}")
                raise PromptNotFoundError(f"Промпт {prompt_id} не найден")

            prompt_content = prompt.content + f"\nСегодня: {str(datetime.now())}"
        else:
            prompt_content = START_PROMPT + f"\nСегодня: {str(datetime.now())}"

        if not mem0ai_on:
            history = await self._get_conversation_history(
                prompt=prompt_content, conversation_id=conversation_id, limit=sliding_window
            )
        else:
            # Получаем историю с системным промптом и релевантными фактами для контекста
            history = await self._get_conversation_history_with_mem0(
                message=message,
                user_id=user_id,
                prompt=prompt_content,
                conversation_id=conversation_id,
                limit=sliding_window,
                memory_limit=memory_facts,
            )

        # Передаём историю для генерации ответа
        try:
            stream, result_awaitable = await self.llm.generate_stream_response(
                messages=history,
                model=model,
                tools=[WEB_SEARCH_TOOL, WEB_FETCH_TOOL, CREATE_DOCUMENT_TOOL],
                tool_choice="auto",
            )
        except Exception as e:
            logger.error(f"Ошибка при генерации стримингового ответа: {e}")
            raise LLMGenerationError(str(e)) from e

        # Создаём фоновую задачу для работы mem0ai
        if mem0ai_save:
            task = asyncio.create_task(
                self.memory.add(
                    messages=[{"role": message_role, "content": message}],
                    user_id=str(user_id),
                    run_id=str(user_message.id),
                    metadata={"source_type": FactSource.EXTRACTED.value},
                )
            )

            task.add_done_callback(_handle_memory_result)

        logger.info(f"Сообщение добавлено в беседу {conversation_id}, стриминг запущен")

        # Возвращаем streaming ответ
        return StreamData(
            stream=stream,
            result_awaitable=result_awaitable,
            conversation_id=conversation_id,
            model=model if model is not None else self.llm.config.model or "gpt-4o-mini",
            history=history,
            tools=tools,
        )

    async def stream_generator(self, stream_data: StreamData) -> AsyncIterator[str]:
        """
        Асинхронный генератор для поточной передачи ответа LLM.

        Принимает подготовленные данные от message_stream и yields чанки ответа.

        Args:
            stream_data:

        Yields:
            str: Чанки ответа от LLM для передачи в StreamingResponse
        """
        async for chunk in self._stream_and_save_to_db(
            stream=stream_data.stream,
            result_awaitable=stream_data.result_awaitable,
            conversation_id=stream_data.conversation_id,
            model=stream_data.model,
            history=stream_data.history,
            tools=stream_data.tools,
        ):
            yield chunk

    async def _get_conversation_history(self, prompt: str, conversation_id: UUID, limit: int = 10) -> list[dict]:
        """Получить историю в формате для LLM"""

        result = await self.db.scalars(
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.timestamp.desc())
            .limit(limit)
        )

        messages = result.all()

        # Нормализуем через Pydantic
        history = [HistoryMessage.model_validate(msg).model_dump(mode="json") for msg in reversed(messages)]

        # Преобразуем в формат для LLM
        return [{"role": "system", "content": prompt}] + history

    async def _get_conversation_history_with_mem0(
        self,
        message: str,
        user_id: UUID,
        prompt: str,
        conversation_id: UUID,
        limit: int = 10,
        memory_limit: int = 50,
        fact_score: float = 0.3,
    ) -> list[dict]:
        """Получить историю с релевантными фактами из mem0 в формате для LLM"""
        start = time.time()

        result = await self.db.scalars(
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.timestamp.desc())
            .limit(limit)
        )
        db_time = time.time() - start

        messages = result.all()

        mem_start = time.time()
        facts = await self.memory.search(message, user_id=str(user_id), limit=memory_limit, threshold=fact_score)
        mem_time = time.time() - mem_start

        total_time = time.time() - start
        logger.info(
            f"Кол-во Фактов: {len(facts['results'])}, БД: {db_time:.3f}s, Mem0: {mem_time:.3f}s, Всего: {total_time:.3f}s"
        )
        new_prompt = prompt + parse_facts_from_mem0(facts)

        # Нормализуем через Pydantic
        history = [HistoryMessage.model_validate(msg).model_dump(mode="json") for msg in reversed(messages)]

        # Преобразуем в формат для LLM
        return [{"role": "system", "content": new_prompt}] + history

    async def _stream_and_save_to_db(
        self,
        stream: AsyncIterator[str],
        result_awaitable: Awaitable[dict[str, Any]],
        conversation_id: UUID,
        model: str,
        history: list[dict] | None = None,
        tools: dict[str, Callable[..., Any]] | None = None,
    ) -> AsyncIterator[str]:
        """
        Стримим сообщения пользователю, выполняем tools если есть, и сохраняем в БД.

        Args:
            stream: Асинхронный итератор текстовых chunks
            result_awaitable: Awaitable возвращающий dict с content и tool_calls
            conversation_id: UUID беседы
            model: Название модели
            history: История сообщений для выполнения tools (опционально)
            tools: Словарь доступных tools функций (опционально)
        """
        async for chunk in stream:
            yield chunk

        result = await result_awaitable
        content = result.get("content", "")
        tool_calls = result.get("tool_calls", [])

        # Если нет tool_calls или нет данных для выполнения — сохраняем и выходим
        if not tool_calls or not history or not tools:
            if tool_calls:
                logger.warning("Получены tool_calls но нет history/llm/tools для выполнения")

            assistant_message = MessageModel(
                conversation_id=conversation_id, role="assistant", content=content, model=model
            )
            self.db.add(assistant_message)
            await self.db.commit()
            return

        # Выполняем tools
        logger.info(f"Выполняем {len(tool_calls)} tools...")

        async def execute_tool(tool_call: dict) -> dict:
            name = tool_call["function"]["name"]
            args = tool_call["function"]["arguments"]

            # Пропускаем tools с невалидными аргументами (пустые после ошибки парсинга)
            if not args and name in ["create_file", "web_search", "web_fetch"]:
                error_msg = f"⚠️ Пропущен вызов {name}: пустые аргументы (невалидный JSON от модели)"
                logger.warning(error_msg)
                return {"role": "tool", "tool_call_id": tool_call["id"], "content": error_msg}

            logger.info(f"🔧 {name}({args})")
            try:
                result = await tools[name](**args)
                logger.info(f"📦 {result}")
            except Exception as e:
                error_msg = f"Ошибка выполнения {name}: {e}"
                logger.error(error_msg)
                result = error_msg
            return {"role": "tool", "tool_call_id": tool_call["id"], "content": str(result)}

        tool_results = await asyncio.gather(*[execute_tool(tc) for tc in tool_calls])

        # Добавляем в историю assistant message и tool results
        # Форматируем tool_calls для OpenAI API (требуется поле "type")
        formatted_tool_calls = [
            {
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["function"]["name"],
                    "arguments": json.dumps(tc["function"]["arguments"], ensure_ascii=False),
                },
            }
            for tc in tool_calls
        ]

        assistant_msg = {"role": "assistant", "content": content, "tool_calls": formatted_tool_calls}
        history.append(assistant_msg)
        history.extend(tool_results)

        # Стримим результаты tools пользователю
        yield "\n\n🔧 Выполняю инструменты:\n"
        for i, (tool_call, result) in enumerate(zip(tool_calls, tool_results, strict=True), 1):
            name = tool_call["function"]["name"]
            args = tool_call["function"]["arguments"]
            yield f"{i}. {name}({args})\n"
            yield f"   Результат:\n{result['content']}\n\n"

        # Второй запрос к LLM с результатами tools
        try:
            stream2, result2_awaitable = await self.llm.generate_stream_response(
                messages=history,
                model=model,
            )
        except Exception as e:
            logger.error(f"Ошибка при втором запросе: {e}")
            yield f"\n[Ошибка: {e}]"
            return

        # Стримим финальный ответ
        async for chunk in stream2:
            yield chunk

        # Сохраняем финальный ответ
        result2 = await result2_awaitable
        final_content = result2.get("content", "")

        assistant_message = MessageModel(
            conversation_id=conversation_id, role="assistant", content=final_content, model=model
        )
        self.db.add(assistant_message)
        await self.db.commit()
