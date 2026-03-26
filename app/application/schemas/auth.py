from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    """
    Ответ с токенами после успешной аутентификации.

    Возвращается при логине пользователя, содержит access и refresh JWT токены.
    """

    access_token: str = Field(..., description="JWT access токен для API запросов")
    refresh_token: str = Field(..., description="JWT refresh токен для обновления access токена")
    token_type: str = Field(default="bearer", description="Тип токена (всегда bearer)")
    expires_in: int = Field(..., description="Время жизни access токена в секундах")


class RefreshTokenResponse(BaseModel):
    """
    Ответ с обновлённым access токеном.

    Возвращается при обновлении токена через refresh токен.
    """

    access_token: str = Field(..., description="Новый JWT access токен")
    token_type: str = Field(default="bearer", description="Тип токена (всегда bearer)")
    expires_in: int = Field(..., description="Время жизни access токена в секундах")
