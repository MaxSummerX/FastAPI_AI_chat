"""
Репозитории вакансий.

Интерфейсы для работы с вакансиями в соответствии с принципами clean architecture.
Определяют контракт для чтения, дедупликации, массового импорта и архивирования вакансий.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from uuid import UUID

from app.domain.enums.experience import Experience, OrderField
from app.domain.models.user_vacancies import UserVacancies
from app.domain.models.vacancy import Vacancy


class IVacancyRepository(ABC):
    """
    Интерфейс репозитория для работы с вакансиями.

    Определяет контракт для управления вакансиями и их связями с пользователями:
    чтение с проверкой владения, дедупликация по hh_id,
    массовый импорт и архивирование.
    """

    @abstractmethod
    async def get_active_user_vacancy(self, user_id: UUID, vacancy_id: UUID) -> Vacancy | None:
        """
        Получить активную вакансию пользователя по ID.

        Вакансия возвращается только если существует активная связь
        user_id <-> vacancy_id.

        Args:
            user_id: ID пользователя, связанного с вакансией
            vacancy_id: Уникальный идентификатор вакансии

        Returns:
            Объект Vacancy или None, если не найдена / нет связи / связь неактивна
        """
        pass

    @abstractmethod
    async def get_existing_hh_id_map(self, hh_ids: list[str]) -> dict[str, UUID]:
        """
        Получить мапу существующих в базе вакансий: hh_id -> внутренний ID.

        Используется для дедупликации при импорте и создания связей
        с уже существующими вакансиями.

        Args:
            hh_ids: Список идентификаторов вакансий на hh.ru

        Returns:
            Словарь {hh_id: id вакансии в базе}
        """
        pass

    @abstractmethod
    async def get_user_linked_hh_ids(self, user_id: UUID, hh_ids: list[str]) -> set[str]:
        """
        Получить множество hh_id вакансий, уже связанных с данным пользователем.

        Args:
            user_id: ID пользователя
            hh_ids: Список идентификаторов вакансий на hh.ru

        Returns:
            Множество hh_id из переданных, уже связанных с пользователем
        """
        pass

    @abstractmethod
    async def get_active_hh_ids(self, published_older: timedelta | None = None) -> set[str]:
        """
        Получить hh_id не архивированных вакансий.

        Используется для проверки актуальности статусов на hh.ru.

        Args:
            published_older: если указано - получить вакансии, опубликованные
                             на hh.ru более N назад (по published_at)

        Returns:
            Множество hh_id не архивированных вакансий
        """
        pass

    @abstractmethod
    async def bulk_save_with_links(
        self,
        vacancies: list[Vacancy],
        links: list[UserVacancies],
        user_id: UUID,
    ) -> None:
        """
        Сохранить пакет вакансий и связей user<->vacancy одной транзакцией.

        Args:
            vacancies: Список объектов Vacancy для создания
            links: Список объектов UserVacancies для существующих вакансий
            user_id: ID пользователя для связей с новыми вакансиями
        """
        pass

    @abstractmethod
    async def update_archive_statuses(self, hh_ids: dict[str, bool]) -> int:
        """
        Пакетно обновить архивные статусы вакансий.

        Args:
            hh_ids: Словарь {hh_id: is_archived} — каждому hh_id своё значение
                    (включая разархивацию, если вакансия снова активна на hh.ru)

        Returns:
            Количество обновлённых записей
        """
        pass

    @abstractmethod
    async def get_by_hh_id(self, hh_id: str) -> Vacancy | None:
        """
        Найти вакансию по hh_id (без проверки владения).

        Returns:
            Вакансия или None
        """
        pass

    @abstractmethod
    async def get_user_vacancy_with_favorite(self, user_id: UUID, vacancy_id: UUID) -> tuple[Vacancy, bool] | None:
        """
        Получить активную вакансию пользователя с флагом избранного.

        Returns:
            Кортеж (Vacancy, is_favorite) или None
        """
        pass

    @abstractmethod
    async def paginate_user_vacancies(
        self,
        user_id: UUID,
        *,
        tier: list[Experience] | None = None,
        favorite: bool | None = None,
        order_by: OrderField | None = None,
        order_desc: bool = False,
        cursor: tuple[datetime, UUID] | None = None,
        limit: int,
    ) -> list[tuple[Vacancy, bool]]:
        """
        Постраничный список активных вакансий пользователя с флагом избранного.

        Args:
            user_id: ID пользователя
            tier: Фильтр по уровням опыта (None — все)
            favorite: Фильтр по избранному (None — все)
            order_by: Поле сортировки (None — created_at по убыванию)
            order_desc: Направление сортировки
            cursor: Составной ключ (created_at, id) для курсорной пагинации
            limit: Размер страницы (+1 элемент для определения has_next)

        Returns:
            Список кортежей (Vacancy, is_favorite)
        """
        pass

    @abstractmethod
    async def has_user_link(self, user_id: UUID, vacancy_id: UUID) -> bool:
        """
        Проверить существование связи user<->vacancy (любой активности).
        """
        pass

    @abstractmethod
    async def save_with_link(self, vacancy: Vacancy, user_id: UUID) -> None:
        """
        Сохранить новую вакансию и создать активную связь с пользователем.
        """
        pass

    @abstractmethod
    async def create_link(self, user_id: UUID, vacancy_id: UUID) -> None:
        """
        Создать активную связь пользователя с существующей вакансией.
        """
        pass

    @abstractmethod
    async def deactivate_user_link(self, user_id: UUID, vacancy_id: UUID) -> bool:
        """
        Деактивировать связь пользователя с вакансией (мягкое удаление).

        Returns:
            True если связь найдена и деактивирована
        """
        pass

    @abstractmethod
    async def set_favorite(self, user_id: UUID, vacancy_id: UUID, is_favorite: bool) -> bool:
        """
        Установить/снять избранное для связи user<->vacancy.

        Returns:
            True если связь найдена и обновлена
        """
        pass

    @abstractmethod
    async def rollback(self) -> None:
        """
        Откатить текущую транзакцию.

        Используется для восстановления после ошибок flush/commit
        (например, конфликт уникальности при параллельном импорте).
        """
        pass
