import asyncio
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from loguru import logger

from app.application.dto.stream import StreamData
from app.application.exceptions.conversation import ConversationNotFoundError
from app.application.exceptions.llm import LLMGenerationError
from app.application.exceptions.prompt import PromptNotFoundError
from app.application.prompts.base import START_PROMPT
from app.application.schemas.fact import FactSource
from app.application.schemas.message import HistoryMessage, MessageResponse
from app.application.schemas.pagination import PaginatedResponse
from app.domain.repositories.conversations import IConversationRepository
from app.domain.repositories.messages import IMessageRepository
from app.domain.repositories.prompts import IPromptRepository
from app.domain.services.llm import ILLMService
from app.domain.services.memory import IMemoryService
from app.infrastructure.llms.tools import (
    CREATE_DOCUMENT_TOOL,
    FILE_SEARCH_TOOL,
    WEB_FETCH_TOOL,
    WEB_SEARCH_TOOL,
    make_create_file_tool,
    make_search_documents_tool,
    web_fetch,
    web_search,
)


def _handle_memory_result(ts: asyncio.Task) -> None:
    """Обработать результат фоновой задачи mem0ai."""
    if ts.cancelled():
        logger.warning("Задача mem0ai отменена")
    elif ts.exception():
        logger.error("Ошибка mem0ai: {}", ts.exception(), exc_info=ts.exception())
    else:
        logger.debug("mem0ai успешно сохранил память")


class MessageService:
    """
    Сервис для обработки сообщений с поддержкой multi-round tool calls.

    Управляет жизненным циклом сообщений в беседах:
    создание, получение истории, генерация AI-ответов через LLM,
    интеграция с системой памяти (mem0ai) и выполнение инструментов.
    """

    def __init__(
        self,
        message_repo: IMessageRepository,
        conversation_repo: IConversationRepository,
        prompt_repo: IPromptRepository,
        llm_service: ILLMService,
        memory_service: IMemoryService,
    ):
        """
        Инициализирует сервис сообщений.

        Args:
            message_repo: Репозиторий сообщений для доступа к данным
            conversation_repo: Репозиторий бесед для проверки существования
            prompt_repo: Репозиторий промптов для кастомных системных промптов
            llm_service: Сервис языковой модели для генерации ответов
            memory_service: Сервис памяти для извлечения и сохранения фактов
        """
        self.message_repo = message_repo
        self.conversation_repo = conversation_repo
        self.prompt_repo = prompt_repo
        self.llm_service = llm_service
        self.memory_service = memory_service

    async def get_user_messages(
        self,
        limit: int,
        cursor: str | None,
        user_id: UUID,
        conversation_id: UUID,
    ) -> PaginatedResponse[MessageResponse]:
        """
        Получить сообщения беседы с курсорной пагинацией.

        Args:
            limit: Максимальное количество сообщений на странице
            cursor: Курсор из предыдущего ответа для следующей страницы
            user_id: UUID пользователя для проверки прав доступа
            conversation_id: UUID беседы

        Returns:
            PaginatedResponse с сообщениями и метаданными пагинации

        Raises:
            ConversationNotFoundError: Если беседа не существует или недоступна пользователю
        """
        logger.debug(
            "Запрос на получение сообщений пользователя пользователя {} с пагинацией: limit={}, cursor={}",
            user_id,
            limit,
            "да" if cursor else "нет",
        )

        conversation = await self.conversation_repo.get_by_id(conversation_id=conversation_id, user_id=user_id)

        if not conversation:
            logger.warning("Попытка доступа к несуществующей беседе {} пользователем {}", conversation_id, user_id)
            raise ConversationNotFoundError("Conversation not found")

        messages, next_cursor, has_next = await self.message_repo.get_paginated(
            conversation_id=conversation_id,
            cursor=cursor,
            limit=limit,
        )
        logger.debug(
            "Возвращено {} сообщений, has_next={}, next_cursor={}",
            len(messages),
            has_next,
            "да" if next_cursor else "нет",
        )

        return PaginatedResponse(
            items=[MessageResponse.model_validate(message) for message in messages],
            next_cursor=next_cursor,
            has_next=has_next,
        )

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
            "search_documents": make_search_documents_tool(user_id),
        }

        logger.info(
            "Запрос на добавление стримингового ответа v2 в беседу {} пользователем {}", conversation_id, user_id
        )

        # Проверка существования беседы
        conversation = await self.conversation_repo.get_by_id(conversation_id=conversation_id, user_id=user_id)

        if not conversation:
            raise ConversationNotFoundError("Conversation {} не найден", conversation_id)

        user_message = await self.message_repo.create(
            conversation_id=conversation_id, role=message_role, content=message, model=self.llm_service.default_model
        )

        # Получаем промпт с улучшенными проверками
        if prompt_id:
            prompt = await self.prompt_repo.get_by_id(prompt_id=prompt_id, user_id=user_id)

            logger.info("Поиск промпта: id={}, найден={}", prompt_id, prompt is not None)
            if not prompt:
                logger.warning("Промпт не найден: id={}, пользователь={}", prompt_id, user_id)
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
            stream, result_awaitable = await self.llm_service.generate_stream_response(
                messages=history,
                model=model,
                tools=[WEB_SEARCH_TOOL, WEB_FETCH_TOOL, CREATE_DOCUMENT_TOOL, FILE_SEARCH_TOOL],
                tool_choice="auto",
            )
        except Exception as e:
            logger.error("Ошибка при генерации стримингового ответа: {}", e)
            raise LLMGenerationError(str(e)) from e

        # Создаём фоновую задачу для работы mem0ai
        if mem0ai_save:
            task = asyncio.create_task(
                self.memory_service.add(
                    messages=[{"role": message_role, "content": message}],
                    user_id=str(user_id),
                    run_id=str(user_message.id),
                    metadata={"source_type": FactSource.EXTRACTED.value},
                )
            )

            task.add_done_callback(_handle_memory_result)

        logger.info("Сообщение добавлено в беседу {}, стриминг запущен", conversation_id)

        # Возвращаем streaming ответ
        return StreamData(
            stream=stream,
            result_awaitable=result_awaitable,
            conversation_id=conversation_id,
            model=model if model is not None else self.llm_service.default_model or "gpt-4o-mini",
            history=history,
            tools=tools,
        )

    @staticmethod
    def parse_facts_from_mem0(memory: dict) -> str:
        """Извлечь и отформатировать факты из ответа mem0."""
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

    async def stream_generator(self, stream_data: StreamData) -> AsyncIterator[str]:
        """
        Асинхронный генератор для поточной передачи ответа LLM.

        Принимает подготовленные данные от метода stream и yields чанки ответа.

        Args:
            stream_data: Подготовленные данные для стриминга (StreamData)

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
        """
        Получить историю сообщений в формате для LLM.

        Извлекает последние сообщения из беседы, нормализует их через Pydantic
        и добавляет системный промпт в начало.

        Args:
            prompt: Системный промпт для LLM
            conversation_id: UUID беседы
            limit: Максимальное количество сообщений

        Returns:
            Список словарей в формате [{"role": "...", "content": "..."}]
        """

        messages = await self.message_repo.get_history(conversation_id=conversation_id, limit=limit)

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
        """
        Получить историю сообщений с релевантными фактами из mem0ai.

        Выполняет поиск фактов в памяти пользователя, извлекает историю
        сообщений и формирует контекст для LLM с найденными фактами.

        Args:
            message: Текст сообщения пользователя для поиска релевантных фактов
            user_id: UUID пользователя
            prompt: Системный промпт для LLM
            conversation_id: UUID беседы
            limit: Максимальное количество сообщений из истории
            memory_limit: Максимальное количество фактов из памяти
            fact_score: Минимальный порог схожести для фактов (0.0-1.0)

        Returns:
            Список словарей в формате [{"role": "...", "content": "..."}]
            с расширенным системным промптом, включающим факты
        """
        start = time.time()
        messages = await self.message_repo.get_history(conversation_id=conversation_id, limit=limit)
        db_time = time.time() - start

        mem_start = time.time()
        facts = await self.memory_service.search(
            message, user_id=str(user_id), limit=memory_limit, threshold=fact_score
        )
        mem_time = time.time() - mem_start

        total_time = time.time() - start
        logger.info(
            f"Кол-во Фактов: {len(facts['results'])}, БД: {db_time:.3f}s, Mem0: {mem_time:.3f}s, Всего: {total_time:.3f}s"
        )
        new_prompt = prompt + self.parse_facts_from_mem0(facts)

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
        max_tool_rounds: int = 5,
    ) -> AsyncIterator[str]:
        """
        Стримим сообщения пользователю, выполняем tools если есть, и сохраняем в БД.

        НОВОЕ: Поддержка множественных раундов tool calls (multi-round).
        Модель может вызывать инструменты последовательно несколько раз.

        Args:
            stream: Асинхронный итератор текстовых chunks
            result_awaitable: Awaitable возвращающий dict с content и tool_calls
            conversation_id: UUID беседы
            model: Название модели
            history: История сообщений для выполнения tools (опционально)
            tools: Словарь доступных tools функций (опционально)
            max_tool_rounds: Максимальное количество раундов tool calls (защита от зацикливания)

        Raises:
            ValueError: Если превышено максимальное количество раундов tools
        """
        if history is None:
            history = []
        if tools is None:
            tools = {}

        # Цикл для multi-round tool calls
        for round_num in range(max_tool_rounds + 1):
            # Стримим ответ от LLM
            async for chunk in stream:
                yield chunk

            # Получаем результат
            result = await result_awaitable
            content = result.get("content", "")
            tool_calls = result.get("tool_calls", [])

            # Логирование раунда
            if tool_calls:
                logger.info("🔄 Раунд {}: {} tool calls", round_num + 1, len(tool_calls))

            # Если нет tool_calls или нет данных для выполнения — сохраняем и выходим
            if not tool_calls or not tools:
                if tool_calls:
                    logger.warning("Получены tool_calls но нет history/llm/tools для выполнения")

                # Сохраняем финальный ответ в БД
                await self.message_repo.create(
                    conversation_id=conversation_id, role="assistant", content=content, model=model
                )
                return

            # Форматируем tool_calls для OpenAI API и сохраняем в БД
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

            if content:
                await self.message_repo.create(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=content,
                    model=model,
                    metadata_={"tool_calls": formatted_tool_calls},  # Сохраняем metadata
                )

            # Выполняем tools
            logger.info("Выполняем {} tools...", len(tool_calls))

            async def execute_tool(tool_call: dict, formatted_calls: list) -> dict:
                """Выполнить один tool call."""
                func_name = tool_call["function"]["name"]
                func_args = tool_call["function"]["arguments"]

                # Пропускаем tools с невалидными аргументами
                if not func_args and func_name in ["create_file", "web_search", "web_fetch", "search_documents"]:
                    error_msg = f"⚠️ Пропущен вызов {func_name}: пустые аргументы (невалидный JSON от модели)"
                    logger.warning(error_msg)
                    return {"role": "tool", "tool_calsl_id": tool_call["id"], "content": error_msg}

                logger.info(f"🔧 {func_name}({func_args})")
                try:
                    result = await tools[func_name](**func_args)
                    logger.info(f"📦 {result}")

                    # Сохраняем result с tool_calls в БД
                    await self.message_repo.create(
                        conversation_id=conversation_id,
                        role="assistant",
                        content=result,
                        model=model,
                        metadata_={"tool_calls": formatted_calls},  # Сохраняем metadata
                    )

                except Exception as er:
                    error_msg = f"Ошибка выполнения {func_name}: {er}"
                    logger.error(error_msg)
                    result = error_msg
                return {"role": "tool", "tool_call_id": tool_call["id"], "content": str(result)}

            tool_results = await asyncio.gather(*[execute_tool(tc, formatted_tool_calls) for tc in tool_calls])

            # Добавляем в историю assistant message и tool results
            assistant_msg = {"role": "assistant", "content": content, "tool_calls": formatted_tool_calls}
            history.append(assistant_msg)
            history.extend(tool_results)

            # Стримим результаты tools пользователю
            if round_num == 0:
                yield "\n\n🔧 Выполняю инструменты:\n"
            else:
                yield f"\n\n🔧 Раунд {round_num + 1} - Выполняю инструменты:\n"

            for i, (tool_call, result) in enumerate(zip(tool_calls, tool_results, strict=True), 1):
                name = tool_call["function"]["name"]
                args = tool_call["function"]["arguments"]
                yield f"{i}. {name}({args})\n"
                yield f"   Результат:\n{result['content']}\n\n"

            # Следующий запрос к LLM с результатами tools
            try:
                stream, result_awaitable = await self.llm_service.generate_stream_response(
                    messages=history,
                    model=model,
                )
            except Exception as e:
                logger.error(f"Ошибка при запросе: {e}")
                yield f"\n[Ошибка: {e}]"
                return

            # Продолжаем цикл - stream и result_awaitable обновлены для следующей итерации

        # Если вышли из цикла по превышению max_tool_rounds
        logger.error("Превышено максимальное количество раундов tool calls: {}", max_tool_rounds)
        yield "\n\n[Ошибка: Превышено максимальное количество операций]"

        # Сохраняем последний результат
        result = await result_awaitable
        final_content = result.get("content", "")
        await self.message_repo.create(
            conversation_id=conversation_id, role="assistant", content=final_content, model=model
        )
