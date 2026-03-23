import os
from urllib.parse import urlparse


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


def _getenv_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    v = raw.strip().lower()
    if v in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


# Storage
DB_DIR: str = _getenv_str("MENTORBOT_DB_DIR", "./db")

# Basic auth (HTTP Basic)
BASIC_AUTH_ENABLED: bool = _getenv_bool("MENTORBOT_BASIC_AUTH_ENABLED", False)
BASIC_AUTH_USERNAME: str = _getenv_str("MENTORBOT_BASIC_AUTH_USERNAME", "")
BASIC_AUTH_PASSWORD: str = _getenv_str("MENTORBOT_BASIC_AUTH_PASSWORD", "")

# LLM API style:
# - "ollama": native Ollama API via langchain-ollama (default)
# - "openai-completions": OpenAI-compatible /v1/completions servers (e.g. llama.cpp)
LLM_API_STYLE: str = _getenv_str("MENTORBOT_LLM_API_STYLE", _getenv_str("LLM_API_STYLE", "ollama")).strip().lower()
LLM_BASE_URL: str = _getenv_str("MENTORBOT_LLM_BASE_URL", _getenv_str("LLM_BASE_URL", "http://192.168.1.215:8080")).strip().rstrip("/")
LLM_MODEL: str = _getenv_str(
    "MENTORBOT_LLM_MODEL",
    _getenv_str("LLM_MODEL", "ggml-org/gemma-3-1b-it-GGUF"),
)
LLM_MAX_TOKENS: int = _getenv_int("MENTORBOT_LLM_MAX_TOKENS", _getenv_int("LLM_MAX_TOKENS", 512))
LLM_TEMPERATURE: float = _getenv_float("MENTORBOT_LLM_TEMPERATURE", _getenv_float("LLM_TEMPERATURE", 0.2))
LLM_TIMEOUT_S: float = _getenv_float("MENTORBOT_LLM_TIMEOUT_S", _getenv_float("LLM_TIMEOUT_S", 20.0))

# Ollama models
OLLAMA_EMBED_MODEL: str = _getenv_str("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_LLM_MODEL: str = _getenv_str("OLLAMA_LLM_MODEL", "gpt-oss:20b")
OLLAMA_LLM_FALLBACK_MODEL: str = _getenv_str("OLLAMA_LLM_FALLBACK_MODEL", "gpt-oss:20b")

# Preferred configuration: provide the full base URL, e.g. http://192.168.1.215:8080
_OLLAMA_BASE_URL_ENV = _getenv_str("OLLAMA_BASE_URL", "")
_OLLAMA_HOST_ENV = _getenv_str("OLLAMA_HOST", "")
_OLLAMA_PORT_ENV_RAW = os.getenv("OLLAMA_PORT")

_DEFAULT_OLLAMA_BASE_URL = "http://192.168.1.215:11434"
_base_url_candidate = _OLLAMA_BASE_URL_ENV or _DEFAULT_OLLAMA_BASE_URL
if "://" not in _base_url_candidate:
    _base_url_candidate = f"http://{_base_url_candidate}"

_parsed = urlparse(_base_url_candidate)
_parsed_host = _parsed.hostname or "192.168.1.215"
_parsed_port = _parsed.port or 11434

OLLAMA_BASE_URL: str = _base_url_candidate
OLLAMA_HOST: str = _OLLAMA_HOST_ENV or _parsed_host
OLLAMA_PORT: int = _getenv_int("OLLAMA_PORT", int(_parsed_port))
OLLAMA_CONNECT_TIMEOUT_S: float = _getenv_float("OLLAMA_CONNECT_TIMEOUT_S", 0.4)

# Retrieval
RETRIEVAL_K: int = _getenv_int("MENTORBOT_RETRIEVAL_K", 4)
RETRIEVAL_MIN_RELEVANCE: float = _getenv_float("MENTORBOT_RETRIEVAL_MIN_RELEVANCE", 0.25)

# Conversation
HISTORY_MAX_MESSAGES: int = _getenv_int("MENTORBOT_HISTORY_MAX_MESSAGES", 24)

# Quizzes
QUIZ_PASS_PERCENT: float = _getenv_float("MENTORBOT_QUIZ_PASS_PERCENT", 60.0)
