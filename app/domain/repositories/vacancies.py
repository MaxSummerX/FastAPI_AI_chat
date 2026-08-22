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
