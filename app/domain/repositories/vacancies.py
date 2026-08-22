"""
Репозитории вакансий.

Интерфейсы для работы с вакансиями в соответствии с принципами clean architecture.
Определяют контракт для чтения, дедупликации, массового импорта и архивирования вакансий.
"""

from abc import ABC, abstractmethod
from uuid import UUID

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
    async def get_existing_hh_ids(self, hh_ids: list[str]) -> set[str]:
        """
        Получить множество hh_id, уже существующих в базе.

        Используется для дедупликации при импорте вакансий с hh.ru.

        Args:
            hh_ids: Список идентификаторов вакансий на hh.ru

        Returns:
            Множество hh_id, которые уже есть в базе
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
    async def get_active_hh_ids(self) -> set[str]:
        """
        Получить hh_id всех неархивированных вакансий.

        Используется для проверки актуальности статусов на hh.ru.

        Returns:
            Множество hh_id неархивированных вакансий
        """
        pass

    @abstractmethod
    async def bulk_save_with_links(
        self,
        vacancies: list[Vacancy],
        links: list[UserVacancies],
    ) -> None:
        """
        Сохранить пакет вакансий и связей user<->vacancy одной транзакцией.

        Args:
            vacancies: Список объектов Vacancy для создания
            links: Список объектов UserVacancies для создания связей
        """
        pass

    @abstractmethod
    async def archive_by_hh_ids(self, hh_ids: list[str]) -> int:
        """
        Архивировать вакансии по списку hh_id.

        Args:
            hh_ids: Список идентификаторов вакансий на hh.ru

        Returns:
            Количество заархивированных записей
        """
        pass
