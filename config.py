import os


def _getenv_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or not value.strip() else value.strip()


def _getenv_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except Exception:
        return default


def _getenv_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except Exception:
        return default


# Storage
DB_DIR: str = _getenv_str("MENTORBOT_DB_DIR", "./db")

# Ollama models
OLLAMA_EMBED_MODEL: str = _getenv_str("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_LLM_MODEL: str = _getenv_str("OLLAMA_LLM_MODEL", "gpt-oss:latest")
OLLAMA_LLM_FALLBACK_MODEL: str = _getenv_str("OLLAMA_LLM_FALLBACK_MODEL", "llama3:latest")
OLLAMA_HOST: str = _getenv_str("OLLAMA_HOST", "127.0.0.1")
OLLAMA_PORT: int = _getenv_int("OLLAMA_PORT", 11434)
OLLAMA_CONNECT_TIMEOUT_S: float = _getenv_float("OLLAMA_CONNECT_TIMEOUT_S", 0.4)

# Retrieval
RETRIEVAL_K: int = _getenv_int("MENTORBOT_RETRIEVAL_K", 4)
RETRIEVAL_MIN_RELEVANCE: float = _getenv_float("MENTORBOT_RETRIEVAL_MIN_RELEVANCE", 0.25)

# Conversation
HISTORY_MAX_MESSAGES: int = _getenv_int("MENTORBOT_HISTORY_MAX_MESSAGES", 24)

# Quizzes
QUIZ_PASS_PERCENT: float = _getenv_float("MENTORBOT_QUIZ_PASS_PERCENT", 60.0)
