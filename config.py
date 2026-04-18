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


def _parse_duration_seconds(value: str) -> int | None:
    """
    Parses values like '86400', '30s', '15m', '24h', '7d' into seconds.
    Returns None if parsing fails.
    """
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    try:
        if raw.isdigit():
            return int(raw)
        unit = raw[-1]
        n = int(raw[:-1])
        if unit == "s":
            return n
        if unit == "m":
            return n * 60
        if unit == "h":
            return n * 60 * 60
        if unit == "d":
            return n * 24 * 60 * 60
    except Exception:
        return None
    return None


def _getenv_duration_s(name: str, default_seconds: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return int(default_seconds)
    parsed = _parse_duration_seconds(raw)
    return int(default_seconds) if parsed is None else int(parsed)


# Storage
DB_DIR: str = _getenv_str("MENTORBOT_DB_DIR", "./db")

# Application DB (students, quizzes, notes, groups, reports)
APP_DB_PATH: str = _getenv_str("MENTORBOT_APP_DB_PATH", f"{DB_DIR.rstrip('/')}/mentorbot-app.sqlite3")
SESSION_TTL_S: int = _getenv_duration_s("MENTORBOT_SESSION_TTL", 7 * 24 * 60 * 60)  # 7 days

# Persistent cache (stored on DB_DIR/PVC by default)
CACHE_ENABLED: bool = _getenv_bool("MENTORBOT_CACHE_ENABLED", True)
CACHE_TTL_S: int = _getenv_int("MENTORBOT_CACHE_TTL_S", 7 * 24 * 60 * 60)  # 7 days
CACHE_MAX_ENTRIES: int = _getenv_int("MENTORBOT_CACHE_MAX_ENTRIES", 5000)
CACHE_PATH: str = _getenv_str("MENTORBOT_CACHE_PATH", f"{DB_DIR.rstrip('/')}/mentorbot-cache.sqlite3")
CACHE_RETRIEVAL_ENABLED: bool = _getenv_bool("MENTORBOT_CACHE_RETRIEVAL_ENABLED", True)

# Chat logs (daily JSONL logs on DB_DIR/PVC by default)
CHAT_LOG_ENABLED: bool = _getenv_bool("MENTORBOT_CHAT_LOG_ENABLED", True)
CHAT_LOG_DIR: str = _getenv_str("MENTORBOT_CHAT_LOG_DIR", f"{DB_DIR.rstrip('/')}/chat_logs")

# Basic auth (HTTP Basic)
BASIC_AUTH_ENABLED: bool = _getenv_bool("MENTORBOT_BASIC_AUTH_ENABLED", False)
BASIC_AUTH_USERNAME: str = _getenv_str("MENTORBOT_BASIC_AUTH_USERNAME", "")
BASIC_AUTH_PASSWORD: str = _getenv_str("MENTORBOT_BASIC_AUTH_PASSWORD", "")

# LLM API style:
# - "ollama": native Ollama API via langchain-ollama (default)
# - "openai-completions": OpenAI-compatible /v1/completions servers (e.g. llama.cpp)
# - "openai-chat": OpenAI-compatible /v1/chat/completions (e.g. OpenRouter)
LLM_API_STYLE: str = _getenv_str("MENTORBOT_LLM_API_STYLE", _getenv_str("LLM_API_STYLE", "ollama")).strip().lower()
LLM_BASE_URL: str = _getenv_str("MENTORBOT_LLM_BASE_URL", _getenv_str("LLM_BASE_URL", "http://192.168.1.215:8080")).strip().rstrip("/")
LLM_MODEL: str = _getenv_str(
    "MENTORBOT_LLM_MODEL",
    _getenv_str("LLM_MODEL", "ggml-org/gpt-oss-20b-GGUF"),
)
LLM_MAX_TOKENS: int = _getenv_int("MENTORBOT_LLM_MAX_TOKENS", _getenv_int("LLM_MAX_TOKENS", 512))
LLM_TEMPERATURE: float = _getenv_float("MENTORBOT_LLM_TEMPERATURE", _getenv_float("LLM_TEMPERATURE", 0.2))
LLM_TIMEOUT_S: float = _getenv_float("MENTORBOT_LLM_TIMEOUT_S", _getenv_float("LLM_TIMEOUT_S", 20.0))
_OPENAI_API_KEY: str = _getenv_str("OPENAI_API_KEY", "")
_OPENROUTER_API_KEY: str = _getenv_str("OPENROUTER_API_KEY", "")
_LLM_API_KEY_OVERRIDE: str = _getenv_str("MENTORBOT_LLM_API_KEY", "")

# Pick the right key for the configured base URL.
_llm_base_url_lower = (LLM_BASE_URL or "").lower()
if _LLM_API_KEY_OVERRIDE:
    LLM_API_KEY: str = _LLM_API_KEY_OVERRIDE
elif "api.openai.com" in _llm_base_url_lower:
    LLM_API_KEY = _OPENAI_API_KEY
elif "openrouter.ai" in _llm_base_url_lower:
    LLM_API_KEY = _OPENROUTER_API_KEY
else:
    # Reasonable default if using another OpenAI-compatible provider.
    LLM_API_KEY = _OPENAI_API_KEY or _OPENROUTER_API_KEY
OPENROUTER_SITE_URL: str = _getenv_str("OPENROUTER_SITE_URL", "")
OPENROUTER_APP_NAME: str = _getenv_str("OPENROUTER_APP_NAME", "mentorbot")

# Embeddings provider (can be Ollama or OpenAI-compatible /v1/embeddings, e.g. OpenRouter)
EMBEDDINGS_API_STYLE: str = _getenv_str("MENTORBOT_EMBEDDINGS_API_STYLE", "").strip().lower()
EMBEDDINGS_BASE_URL: str = _getenv_str("MENTORBOT_EMBEDDINGS_BASE_URL", "").strip().rstrip("/")
EMBEDDINGS_MODEL: str = _getenv_str("MENTORBOT_EMBEDDINGS_MODEL", "text-embedding-3-small").strip()
_EMB_API_KEY_OVERRIDE: str = _getenv_str("MENTORBOT_EMBEDDINGS_API_KEY", "")
_emb_base_url = (EMBEDDINGS_BASE_URL or LLM_BASE_URL or "").lower()
if _EMB_API_KEY_OVERRIDE:
    EMBEDDINGS_API_KEY: str = _EMB_API_KEY_OVERRIDE
elif "api.openai.com" in _emb_base_url:
    EMBEDDINGS_API_KEY = _OPENAI_API_KEY
elif "openrouter.ai" in _emb_base_url:
    EMBEDDINGS_API_KEY = _OPENROUTER_API_KEY
else:
    EMBEDDINGS_API_KEY = _OPENAI_API_KEY or _OPENROUTER_API_KEY

# Ollama models
OLLAMA_EMBED_MODEL: str = _getenv_str("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_LLM_MODEL: str = _getenv_str("OLLAMA_LLM_MODEL", "gpt-oss:20b")
OLLAMA_LLM_FALLBACK_MODEL: str = _getenv_str("OLLAMA_LLM_FALLBACK_MODEL", "gpt-oss:20b")
# Use seconds for compatibility across clients (some expect int).
OLLAMA_KEEP_ALIVE_S: int = _getenv_duration_s("OLLAMA_KEEP_ALIVE", 24 * 60 * 60)
# Optional performance caps. Set to 0/empty to leave uncapped.
OLLAMA_NUM_PREDICT: int = _getenv_int("OLLAMA_NUM_PREDICT", 0)
OLLAMA_NUM_CTX: int = _getenv_int("OLLAMA_NUM_CTX", 0)

# Preferred configuration: provide the full base URL, e.g. http://192.168.1.215:8080
_OLLAMA_BASE_URL_ENV = _getenv_str("OLLAMA_BASE_URL", "")
_OLLAMA_HOST_ENV = _getenv_str("OLLAMA_HOST", "")
_OLLAMA_PORT_ENV_RAW = os.getenv("OLLAMA_PORT")

_DEFAULT_OLLAMA_BASE_URL = "http://192.168.1.191:11434"
_base_url_candidate = _OLLAMA_BASE_URL_ENV or _DEFAULT_OLLAMA_BASE_URL
if "://" not in _base_url_candidate:
    _base_url_candidate = f"http://{_base_url_candidate}"

_parsed = urlparse(_base_url_candidate)
_parsed_host = _parsed.hostname or "192.168.1.191"
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
QUIZ_PASS_PERCENT: float = _getenv_float("MENTORBOT_QUIZ_PASS_PERCENT", 70.0)
QUIZ_SKIP_PER_DAY: int = _getenv_int("MENTORBOT_QUIZ_SKIP_PER_DAY", 5)

# Parent/Admin PIN (optional bootstrap; if unset, can be set in UI)
PARENT_PIN: str = _getenv_str("MENTORBOT_PARENT_PIN", "")
