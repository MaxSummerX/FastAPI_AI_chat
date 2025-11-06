import os

from dotenv import load_dotenv

from app.configs.llms.openai import OpenAIConfig


load_dotenv()

base_config_for_llm = OpenAIConfig(
    model=os.getenv("MODEL"),
    temperature=0.6,
    api_key=os.getenv("OPENROUTER_API_KEY"),
    max_tokens=2000,
)
