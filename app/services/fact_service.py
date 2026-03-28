import json
from typing import Any, cast
from uuid import UUID

from loguru import logger
from mem0 import AsyncMemory
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.fact import FactCreate
from app.domain.enums.fact import FactCategory, FactSource
from app.domain.models import User as UserModel
from app.domain.models.fact import Fact as FactModel


class FactNotFoundException(Exception):
    """Факт не найден"""

    pass


class UserProvidedException(Exception):
    """Факт не был создан пользователем (нельзя редактировать/удалять)"""

    pass


async def get_fact_or_404_or_403(fact_id: UUID, user_id: UUID, db: AsyncSession) -> FactModel:
    """
    Получить факт или выбросить исключение.

    Проверяет что факт существует, активен, принадлежит пользователю
    и является USER_PROVIDED (только такие факты можно редактировать/удалять).

    Args:
        fact_id: UUID факта
        user_id: UUID пользователя
        db: Сессия БД

    Returns:
        FactModel: Найденный факт

    Raises:
        FactNotFoundException: Если факт не найден или неактивен
        UserProvidedException: Если факт не был создан пользователем (EXTRACTED)
    """
    stmt = select(FactModel).where(FactModel.id == fact_id, FactModel.user_id == user_id, FactModel.is_active.is_(True))

    fact = cast(FactModel | None, await db.scalar(stmt))

    if not fact:
        raise FactNotFoundException(f"Fact {fact_id} not found or not active")

    if fact.source_type != FactSource.USER_PROVIDED:
        raise UserProvidedException(f"Fact {fact_id} not provided")

    return fact


async def create_user_fact(
    data: FactCreate,
    memory: AsyncMemory,
    current_user: UserModel,
    db: AsyncSession,
) -> None:
    """
    Создать факт в PostgreSQL и mem0ai.

    Процесс:
    1. Добавляет факт в Qdrant через mem0ai (infer=False - без связей в Neo4j)
    2. Получает mem0_id из ответа Qdrant
    3. Создаёт запись в PostgreSQL с mem0_id

    Args:
        data: Данные для создания факта
        memory: Экземпляр AsyncMemory из mem0ai
        current_user: Текущий пользователь
        db: Сессия базы данных PostgreSQL

    Returns:
        None (функция для background task)

    Raises:
        Exception: При ошибке создания в mem0ai или PostgreSQL
    """
    try:
        category = data.category

        if category is None:
            category = FactCategory.PERSONAL

        mem0_metadata = {
            "source_type": FactSource.USER_PROVIDED.value,
            "category": category.value,
        }

        if data.metadata_:
            mem0_metadata.update(data.metadata_)

        result = await memory.add(
            messages=data.content, user_id=str(current_user.id), infer=False, metadata=mem0_metadata
        )

        new_fact = FactModel(
            user_id=current_user.id,
            content=data.content,
            category=category,
            source_type=FactSource.USER_PROVIDED,
            confidence=data.confidence,
            metadata_=data.metadata_,
            mem0_id=UUID(result["results"][0]["id"]),  # Конвертируем строку в UUID
        )

        db.add(new_fact)
        await db.commit()

        logger.info(f"Факт {new_fact.id} создан с mem0_id {new_fact.mem0_id}")

    except Exception as e:
        logger.error(f"Ошибка при создании факта: {e}")
        await db.rollback()
        raise


async def update_user_fact(
    fact: FactModel,
    data: FactCreate,
    memory: AsyncMemory,
    current_user: UserModel,
    db: AsyncSession,
) -> None:
    """
    Обновить факт в PostgreSQL и mem0ai.

    Процесс:
    1. Удаляет старый факт из Qdrant
    2. Добавляет новый факт в Qdrant
    3. Обновляет запись в PostgreSQL с новым mem0_id

    Args:
        fact: Объект факта для обновления (FactModel)
        data: Новые данные факта
        memory: Экземпляр AsyncMemory из mem0ai
        current_user: Текущий пользователь
        db: Сессия базы данных PostgreSQL

    Returns:
        None (функция для background task)

    Raises:
        ValueError: Если факт не найден
        Exception: При ошибке обновления в mem0ai или PostgreSQL
    """
    try:
        if not fact.mem0_id:
            raise ValueError(f"Факт {fact.id} не имеет mem0_id - невозможное состояние")

        # 1. Удалить старый факт из Qdrant
        await memory.delete(memory_id=str(fact.mem0_id))
        logger.info(f"Удален старый mem0_id {fact.mem0_id} из Qdrant")

        category = data.category if data.category else FactCategory.PERSONAL

        mem0_metadata = {
            "source_type": FactSource.USER_PROVIDED.value,
            "category": category.value,
        }

        if data.metadata_:
            mem0_metadata.update(data.metadata_)

        # 2. Добавить новый факт в Qdrant
        result = await memory.add(
            messages=data.content, user_id=str(current_user.id), infer=False, metadata=mem0_metadata
        )

        update_data = data.model_dump(exclude_unset=True, by_alias=False)
        update_data["mem0_id"] = UUID(result["results"][0]["id"])  # Конвертируем строку в UUID
        update_data["category"] = category

        # 3. Обновить факт в PostgreSQL
        await db.execute(update(FactModel).where(FactModel.id == fact.id).values(**update_data))

        await db.commit()

        logger.info(f"Факт {fact.id} обновлён с новым mem0_id {result['results'][0]['id']}")

    except Exception as e:
        logger.error(f"Ошибка при обновлении факта {fact.id}: {e}")
        await db.rollback()
        raise


async def import_from_mem0ai_to_postgres_db(
    user_id: UUID,
    memory: AsyncMemory,
    db: AsyncSession,
) -> None:
    """
    Импортировать факты из mem0ai в PostgreSQL.

    Процесс:
    1. Получает все факты EXTRACTED из mem0ai для пользователя
    2. Собирает валидные message_id и строит отображения:
       - fact_by_memory: {memory_content: fact_data}
       - message_id_by_memory: {memory_content: message_id}
    3. Батч-запросом получает все сообщения из PostgreSQL
    4. Батч-запросом проверяет какие факты уже существуют
    5. Для каждого нового факта:
       - Пропускает если факт уже существует
       - Пропускает если сообщение не найдено
       - Если нет категории в metadata → вызывает LLM для категоризации
       - Создаёт FactModel с данными из Qdrant
    6. Сохраняет все новые факты одним батч-коммитом

    Оптимизация N+1:
    - Вместо 2N запросов использует 2 батч-запроса (messages + existing_facts)
    - Использует set/dict для O(1) поиска вместо запросов в цикле

    Args:
        user_id: UUID пользователя для импорта фактов
        memory: Экземпляр AsyncMemory из mem0ai
        db: Сессия базы данных PostgreSQL

    Returns:
        None

    Note:
        - Функция для background task (асинхронная)
        - Пропускает факты с невалидным run_id
        - Категоризирует факты через LLM если нет категории в metadata
    """
    from app.application.prompts.parsing_category import PARSE_CATEGORY
    from app.configs.llm_config import parse_llm_config
    from app.domain.models.message import Message as MessageModel
    from app.llms.openai import AsyncOpenAILLM

    llm = AsyncOpenAILLM(parse_llm_config)

    # Запрашиваем все EXTRACTED факты из mem0ai для пользователя
    facts = await memory.get_all(user_id=str(user_id), filters={"source_type": FactSource.EXTRACTED.value})

    # Строим отображения для батч-обработки
    fact_by_memory: dict[str, Any] = {}  # {memory_content: fact_data}
    message_id_by_memory: dict[str, UUID] = {}  # {memory_content: message_id}
    message_ids: list[UUID] = []  # список всех message_id для батч-запроса

    # Собираем факты в отображения, фильтруя невалидные UUID
    for fact in facts["results"]:
        try:
            message_id = UUID(fact["run_id"])  # извлекаем message_id из run_id
            memory_content = fact["memory"]  # текст факта
            message_ids.append(message_id)
            fact_by_memory[memory_content] = fact  # для быстрого O(1) доступа
            message_id_by_memory[memory_content] = message_id
        except ValueError:
            logger.warning(f"Невалидный run_id: {fact.get('run_id')}")
            continue

    # Ранний возврат если нет валидных данных
    if not message_ids:
        logger.info("Нет валидных фактов для импорта")
        return

    # Батч-запросы к PostgreSQL
    # Запрос 1: получаем все сообщения одним запросом (вместо N отдельных)
    messages_result = await db.scalars(select(MessageModel).where(MessageModel.id.in_(message_ids)))
    messages_by_id = {msg.id: msg for msg in messages_result}  # {message_id: message}

    # Запрос 2: проверяем существующие факты одним запросом
    existing_contents = list(fact_by_memory.keys())  # все memory_content для проверки
    existing_facts_result = await db.scalars(
        select(FactModel).where(FactModel.content.in_(existing_contents), FactModel.source_type == FactSource.EXTRACTED)
    )
    existing_fact_contents = {fact.content for fact in existing_facts_result}  # set для O(1)

    # Обработка фактов
    new_facts = []
    skipped_messages = 0
    skipped_facts = 0

    for memory_content, fact in fact_by_memory.items():
        message_id = message_id_by_memory[memory_content]

        # Пропускаем если факт уже существует в PostgreSQL
        if memory_content in existing_fact_contents:
            logger.info(f"Факт уже есть: {memory_content[:50]}...")
            skipped_facts += 1
            continue

        # Пропускаем если сообщение не найдено (было удалено)
        message_db = messages_by_id.get(message_id)
        if not message_db:
            logger.info(f"Сообщение не найдено: {message_id}")
            skipped_messages += 1
            continue

        # Определяем категорию факта
        if fact["metadata"] is None or "category" not in fact["metadata"]:
            # Категория не задана → вызываем LLM для классификации
            message = [
                {"role": "system", "content": PARSE_CATEGORY},
                {"role": "user", "content": fact["memory"]},
            ]
            response = await llm.generate_response(message, response_format={"type": "json_object"})
            response_str = str(response) if isinstance(response, dict) else response
            category_data: dict[str, Any] = json.loads(response_str)
            logger.info(f"Категория из LLM: {category_data}")

            category_value = category_data.get("category")

            if category_value is None:
                logger.info(f"Категория не определена для факта: {fact['memory']}")
                continue
        else:
            # Категория есть в metadata → используем её
            category_value = fact["metadata"]["category"]
            logger.info(f"Категория из metadata: {category_value}")

        # Создаём новый факт для PostgreSQL
        new_fact = FactModel(
            user_id=user_id,
            content=fact["memory"],
            category=category_value,
            source_type=FactSource.EXTRACTED,
            source_conversation_id=message_db.conversation_id,  # ссылка на беседу
            source_message_id=message_db.id,  # ссылка на сообщение
            mem0_id=fact["id"],  # ID факта в Qdrant
        )
        new_facts.append(new_fact)

    # Сохраняем все новые факты одним батч-коммитом
    if new_facts:
        db.add_all(new_facts)
        await db.commit()
    logger.info(
        f"Импорт завершён: создано={len(new_facts)}, пропущено фактов={skipped_facts}, пропущено сообщений={skipped_messages}"
    )
