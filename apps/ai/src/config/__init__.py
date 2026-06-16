"""Configuration module for AI services."""

from .llm import (
    get_llm_client,
    get_chat_model,
    get_embedding_model,
    reset_client,
    chat_completion_stream,
    chat_completion_stream_async,
)
from .llm_guard import enforce_llm_factory, scan_directory_for_violations
from .config_module import (
    Config,
    TemporalConfig,
    OpenRouterConfig,
    QdrantConfig,
    LoggingConfig,
    TelegramConfig,
    AppConfig,
    get_config,
    load_config,
)

# Backward compatibility alias
get_model = get_chat_model

__all__ = [
    "get_llm_client",
    "get_chat_model",
    "get_embedding_model",
    "get_model",  # Backward compatibility
    "reset_client",
    "enforce_llm_factory",
    "scan_directory_for_violations",
    # Config classes
    "Config",
    "TemporalConfig",
    "OpenRouterConfig",
    "QdrantConfig",
    "LoggingConfig",
    "TelegramConfig",
    "AppConfig",
    "get_config",
    "load_config",
]
