from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.exceptions.analysis import InvalidAnalysisTypeError
from app.application.exceptions.llm import LLMGenerationError
from app.application.exceptions.user import UserNotFoundException
from app.application.exceptions.vacancy import VacancyNotFoundError
from app.application.schemas.vacancy_analysis import (
    AnalysisTypeInfo,
    AvailableAnalysesResponse,
    VacancyAnalysisCreate,
    VacancyBaseResponse,
    VacancyListResponse,
    VacancyResponse,
)
from app.domain.enums.analysis import AnalysisType
from app.domain.models.user import User as UserModel
from app.domain.models.user_vacancies import UserVacancies as UserVacanciesModel
from app.domain.models.vacancy import Vacancy as VacancyModel
from app.domain.models.vacancy_analysis import VacancyAnalysis as VacancyAnalysisModel
from app.infrastructure.database.dependencies import get_db
from app.infrastructure.llms.openai import AsyncOpenAILLM
from app.presentation.dependencies import get_current_user, get_researcher_llm
from app.services.ai_research import analyze_vacancy_from_db


MIN_SIZE_RESUME = 300

router = APIRouter(prefix="/{id_vacancy}/analyses", tags=["Vacancy_analyses_V2"])


@router.get("", status_code=status.HTTP_200_OK, summary="Получить все анализы вакансии")
async def get_all_vacancy_analyses(
    id_vacancy: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VacancyListResponse:
    """
    Возвращает все анализы вакансии по id вакансии.
    """
    logger.info(f"Запрос на получение анализов вакансии {id_vacancy} пользователя {current_user.id}")

    # Проверяем что вакансия существует, активна и связана с пользователем
    vacancy = await db.scalar(
        select(VacancyModel.id)
        .join(UserVacanciesModel)
        .where(
            UserVacanciesModel.user_id == current_user.id,
            VacancyModel.id == id_vacancy,
            UserVacanciesModel.is_active.is_(True),
        )
    )

    if not vacancy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vacancy not found")

    result = await db.scalars(
        select(VacancyAnalysisModel).where(
            VacancyAnalysisModel.vacancy_id == id_vacancy, VacancyAnalysisModel.user_id == current_user.id
        )
    )

    analyses = result.all()

    # Собираем уникальные типы анализов
    analyses_types = list({AnalysisType(analysis.analysis_type) for analysis in analyses})

    return VacancyListResponse(
        items=[VacancyBaseResponse.model_validate(analysis) for analysis in analyses], analyses_types=analyses_types
    )


@router.post("", status_code=status.HTTP_201_CREATED, summary="Создать анализ вакансии")
async def create_vacancy_analysis(
    id_vacancy: UUID,
    data: VacancyAnalysisCreate,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    llm: AsyncOpenAILLM = Depends(get_researcher_llm),
) -> VacancyResponse:
    """
    Создает анализ вакансии по заданному типу.

    Для типа CUSTOM обязательно указать custom_prompt и title.
    Для системных типов title генерируется автоматически.

    Типы анализов:
    - matching: Анализ соответствия кандидата вакансии.
    - prioritization: Оценка привлекательности вакансии для отклика
    - preparation: Подготовка к собеседованию
    - skill_gap: Анализ пробелов в навыках
    - custom: Пользовательский промпт
    """
    if data.analysis_type == AnalysisType.CUSTOM:
        if not data.custom_prompt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="custom_prompt is required for CUSTOM type"
            )
        if not data.title:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="title is required for CUSTOM type")
        title = data.title
    else:
        # Системные анализы - title из enum
        title = data.analysis_type.display_name

    # Проверяем существующий анализ у этого пользователя
    is_exists = await db.scalar(
        select(VacancyAnalysisModel.id).where(
            VacancyAnalysisModel.vacancy_id == id_vacancy,
            VacancyAnalysisModel.analysis_type == data.analysis_type,
            VacancyAnalysisModel.user_id == current_user.id,
        )
    )

    if is_exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"Analysis {data.analysis_type.value} already exists"
        )

    resume = current_user.resume

    if resume is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Resume not found. Please upload your resume first.",
        )

    if len(resume) < MIN_SIZE_RESUME:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Resume is too short. Minimum {MIN_SIZE_RESUME} characters required.",
        )

    try:
        result, prompt_template = await analyze_vacancy_from_db(
            llm=llm,
            vacancy_id=id_vacancy,
            analysis_type=data.analysis_type,
            custom_prompt=data.custom_prompt if data.custom_prompt else None,
            user_id=current_user.id,
            resume=current_user.resume,
            session=db,
        )
    except VacancyNotFoundError as e:
        logger.warning(f"Vacancy not found: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except UserNotFoundException as e:
        logger.warning(f"User not found: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found") from None
    except InvalidAnalysisTypeError as e:
        logger.warning(f"Invalid analysis type: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except LLMGenerationError as e:
        logger.error(f"LLM error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI service error. Please try again later."
        ) from None
    except Exception as e:
        logger.error(f"Unexpected error during analysis: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from None

    analysis = VacancyAnalysisModel(
        vacancy_id=id_vacancy,
        user_id=current_user.id,
        title=title,
        analysis_type=data.analysis_type,
        prompt_template=prompt_template,
        custom_prompt=data.custom_prompt,
        result_text=result,
    )
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)

    return VacancyResponse.model_validate(analysis)


@router.get("/types", status_code=status.HTTP_200_OK, summary="Получить доступные типы анализов")
async def get_available_analysis_types() -> AvailableAnalysesResponse:
    """
    Возвращает список всех доступных типов анализов вакансий.
    Используется для отображения опций в UI.
    """
    items = [
        AnalysisTypeInfo(
            value=analysis_type.value,
            display_name=analysis_type.display_name,
            description=analysis_type.description,
            is_builtin=analysis_type in AnalysisType.builtin_types(),
        )
        for analysis_type in AnalysisType
    ]

    return AvailableAnalysesResponse(items=items)
