import os
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from mem0.configs.base import EmbedderConfig, LlmConfig, MemoryConfig, VectorStoreConfig
from mem0.graphs.configs import GraphStoreConfig, Neo4jConfig


# Загрузка переменных окружения
load_dotenv()

# Openrouter env
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Neo4j env
NEO4J_BASE_URL = os.getenv("NEO4J_BASE_URL", "bolt://neo4j:7687")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# mem0ai env
API_MEM0_ONLINE = os.getenv("API_MEM0_ONLINE")
MODEL_FOR_MEM0 = os.getenv("MODEL_FOR_MEMO")

# Qdrant env
QDRANT_BASE_URL = os.getenv("QDRANT_BASE_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "main_app")

# Ollama env
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text:latest")
EMBEDDING_DIMS = int(os.getenv("EMBEDDING_DIMS", "768"))

# Проверяем наличие API ключа
if not API_MEM0_ONLINE:
    logger.error("API_MEM0_ONLINE не установлен в environment variables")
    raise ValueError("API_MEM0_ONLINE is required")

if not OPENROUTER_API_KEY:
    logger.error("API_OPEN_ROUTER не установлен в environment variables")
    raise ValueError("OPENROUTER_API_KEY is required")

# Определяем корень проекта
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Создаём путь к директории для db mem0ai
STORAGE_DIR = PROJECT_ROOT / "storage" / "mem0ai"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Путь к конкретному файлу БД
history_db_path = STORAGE_DIR / "history.db"

# Логирование конфигурации
logger.info(f"Ollama URL: {OLLAMA_BASE_URL}")
logger.info(f"Qdrant URL: {QDRANT_BASE_URL}")
logger.info(f"Neo4j URL: {NEO4J_BASE_URL}")
logger.info(f"Embedding model: {OLLAMA_EMBEDDING_MODEL}")
logger.info(f"Embedding dims: {EMBEDDING_DIMS}")
logger.info(f"Qdrant collection: {QDRANT_COLLECTION_NAME}")
logger.info(f"History DB path: {history_db_path}")


# Конфигурация local mem0


def create_memory_config() -> MemoryConfig:
    """
    Создаёт конфигурацию системы памяти на основе environment variables.
    """
    try:
        config = MemoryConfig(
            # Конфигурация embedding модели (Ollama)
            embedder=EmbedderConfig(
                provider="ollama",
                config={
                    "model": OLLAMA_EMBEDDING_MODEL,
                    "embedding_dims": EMBEDDING_DIMS,
                    "ollama_base_url": OLLAMA_BASE_URL,
                },
            ),
            # Конфигурация LLM (OpenRouter)
            llm=LlmConfig(
                provider="openai",
                config={
                    "api_key": OPENROUTER_API_KEY,
                    "model": MODEL_FOR_MEM0,
                    "max_tokens": 8000,
                    "temperature": 0.1,
                    "openai_base_url": OPENROUTER_BASE_URL,
                },
            ),
            # Конфигурация векторного хранилища (Qdrant)
            vector_store=VectorStoreConfig(
                provider="qdrant",
                config={
                    "url": QDRANT_BASE_URL,
                    "collection_name": QDRANT_COLLECTION_NAME,
                    "embedding_model_dims": EMBEDDING_DIMS,
                    "api_key": QDRANT_API_KEY,
                    "on_disk": True,
                },
            ),
            # Конфигурация графового хранилища (Neo4j)
            graph_store=GraphStoreConfig(
                provider="neo4j",
                config=Neo4jConfig(
                    url=NEO4J_BASE_URL,
                    username=NEO4J_USERNAME,
                    password=NEO4J_PASSWORD,
                    database=NEO4J_DATABASE,
                    base_label=False,
                ),
            ),
            # Путь к истории
            history_db_path=str(history_db_path),
            version="v1.1",
        )

        logger.info("Конфигурация mem0ai успешно создана")
        return config

    except Exception as e:
        logger.error(f"Ошибка при создании конфигурации mem0ai: {e}")
        raise ValueError(f"Failed to create memory config: {e}") from e


# Создаём и экспортируем конфигурацию
custom_config = create_memory_config()
