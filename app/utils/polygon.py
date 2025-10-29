import os

from dotenv import load_dotenv
from fastapi import APIRouter

from app.configs.llms.openai import OpenAIConfig
from app.llms.openai import AsyncOpenAILLM


load_dotenv()

polygon_func = APIRouter(prefix="/polygon", tags=["polygon"])

config = OpenAIConfig(
    model=os.getenv("MODEL"),
    temperature=0.6,
    api_key=os.getenv("OPENROUTER_API_KEY"),
    max_tokens=1000,
)


llm = AsyncOpenAILLM(config)


@polygon_func.post("/chat")
async def chat(message: str) -> dict:
    response = await llm.generate_response([{"role": "user", "content": message}])
    return {"response": response}
