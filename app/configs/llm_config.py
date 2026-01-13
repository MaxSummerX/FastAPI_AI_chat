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

parse_llm_config = OpenAIConfig(
    model=os.getenv("MODEL"),
    temperature=0.1,
    api_key=os.getenv("OPENROUTER_API_KEY"),
    max_tokens=500,
)


researcher_llm_config = OpenAIConfig(
    model=os.getenv("MODEL"),
    temperature=0.4,
    api_key=os.getenv("OPENROUTER_API_KEY"),
    max_tokens=3000,
    top_p=0.2,
    top_k=5,
)
