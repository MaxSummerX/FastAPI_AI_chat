from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Игнорировать лишние поля из .env
    )

    cors_production: list[str] = [
        "https://mydomain.com",
    ]  # В продакшене нужны конкретные домены

    cors_development: list[str] = [
        "http://localhost:3000",  # React/Vue/Angular dev сервер
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
        "http://192.168.3.61:3000",
        "http://192.168.3.61",
    ]

    debug: bool = True

    @property
    def is_development(self) -> bool:
        return self.debug

    @property
    def cors_origins_list(self) -> list[str]:
        if self.is_development:
            return self.cors_development
        return self.cors_production


settings = Settings()
