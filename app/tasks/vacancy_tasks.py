import asyncio
import os
from typing import Any
from uuid import UUID

import redis
from celery import Task
from loguru import logger
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.configs.celery_config import celery
from app.configs.llm_config import researcher_llm_config
from app.enum.analysis import AnalysisType
from app.enum.experience import Experience
from app.llms.openai import AsyncOpenAILLM
from app.models.users import User as UserModel
from app.models.vacancies import Vacancy as VacancyModel
from app.models.vacancy_analysis import VacancyAnalysis as VacancyAnalysisModel
from app.schemas.vacancies import VacancyForAnalysis
from app.tools.ai_research.analyzer import analyze_vacancy
from app.tools.headhunter.find_vacancies import import_vacancies


database_url = os.getenv("POSTGRESQL")
LOCK_REDIS_URL = os.getenv("LOCK_REDIS_URL")

redis_client = redis.from_url(LOCK_REDIS_URL, decode_responses=True)


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


@celery.task(bind=True, max_retries=3)
def import_vacancy_task(self: Task, query: str, tiers: list[Experience] | None, user_id: UUID) -> dict[str, Any]:
    """
    Импортирует вакансии с hh.ru в фоновом режиме.

    Args:
        query: Поисковый запрос
        tiers: Фильтр по уровню опыта
        user_id: ID пользователя

    Returns:
        dict со статистикой импорта
    """
    engine = create_async_engine(database_url, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def run_import() -> dict[str, Any]:
        async with session_maker() as session:
            return await import_vacancies(
                query=query,
                tiers=tiers,
                user_id=user_id,
                session=session,
            )

    try:
        result = asyncio.run(run_import())
        logger.success(f"✅ Импорт завершён: query='{query}': {result}")
        result["user_id"] = user_id
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        raise self.retry(exc=e, countdown=60) from e


@celery.task(bind=True, max_retries=3)
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
    engine = create_async_engine(database_url, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    llm = AsyncOpenAILLM(researcher_llm_config)

    async def run_ai_analyse() -> dict[str, Any]:
        async with session_maker() as session:
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
                .join(UserModel, VacancyModel.user_id == UserModel.id)
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
                    VacancyModel.is_active.is_(True),
                    VacancyModel.user_id == user_id,
                )
                .order_by(VacancyModel.created_at.desc())
                .limit(limit)
            )

            result_from_db = await session.execute(stmt)
            rows_vacancies = result_from_db.all()

            # Конвертируем Row объекты в Pydantic схемы для типизации
            vacancies: list[VacancyForAnalysis] = [VacancyForAnalysis.model_validate(row) for row in rows_vacancies]

        async with session_maker() as session:
            analysis_to_add = []
            index = len(vacancies)

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
                    data = await analyze_vacancy(
                        content=vacancy_data,
                        llm=llm,
                        analysis_type=AnalysisType(analysis),
                        resume=vacancy.resume,
                        custom_prompt=custom_prompt,
                    )

                    analysis_vacancy = VacancyAnalysisModel(
                        vacancy_id=vacancy.id,
                        user_id=user_id,
                        title=f"{AnalysisType(analysis).display_name}: {vacancy.title}",
                        analysis_type=analysis,
                        prompt_template=AnalysisType(analysis).description,
                        custom_prompt=custom_prompt if custom_prompt else None,
                        result_text=data,
                    )

                    analysis_to_add.append(analysis_vacancy)
                    await asyncio.sleep(index * 0.2)

            session.add_all(analysis_to_add)
            await session.commit()

        return {
            "analyzed": len(analysis_to_add),
            "vacancies": len(rows_vacancies),
            "user_id": user_id,
        }

    try:
        result = asyncio.run(run_ai_analyse())
        logger.success(f"✅ Подсчёт вакансий: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        raise self.retry(exc=e, countdown=60) from e
