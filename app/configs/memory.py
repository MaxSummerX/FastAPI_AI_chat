import os
from pathlib import Path

from dotenv import load_dotenv
from mem0.configs.base import EmbedderConfig, LlmConfig, MemoryConfig, VectorStoreConfig
from mem0.graphs.configs import GraphStoreConfig, Neo4jConfig


# Загрузка переменных окружения
load_dotenv()

OPENROUTER_API_KEY = os.getenv("API_OPEN_ROUTER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
API_MEM0_ONLINE = os.getenv("API_MEM0_ONLINE")
MODEL_FOR_MEM0 = os.getenv("MODEL_FOR_MEMO")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

# Определяем корень проекта
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Создаём путь к директории для db mem0ai
STORAGE_DIR = PROJECT_ROOT / "app" / "storage" / "mem0ai"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Путь к конкретному файлу БД
history_db_path = STORAGE_DIR / "history.db"

# Проверяем наличие API ключа
if not API_MEM0_ONLINE:
    raise ValueError("MEM0_API_KEY не установлен")

# Конфигурация local mem0
custom_config = MemoryConfig(
    embedder=EmbedderConfig(
        provider="ollama",
        config={"model": "nomic-embed-text:latest", "embedding_dims": 768, "ollama_base_url": "http://localhost:11434"},
    ),
    llm=LlmConfig(
        provider="openai",
        config={
            "api_key": OPENROUTER_API_KEY,
            "model": MODEL_FOR_MEM0,
            "max_tokens": 8000,
            "temperature": 0.1,
            "openai_base_url": "https://openrouter.ai/api/v1",
        },
    ),
    vector_store=VectorStoreConfig(
        provider="qdrant",
        config={
            "url": "http://localhost:6333",
            "collection_name": "new_app",
            "embedding_model_dims": 768,
            "api_key": QDRANT_API_KEY,
            "on_disk": True,
        },
    ),
    graph_store=GraphStoreConfig(
        provider="neo4j",
        config=Neo4jConfig(
            url="bolt://localhost:7687", username="neo4j", password=NEO4J_PASSWORD, database="neo4j", base_label=False
        ),
    ),
    history_db_path=str(history_db_path),
    version="v1.1",
)
