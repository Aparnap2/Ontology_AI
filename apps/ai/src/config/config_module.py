"""Configuration management for AI Worker."""

import os
from pathlib import Path
from typing import Optional

import structlog
import yaml
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class TemporalConfig(BaseModel):
    """Temporal server configuration."""

    host: str = "localhost"
    port: int = 7233
    namespace: str = "default"
    task_queue: str = "AI_TASK_QUEUE"

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"


class OpenRouterConfig(BaseModel):
    """OpenRouter LLM configuration (OpenAI-compatible)."""

    base_url: str = "https://openrouter.ai/api/v1"
    api_key: str = ""
    model: str = "nvidia/nemotron-3-super-120b-a12b:free"
    embedding_model: str = "nvidia/llama-nemotron-embed-vl-1b-v2:free"


class QdrantConfig(BaseModel):
    """Qdrant vector database configuration."""

    url: str = "http://localhost:6333"
    collection: str = "feedback_items"
    similarity_threshold: float = 0.85


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    format: str = "json"


class TelegramConfig(BaseModel):
    """Telegram mock server configuration."""

    api_base: str = "http://localhost:8085"
    bot_token: str = "test-bot-token"
    chat_id: str = "ontology_ai-alerts"


class AppConfig(BaseModel):
    """Application configuration."""

    name: str = "iterateswarm-ai"
    environment: str = "development"


class Config(BaseModel):
    """Main configuration container."""

    temporal: TemporalConfig = TemporalConfig()
    openrouter: OpenRouterConfig = OpenRouterConfig()
    qdrant: QdrantConfig = QdrantConfig()
    telegram: TelegramConfig = TelegramConfig()
    logging: LoggingConfig = LoggingConfig()
    app: AppConfig = AppConfig()


def load_config(config_path: Optional[str] = None) -> Config:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config.yaml. If None, looks in current directory.

    Returns:
        Config object with all settings.
    """
    if config_path is None:
        search_paths = [
            Path.cwd() / "config.yaml",
            Path(__file__).parent.parent / "config.yaml",
            Path(__file__).parent.parent.parent / "config.yaml",
        ]
        for path in search_paths:
            if path.exists():
                config_path = str(path)
                break

    if config_path and Path(config_path).exists():
        logger.info("Loading configuration", path=config_path)
        with open(config_path) as f:
            config_dict = yaml.safe_load(f)
            return Config(**config_dict)

    logger.info("Using default configuration")
    return Config()


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
