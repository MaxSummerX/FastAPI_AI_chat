"""
Настройки приложения.

Pydantic Settings для типизированной конфигурации с автозагрузкой из .env.
Находится в infrastructure слое, так как зависит от внешнего окружения.
"""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


# Корень проекта
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Игнорировать лишние поля из .env
        case_sensitive=False,
    )
    # База данных
    DATABASE_URL: str = Field(..., description="Строка подключения к БД(postgresql/mysql/sqlite)")
    # Секреты
    SECRET_KEY: SecretStr = Field(..., description="Секретный ключ для JWT токенов")
    ALGORITHM: str = Field(default="HS256", description="Алгоритм шифрования JWT")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, description="Время жизни access токена в минутах")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, description="Время жизни refresh токена в днях")
    # Приложение
    DEBUG: bool = Field(default=False, description="Режим отладки")
    API_PREFIX: str = Field(default="/api/v2", description="Префикс API")
    # Включить инвайты для регистрации
    REQUIRE_INVITE: bool = Field(
        default=False,
        description="Требовать инвайт-код для регистрации (True - только по инвайтам, False - открытая регистрация)",
    )

    # CORS
    CORS_PRODUCTION: list[str] = Field(
        default=["https://mydomain.com"],  # В продакшене нужны конкретные домены
        description="CORS origins для production",
    )
    CORS_DEVELOPMENT: list[str] = Field(
        default=[
            "http://localhost:3000",  # React/Vue/Angular dev сервер
            "http://localhost:8080",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8000",
            "http://192.168.3.61:3000",
            "http://192.168.3.61",
        ],
        description="CORS origins для development",
    )

    @property
    def is_development(self) -> bool:
        """Проверка режима разработки."""
        return self.DEBUG

    @property
    def cors_origins_list(self) -> list[str]:
        """Текущие CORS origins в зависимости от режима."""
        if self.is_development:
            return self.CORS_DEVELOPMENT
        return self.CORS_PRODUCTION


settings = Settings()
