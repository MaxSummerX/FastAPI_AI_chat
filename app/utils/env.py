import os


def get_required_env(key: str) -> str:
    """Получает обязательную переменную окружения."""

    value = os.getenv(key)
    if value is None:
        raise ValueError(f"{key} must be set in the environment configuration file")
    return value
