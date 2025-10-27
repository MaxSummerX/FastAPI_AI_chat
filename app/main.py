from fastapi import FastAPI


# Создаём приложение FastAPI
app = FastAPI(title="AI chat", version="0.1.0")


@app.get("/", tags=["root"])
async def root() -> dict:
    """
    Корневой тестовый endpoint, для проверки работы API
    """
    return {"message": "Добро пожаловать"}
