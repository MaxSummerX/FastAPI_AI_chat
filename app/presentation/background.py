"""
Фоновые обёртки для BackgroundTasks.
"""

from pathlib import Path
from uuid import UUID

from httpx import AsyncClient
from loguru import logger

from app.domain.services.memory import IMemoryService


async def bg_import_conversation(
    user_id: UUID,
    provider: str,
    file_path: Path,
    split_dir: Path,
) -> None:
    """
    Фоновый импорт бесед: собственная сессия БД (request-сессия уже закрыта).

    Временные файлы чистятся в finally - даже если импорт упал.

    Args:
        user_id: ID пользователя
        provider: Провайдер экспорта (gpt/claude)
        file_path: Путь к загруженному файлу
        split_dir: Директория разбивки на диалоги
    """
    from app.application.services.upload_service import UploadService
    from app.domain.enums.provider import ImportedProvider
    from app.infrastructure.database.dependencies import async_session_maker
    from app.infrastructure.persistence.sqlalchemy import ConversationSQLAlchemyRepository, MessageSQLAlchemyRepository
    from app.infrastructure.upload.file_storage import cleanup

    try:
        async with async_session_maker() as session:
            service = UploadService(
                conversation_repo=ConversationSQLAlchemyRepository(session),
                message_repo=MessageSQLAlchemyRepository(session),
            )
            if provider == ImportedProvider.GPT.value:
                await service.import_from_gpt(user_id, provider, file_path, split_dir)
            elif provider == ImportedProvider.CLAUDE.value:
                await service.import_from_claude(user_id, provider, file_path, split_dir)
            else:
                raise ValueError(f"Неизвестный провайдер импорта: {provider}")
    except Exception:
        logger.exception("Фоновый импорт бесед упал | user_id={}, provider={}", user_id, provider)
    finally:
        await cleanup(file_path)
        await cleanup(split_dir)


async def bg_import_facts_from_mem0(user_id: UUID, memory_service: IMemoryService) -> None:
    """
    Фоновый импорт фактов из mem0: собственная сессия БД.

    Args:
        user_id: ID пользователя
        memory_service: Сервис памяти (mem0)
    """
    from app.application.services.fact_import_service import FactImportService
    from app.infrastructure.database.dependencies import async_session_maker
    from app.infrastructure.llms.config import parse_llm_config
    from app.infrastructure.llms.factory import create_llm_service
    from app.infrastructure.persistence.sqlalchemy import FactsSQLAlchemyRepository, MessageSQLAlchemyRepository

    try:
        async with async_session_maker() as session:
            service = FactImportService(
                fact_repo=FactsSQLAlchemyRepository(session),
                message_repo=MessageSQLAlchemyRepository(session),
                memory_service=memory_service,
                llm_service=create_llm_service(parse_llm_config),
            )
            await service.import_from_mem0ai_to_postgres_db(user_id=user_id)

    except Exception:
        logger.exception("Фоновый импорт фактов упал | user_id={}", user_id)


async def bg_sync_archive_statuses(hh_client: AsyncClient) -> None:
    """
    Фоновая синхронизация статусов архивации вакансий: собственная сессия БД.

    Args:
        hh_client: HTTP-клиент hh.ru
    """
    from app.application.services.vacancy_import_service import VacancyImportService
    from app.infrastructure.database.dependencies import async_session_maker
    from app.infrastructure.persistence.sqlalchemy import VacancySQLAlchemyRepository

    try:
        async with async_session_maker() as session:
            service = VacancyImportService(
                vacancy_repo=VacancySQLAlchemyRepository(session),
                hh_client=hh_client,
            )
            await service.sync_archive_statuses()

    except Exception:
        logger.exception("Фоновая синхронизация статусов архивации упала")
