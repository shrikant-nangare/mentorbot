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
# - "openai-chat": OpenAI-compatible POST /v1/chat/completions (default)
# - "openai-completions": OpenAI-compatible POST /v1/completions (e.g. llama.cpp server)
LLM_API_STYLE: str = _getenv_str("MENTORBOT_LLM_API_STYLE", _getenv_str("LLM_API_STYLE", "openai-chat")).strip().lower()
LLM_BASE_URL: str = _getenv_str(
    "MENTORBOT_LLM_BASE_URL", _getenv_str("LLM_BASE_URL", "https://api.openai.com/v1")
).strip().rstrip("/")
LLM_MODEL: str = _getenv_str(
    "MENTORBOT_LLM_MODEL",
    _getenv_str("LLM_MODEL", "gpt-4o-mini"),
)
LLM_MAX_TOKENS: int = _getenv_int("MENTORBOT_LLM_MAX_TOKENS", _getenv_int("LLM_MAX_TOKENS", 512))
LLM_TEMPERATURE: float = _getenv_float("MENTORBOT_LLM_TEMPERATURE", _getenv_float("LLM_TEMPERATURE", 0.2))
LLM_TIMEOUT_S: float = _getenv_float("MENTORBOT_LLM_TIMEOUT_S", _getenv_float("LLM_TIMEOUT_S", 20.0))
_OPENAI_API_KEY: str = _getenv_str("OPENAI_API_KEY", "")
_LLM_API_KEY_OVERRIDE: str = _getenv_str("MENTORBOT_LLM_API_KEY", "")
LLM_API_KEY: str = _LLM_API_KEY_OVERRIDE if _LLM_API_KEY_OVERRIDE else _OPENAI_API_KEY

# Embeddings: OpenAI-compatible POST /v1/embeddings (base URL often matches LLM_BASE_URL).
EMBEDDINGS_BASE_URL: str = _getenv_str("MENTORBOT_EMBEDDINGS_BASE_URL", "").strip().rstrip("/")
EMBEDDINGS_MODEL: str = _getenv_str("MENTORBOT_EMBEDDINGS_MODEL", "text-embedding-3-small").strip()
_EMB_API_KEY_OVERRIDE: str = _getenv_str("MENTORBOT_EMBEDDINGS_API_KEY", "")
EMBEDDINGS_API_KEY: str = _EMB_API_KEY_OVERRIDE if _EMB_API_KEY_OVERRIDE else LLM_API_KEY

# Short timeout for HTTP reachability probes (health checks).
HTTP_CONNECT_TIMEOUT_S: float = _getenv_float("MENTORBOT_HTTP_CONNECT_TIMEOUT_S", 2.0)

# Optional headers some OpenAI-compatible providers accept (Referer / app title).
HTTP_REFERER_OPTIONAL: str = _getenv_str("MENTORBOT_HTTP_REFERER", "")
HTTP_TITLE_OPTIONAL: str = _getenv_str("MENTORBOT_HTTP_TITLE", "")

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
