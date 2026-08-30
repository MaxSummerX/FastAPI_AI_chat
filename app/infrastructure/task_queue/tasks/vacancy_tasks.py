import asyncio
from typing import Any
from uuid import UUID

import redis
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from celery.signals import worker_process_init, worker_process_shutdown
from loguru import logger
from sqlalchemy import and_, select

from app.application.schemas.vacancy import VacancyForAnalysis
from app.application.services.vacancy_analyzer import VacancyAnalyzer
from app.application.services.vacancy_import_service import VacancyImportService
from app.domain.enums.analysis import AnalysisType
from app.domain.enums.experience import Experience
from app.domain.models.user import User as UserModel
from app.domain.models.user_vacancies import UserVacancies as UserVacanciesModel
from app.domain.models.vacancy import Vacancy as VacancyModel
from app.domain.models.vacancy_analysis import VacancyAnalysis as VacancyAnalysisModel
from app.infrastructure.llms.config import analysis_llm_config
from app.infrastructure.llms.openai import AsyncOpenAILLM
from app.infrastructure.persistence.sqlalchemy.vacancy_repository import VacancySQLAlchemyRepository
from app.infrastructure.settings.settings import settings
from app.infrastructure.task_queue.celery_config import celery


LOCK_REDIS_URL = settings.LOCK_REDIS_URL
REQUEST_DELAY: float = 0.3

redis_client = redis.from_url(LOCK_REDIS_URL, decode_responses=True)


_worker_resources: dict = {}


@worker_process_init.connect
def init_worker(**kwargs: Any) -> None:
    """
    Выполняется в каждом воркер-процессе ПОСЛЕ fork.
    Engine создаётся уже в правильном процессе без привязки к старому loop.
    """
    from app.infrastructure.database.connection import create_session_factory
    from app.infrastructure.hh.headhunter_client import get_hh_client

    # Сначала создаём loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Потом engine — он создаётся внутри этого loop
    _worker_resources["session_factory"] = create_session_factory()
    _worker_resources["loop"] = loop

    async def init_hh() -> None:
        _worker_resources["hh_client"] = await get_hh_client()

    loop.run_until_complete(init_hh())


@celery.task
def clear_lock(retval: Any, lock_key: str) -> dict[str, Any]:
    """
    Удаляет блокировку из Redis после завершения задачи.
    Используется как callback в Celery цепочках задач.

    Args:
        retval: Результат предыдущей задачи (игнорируется)
        lock_key: Ключ блокировки для удаления
    """
    try:
        redis_client.delete(lock_key)
        logger.info(f"Блокировка удалена: {lock_key}")
        return {"status": "lock_cleared", "lock_key": lock_key}
    except Exception as e:
        logger.error(f"Ошибка при удалении блокировки: {e}")
        return {"status": "error", "error": str(e)}


@celery.task(bind=True, max_retries=3, time_limit=14400, soft_time_limit=13800)
def import_vacancy_task(self: Task, query: str, tiers: list[Experience] | None, user_id: str) -> dict[str, Any]:
    """
    Импортирует вакансии с hh.ru в фоновом режиме.

    Args:
        query: Поисковый запрос
        tiers: Фильтр по уровню опыта
        user_id: ID пользователя

    Returns:
        dict со статистикой импорта
    """

    async def run_import() -> dict[str, int]:
        """Асинхронная функция импорта вакансий."""
        async with _worker_resources["session_factory"]() as session:
            import_service = VacancyImportService(VacancySQLAlchemyRepository(session), _worker_resources["hh_client"])
            return await import_service.import_vacancies(
                query=query,
                tiers=tiers,
                user_id=UUID(user_id),
            )

    try:
        result: dict[str, Any] = _worker_resources["loop"].run_until_complete(run_import())
        logger.success(f"✅ Импорт завершён: query='{query}': {result}")
        result["user_id"] = user_id
        return result
    except Exception as e:
        logger.exception(f"❌ Ошибка импорта: {e}")
        raise self.retry(exc=e, countdown=60) from e


@celery.task(bind=True, max_retries=3, time_limit=14400, soft_time_limit=13800)
def ai_analyse_task(
    self: Task,
    type_analyze: list[AnalysisType],
    tiers: list[Experience],
    user_id: UUID,
    custom_prompt: str | None,
    limit: int = 50,
) -> dict[str, Any]:
    """
    Анализирует вакансии с помощью AI в фоновом режиме.

    Args:
        type_analyze: Список типов анализа
        tiers: Фильтр по уровню опыта
        user_id: ID пользователя
        custom_prompt: Кастомный промпт для CUSTOM типа
        limit: Максимальное количество вакансий для анализа

    Returns:
        dict со статистикой анализа
    """

    llm = AsyncOpenAILLM(analysis_llm_config)

    async def run_ai_analyse() -> dict[str, Any]:
        async with _worker_resources["session_factory"]() as session:
            stmt = (
                select(
                    VacancyModel.id,
                    VacancyModel.title,
                    VacancyModel.description,
                    VacancyModel.salary_from,
                    VacancyModel.salary_to,
                    VacancyModel.salary_currency,
                    VacancyModel.salary_gross,
                    VacancyModel.experience_id,
                    VacancyModel.area_name,
                    VacancyModel.schedule_id,
                    VacancyModel.employment_id,
                    VacancyModel.employer_name,
                    UserModel.resume,
                )
                .select_from(VacancyModel)
                .join(UserVacanciesModel, UserVacanciesModel.vacancy_id == VacancyModel.id)
                .join(UserModel, UserVacanciesModel.user_id == UserModel.id)
                .outerjoin(
                    VacancyAnalysisModel,
                    and_(
                        VacancyModel.id == VacancyAnalysisModel.vacancy_id,
                        VacancyAnalysisModel.analysis_type.in_(type_analyze),
                    ),
                )
                .where(
                    VacancyAnalysisModel.id.is_(None),
                    VacancyModel.experience_id.in_(tiers),
                    UserVacanciesModel.is_active.is_(True),
                    UserVacanciesModel.user_id == user_id,
                )
                .order_by(VacancyModel.created_at.desc())
                .limit(limit)
            )

            result_from_db = await session.execute(stmt)
            rows_vacancies = result_from_db.all()

            # Конвертируем Row объекты в Pydantic схемы для типизации
            vacancies: list[VacancyForAnalysis] = [VacancyForAnalysis.model_validate(row) for row in rows_vacancies]

        async with _worker_resources["session_factory"]() as session:
            analyzed = 0
            skipped = 0
            for vacancy in vacancies:
                for analysis in type_analyze:
                    vacancy_data = {
                        "title": vacancy.title,
                        "description": vacancy.description,
                        "salary_from": vacancy.salary_from,
                        "salary_to": vacancy.salary_to,
                        "employer": vacancy.employer_name,
                        "currency": vacancy.salary_currency,
                        "salary_gross": vacancy.salary_gross,
                        "experience_id": vacancy.experience_id,
                        "area_name": vacancy.area_name,
                        "schedule_id": vacancy.schedule_id,
                        "employment_id": vacancy.employment_id,
                    }
                    try:
                        analyzer = VacancyAnalyzer(
                            llm=llm,
                            vacancy_repo=VacancySQLAlchemyRepository(session),
                        )
                        data = await analyzer.analyze(
                            content=vacancy_data,
                            analysis_type=AnalysisType(analysis),
                            resume=vacancy.resume,
                            custom_prompt=custom_prompt,
                        )

                        session.add(
                            VacancyAnalysisModel(
                                vacancy_id=vacancy.id,
                                user_id=user_id,
                                title=f"{AnalysisType(analysis).display_name}: {vacancy.title}",
                                analysis_type=analysis,
                                prompt_template=AnalysisType(analysis).description,
                                custom_prompt=custom_prompt if custom_prompt else None,
                                result_text=data,
                            )
                        )
                        await session.commit()
                        analyzed += 1
                    except Exception:
                        await session.rollback()
                        skipped += 1
                        logger.exception(f"Пропущен анализ: vacancy={vacancy.id}, type={analysis}")
                    await asyncio.sleep(REQUEST_DELAY)

        return {
            "analyzed": analyzed,
            "skipped": skipped,
            "vacancies": len(vacancies),
            "user_id": user_id,
        }

    try:
        result: dict[str, Any] = _worker_resources["loop"].run_until_complete(run_ai_analyse())
        logger.success(f"✅ Подсчёт вакансий: {result}")
        return result
    except SoftTimeLimitExceeded:
        logger.warning(
            "Soft time limit в ai_analyse_task (user={}): : частичный результат сохранён, без retry", user_id
        )
        return {"status": "partial_timeout", "user_id": user_id}
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        raise self.retry(exc=e, countdown=60) from e


@celery.task(bind=True, max_retries=3, time_limit=14400, soft_time_limit=13800)
def sync_archive_statuses_task(self: Task) -> dict:
    """
    Celery задача для синхронизации архивных статусов вакансий с hh.ru.

    Проверяет все активные вакансии в БД и обновляет их статус (archived=True/False)
    через страницы hh.ru. Использует VacancyImportService для выполнения синхронизации.

    Args:
        self: Экземпляр Celery задачи (автоматически передаётся при bind=True)

    Returns:
        Словарь со статистикой выполнения:
        - processed: количество успешно обновлённых вакансий
        - skipped: количество пропущенных (ошибки API)
        - total: общее количество проверенных вакансий

    Raises:
        Exception: При ошибке синхронизации с автоматическим retry через 60 секунд
    """

    async def _run() -> dict:
        async with _worker_resources["session_factory"]() as session:
            service = VacancyImportService(VacancySQLAlchemyRepository(session), _worker_resources["hh_client"])
            return await service.sync_archive_statuses()

    try:
        result: dict = _worker_resources["loop"].run_until_complete(_run())
        logger.success(f"✅ Синхронизация завершена: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка синхронизации: {e}")
        raise self.retry(exc=e, countdown=60) from e


@worker_process_shutdown.connect
def shutdown_http_clients(**kwargs: Any) -> None:
    """
    Закрытие HTTP клиента при остановке/рестарте воркер-процесса.
    Срабатывает при SIGTERM/SIGINT воркера, а также при рециклинге
    процесса по worker_max_tasks_per_child.
    """
    loop = _worker_resources.get("loop")
    if loop is None or loop.is_closed():
        logger.warning("Loop не найден или уже закрыт — пропускаем закрытие hh_client")
        return

    async def _shutdown() -> None:
        from app.infrastructure.hh.headhunter_client import close_hh_client

        await close_hh_client()

    try:
        loop.run_until_complete(_shutdown())
    except Exception as e:
        logger.error(f"Ошибка при закрытии hh_client: {e}")
    finally:
        loop.close()
