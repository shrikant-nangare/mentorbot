import json
import logging
import math
import re
import hashlib
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings, OllamaLLM

import config
from persistent_cache import CacheConfig, SqliteCache
from openai_compat_embeddings import OpenAICompatEmbeddings

logger = logging.getLogger(__name__)

_CACHE: SqliteCache | None = None


def _get_cache() -> SqliteCache | None:
    global _CACHE
    if not bool(getattr(config, "CACHE_ENABLED", False)):
        return None
    if _CACHE is not None:
        return _CACHE
    try:
        _CACHE = SqliteCache(
            CacheConfig(
                path=str(getattr(config, "CACHE_PATH", "")),
                ttl_s=int(getattr(config, "CACHE_TTL_S", 0)),
                max_entries=int(getattr(config, "CACHE_MAX_ENTRIES", 0)),
            )
        )
    except Exception:
        _CACHE = None
    return _CACHE


def _cache_key(prefix: str, payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    h = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return f"{prefix}:{h}"


def _http_ok(url: str, method: str = "GET") -> bool:
    try:
        headers = {"Accept": "application/json"}
        api_key = str(getattr(config, "LLM_API_KEY", "") or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = Request(url, headers=headers, method=method)
        with urlopen(req, timeout=float(config.OLLAMA_CONNECT_TIMEOUT_S)) as resp:
            status = getattr(resp, "status", 200)
            return 200 <= int(status) < 300
    except HTTPError as e:
        # If an endpoint requires auth, a 401/403 still proves reachability.
        if int(getattr(e, "code", 0)) in {401, 403}:
            return True
        return False
    except (URLError, ValueError, TimeoutError):
        return False
    except Exception:
        return False


def ollama_is_reachable() -> bool:
    base = str(config.OLLAMA_BASE_URL).rstrip("/")
    # Native Ollama reliably exposes GET /api/tags.
    return _http_ok(f"{base}/api/tags", method="GET")


def openai_completions_is_reachable() -> bool:
    base = str(config.LLM_BASE_URL).rstrip("/")
    if base.endswith("/v1"):
        return _http_ok(f"{base}/models", method="GET")
    return _http_ok(f"{base}/v1/models", method="GET")


def _ensure_ollama_reachable() -> None:
    if not ollama_is_reachable():
        raise RuntimeError(
            f"Ollama is not reachable at {config.OLLAMA_BASE_URL} ({config.OLLAMA_HOST}:{config.OLLAMA_PORT}). "
            f"Make sure you're pointing at the Ollama server URL (it must expose /api/tags and /api/embed). "
            f"If you're using Open WebUI (often :8080), the Ollama API is typically :11434."
        )


def _ensure_openai_completions_reachable() -> None:
    # For OpenAI/OpenRouter base URLs, "reachability" without a key often returns 401/403.
    # Provide a clearer error in that case.
    base = str(getattr(config, "LLM_BASE_URL", "") or "").strip()
    if ("api.openai.com" in base or "openrouter.ai" in base) and not str(getattr(config, "LLM_API_KEY", "") or "").strip():
        raise RuntimeError("OpenAI/OpenRouter API key is not configured (set OPENAI_API_KEY or MENTORBOT_LLM_API_KEY).")

    if not openai_completions_is_reachable():
        raise RuntimeError(
            f"LLM server is not reachable at {config.LLM_BASE_URL}. "
            f"For llama.cpp OpenAI-compatible mode this must expose GET /v1/models and POST /v1/completions."
        )


def _openai_headers() -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json", "Accept": "application/json"}
    api_key = str(getattr(config, "LLM_API_KEY", "") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # OpenRouter-specific optional metadata headers (safe for other providers too).
    site = str(getattr(config, "OPENROUTER_SITE_URL", "") or "").strip()
    title = str(getattr(config, "OPENROUTER_APP_NAME", "") or "").strip()
    if site:
        headers["HTTP-Referer"] = site
    if title:
        headers["X-Title"] = title
    return headers


def _invoke_openai_chat(prompt: str) -> str:
    """
    OpenAI-compatible chat completion endpoint.
    Works with OpenRouter when base_url is https://openrouter.ai/api/v1.
    """
    if not str(getattr(config, "LLM_API_KEY", "") or "").strip():
        raise RuntimeError("OpenAI API key is not configured (set OPENAI_API_KEY or MENTORBOT_LLM_API_KEY).")

    base = str(config.LLM_BASE_URL).rstrip("/")
    url = f"{base}/chat/completions" if base.endswith("/v1") else f"{base}/v1/chat/completions"
    payload = {
        "model": config.LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": float(config.LLM_TEMPERATURE),
    }
    max_tokens = int(config.LLM_MAX_TOKENS)
    # Some OpenAI models require max_completion_tokens instead of max_tokens.
    if "api.openai.com" in base.lower():
        payload["max_completion_tokens"] = max_tokens
    else:
        payload["max_tokens"] = max_tokens
    req = Request(url, data=json.dumps(payload).encode("utf-8"), headers=_openai_headers(), method="POST")
    try:
        with urlopen(req, timeout=float(config.LLM_TIMEOUT_S)) as resp:
            raw = resp.read().decode("utf-8")
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI chat request failed ({e.code}): {body}") from None
    data = json.loads(raw or "{}")
    choices = data.get("choices") or []
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(f"Unexpected /v1/chat/completions response: {data}")
    msg = choices[0].get("message") or {}
    content = msg.get("content", "")
    return str(content or "")


@lru_cache(maxsize=1)
def get_vectordb() -> Chroma:
    emb_style = str(getattr(config, "EMBEDDINGS_API_STYLE", "") or "").strip().lower()
    if emb_style in {"openai-embeddings", "openrouter-embeddings"}:
        base_url = (getattr(config, "EMBEDDINGS_BASE_URL", "") or getattr(config, "LLM_BASE_URL", "")).rstrip("/")
        api_key = str(getattr(config, "EMBEDDINGS_API_KEY", "") or getattr(config, "LLM_API_KEY", "")).strip()
        embedding_function = OpenAICompatEmbeddings(
            base_url=base_url,
            api_key=api_key,
            model=str(getattr(config, "EMBEDDINGS_MODEL", "text-embedding-3-small") or "text-embedding-3-small"),
            timeout_s=float(getattr(config, "LLM_TIMEOUT_S", 30.0)),
            extra_headers={
                "HTTP-Referer": str(getattr(config, "OPENROUTER_SITE_URL", "") or ""),
                "X-Title": str(getattr(config, "OPENROUTER_APP_NAME", "") or ""),
            },
        )
    else:
        embed_kwargs = {
            "model": config.OLLAMA_EMBED_MODEL,
            "base_url": config.OLLAMA_BASE_URL,
            "keep_alive": int(getattr(config, "OLLAMA_KEEP_ALIVE_S", 0) or 0),
        }
        num_ctx = int(getattr(config, "OLLAMA_NUM_CTX", 0) or 0)
        if num_ctx > 0:
            embed_kwargs["num_ctx"] = num_ctx
        embedding_function = OllamaEmbeddings(**embed_kwargs)
    return Chroma(
        persist_directory=config.DB_DIR,
        embedding_function=embedding_function,
    )


@lru_cache(maxsize=1)
def _get_llm_primary() -> OllamaLLM:
    llm_kwargs = {
        "model": config.OLLAMA_LLM_MODEL,
        "base_url": config.OLLAMA_BASE_URL,
        "keep_alive": int(getattr(config, "OLLAMA_KEEP_ALIVE_S", 0) or 0),
    }
    num_ctx = int(getattr(config, "OLLAMA_NUM_CTX", 0) or 0)
    num_predict = int(getattr(config, "OLLAMA_NUM_PREDICT", 0) or 0)
    if num_ctx > 0:
        llm_kwargs["num_ctx"] = num_ctx
    if num_predict > 0:
        llm_kwargs["num_predict"] = num_predict
    return OllamaLLM(**llm_kwargs)


@lru_cache(maxsize=1)
def _get_llm_fallback() -> OllamaLLM:
    if config.OLLAMA_LLM_FALLBACK_MODEL == config.OLLAMA_LLM_MODEL:
        return _get_llm_primary()
    llm_kwargs = {
        "model": config.OLLAMA_LLM_FALLBACK_MODEL,
        "base_url": config.OLLAMA_BASE_URL,
        "keep_alive": int(getattr(config, "OLLAMA_KEEP_ALIVE_S", 0) or 0),
    }
    num_ctx = int(getattr(config, "OLLAMA_NUM_CTX", 0) or 0)
    num_predict = int(getattr(config, "OLLAMA_NUM_PREDICT", 0) or 0)
    if num_ctx > 0:
        llm_kwargs["num_ctx"] = num_ctx
    if num_predict > 0:
        llm_kwargs["num_predict"] = num_predict
    return OllamaLLM(**llm_kwargs)


def _normalize_text_for_chat(text: str) -> str:
    t = text or ""
    replacements = {
        "\u201c": '"',
        "\u201d": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u2013": "-",
        "\u2014": "-",
        "\u00a0": " ",
        "½": "1/2",
        "¼": "1/4",
        "¾": "3/4",
        "⅓": "1/3",
        "⅔": "2/3",
    }
    for k, v in replacements.items():
        t = t.replace(k, v)
    return t


def _invoke_openai_completions(prompt: str) -> str:
    _ensure_openai_completions_reachable()
    base = str(config.LLM_BASE_URL).rstrip("/")
    url = f"{base}/completions" if base.endswith("/v1") else f"{base}/v1/completions"
    payload = {
        "model": config.LLM_MODEL,
        "prompt": prompt,
        "max_tokens": int(config.LLM_MAX_TOKENS),
        "temperature": float(config.LLM_TEMPERATURE),
    }
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=_openai_headers(),
        method="POST",
    )
    with urlopen(req, timeout=float(config.LLM_TIMEOUT_S)) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw or "{}")
    choices = data.get("choices") or []
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(f"Unexpected /v1/completions response: {data}")
    return str(choices[0].get("text", "") or "")


def _llm_invoke(prompt: str) -> str:
    cache = _get_cache()
    key: str | None = None
    if cache is not None:
        key = _cache_key(
            "llm",
            {
                "style": str(getattr(config, "LLM_API_STYLE", "")),
                "prompt": prompt,
                "ollama_base_url": str(getattr(config, "OLLAMA_BASE_URL", "")),
                "ollama_model": str(getattr(config, "OLLAMA_LLM_MODEL", "")),
                "ollama_keep_alive_s": int(getattr(config, "OLLAMA_KEEP_ALIVE_S", 0)),
                "ollama_num_ctx": int(getattr(config, "OLLAMA_NUM_CTX", 0)),
                "ollama_num_predict": int(getattr(config, "OLLAMA_NUM_PREDICT", 0)),
                "openai_base_url": str(getattr(config, "LLM_BASE_URL", "")),
                "openai_model": str(getattr(config, "LLM_MODEL", "")),
            },
        )
        hit = cache.get(key)
        if hit is not None:
            hit_text = str(hit)
            # Never serve cached empty responses; treat as a bad entry.
            if not hit_text.strip():
                try:
                    cache.delete(key)
                except Exception:
                    pass
            else:
                return hit_text

    style = (config.LLM_API_STYLE or "").strip().lower()
    if style in {"openai-chat", "openrouter"}:
        out = _normalize_text_for_chat(_invoke_openai_chat(prompt))
        if not out.strip():
            out = _normalize_text_for_chat(_invoke_openai_chat(prompt))
        if not out.strip():
            raise RuntimeError("LLM returned an empty response.")
        if cache is not None and key is not None:
            cache.set(key, out)
        return out

    if style in {"openai-completions", "openai", "llamacpp"}:
        out = _normalize_text_for_chat(_invoke_openai_completions(prompt))
        if not out.strip():
            # One retry in case the backend produced an empty completion.
            out = _normalize_text_for_chat(_invoke_openai_completions(prompt))
        if not out.strip():
            raise RuntimeError("LLM returned an empty response.")
        if cache is not None and key is not None:
            cache.set(key, out)
        return out

    try:
        _ensure_ollama_reachable()
        out = _normalize_text_for_chat(_get_llm_primary().invoke(prompt))
        if not out.strip():
            # One retry in case the backend produced an empty completion.
            out = _normalize_text_for_chat(_get_llm_primary().invoke(prompt))
        if not out.strip():
            raise RuntimeError("LLM returned an empty response.")
        if cache is not None and key is not None:
            cache.set(key, out)
        return out
    except Exception as e:
        msg = str(e).lower()
        model_missing = ("model" in msg and ("not found" in msg or "pull" in msg or "unknown" in msg))
        if model_missing and config.OLLAMA_LLM_FALLBACK_MODEL != config.OLLAMA_LLM_MODEL:
            logger.warning(
                "Primary Ollama model unavailable; falling back",
                extra={"primary_model": config.OLLAMA_LLM_MODEL, "fallback_model": config.OLLAMA_LLM_FALLBACK_MODEL},
            )
            _ensure_ollama_reachable()
            out = _normalize_text_for_chat(_get_llm_fallback().invoke(prompt))
            if not out.strip():
                out = _normalize_text_for_chat(_get_llm_fallback().invoke(prompt))
            if not out.strip():
                raise RuntimeError("LLM returned an empty response.")
            if cache is not None and key is not None:
                cache.set(key, out)
            return out
        raise


def _doc_source_label(metadata: dict | None) -> str:
    md = metadata or {}
    source = md.get("source") or md.get("file_path") or md.get("filename") or md.get("path") or ""
    page = md.get("page")
    if source and page is not None:
        return f"{source} (page {page})"
    if source:
        return str(source)
    if page is not None:
        return f"page {page}"
    return "unknown source"


def retrieve_context(query: str, k: int = 4, min_relevance: float = 0.25) -> tuple[str, list[dict]]:
    """
    Returns (context_text, sources).
    Filters low-relevance chunks to reduce topic drift.
    """
    sources: list[dict] = []
    context_chunks: list[str] = []

    cache = _get_cache() if bool(getattr(config, "CACHE_RETRIEVAL_ENABLED", True)) else None
    if cache is not None:
        rkey = _cache_key(
            "retrieval",
            {
                "query": query,
                "k": int(k),
                "min_relevance": float(min_relevance),
                "db_dir": str(config.DB_DIR),
                "embed_model": str(config.OLLAMA_EMBED_MODEL),
                "ollama_base_url": str(config.OLLAMA_BASE_URL),
            },
        )
        cached = cache.get_json(rkey)
        if isinstance(cached, dict) and isinstance(cached.get("context"), str) and isinstance(cached.get("sources"), list):
            return (str(cached["context"]), list(cached["sources"]))

    try:
        hits = get_vectordb().similarity_search_with_relevance_scores(query, k=k)
        # hits: list[tuple[Document, float]] where score is higher = more relevant (0..1)
        for doc, score in hits:
            if score is None or float(score) < float(min_relevance):
                continue
            label = _doc_source_label(getattr(doc, "metadata", None))
            text = (getattr(doc, "page_content", "") or "").strip()
            if not text:
                continue
            sources.append({"label": label, "relevance": float(score)})
            context_chunks.append(f"[{label} | relevance={float(score):.2f}]\n{text}")
    except Exception:
        # If embeddings/backend isn't available (common with completion-only servers),
        # degrade gracefully by returning no retrieval context.
        return ("", [])

    context_text = "\n\n---\n\n".join(context_chunks)
    if cache is not None:
        cache.set_json(rkey, {"context": context_text, "sources": sources})
    return (context_text, sources)


def _format_history(history: list[dict] | None) -> str:
    if not history:
        return ""

    lines: list[str] = []
    for msg in history[-12:]:
        role = str(msg.get("role", "")).strip().lower()
        content = str(msg.get("content", "")).strip()
        if not content:
            continue
        if role in {"assistant", "bot"}:
            lines.append(f"MentorBot: {content}")
        elif role in {"user", "human"}:
            lines.append(f"User: {content}")
        else:
            lines.append(f"{role or 'Message'}: {content}")
    return "\n".join(lines)


def _is_explain_request(question: str) -> bool:
    q = (question or "").strip().lower()
    if not q:
        return False

    # If it looks like a computation/exercise, treat it as problem-solving (not concept definition).
    # Examples: "what is 1/2+3/4?", "solve 9x + 2 = 11", "what is 3*7?"
    if re.search(r"\d", q) and re.search(r"[\+\-\*/=^]|(\d+\s*/\s*\d+)", q):
        return False

    # Direct concept explanation intents.
    if re.match(r"^(explain|define|describe|what is|what are|meaning of|tell me about)\b", q):
        return True

    # Short imperative (common in chat): "noun?" / "explain noun?"
    if q.endswith("?") and len(q.split()) <= 3:
        return True

    return False


def is_explain_request(question: str) -> bool:
    return _is_explain_request(question)


def _infer_problem_type(question: str) -> str:
    q = (question or "").lower()
    has_fraction = bool(re.search(r"\d+\s*/\s*\d+", q))
    if has_fraction and "+" in q:
        return "adding fractions"
    if has_fraction and "-" in q:
        return "subtracting fractions"
    if has_fraction:
        return "fractions"
    if re.search(r"\b(solve|equation)\b", q) or "=" in q:
        return "solving an equation"
    if re.search(r"\b(photosynthesis|evaporation|gravity|atom|cell|energy|force|electricity|ecosystem)\b", q):
        return "science concept"
    return "general problem"


_FRACTION_BINOP_RE = re.compile(r"(\d+)\s*/\s*(\d+)\s*([+\-])\s*(\d+)\s*/\s*(\d+)")


def _lcm(a: int, b: int) -> int:
    return abs(a * b) // math.gcd(a, b) if a and b else 0


def _format_fraction_steps_from_question(question: str) -> str | None:
    """
    Returns a deterministic, math-formatted step-by-step guide for a simple
    fraction expression like '1/2 + 3/4' (or with spaces), WITHOUT the final answer.
    """
    m = _FRACTION_BINOP_RE.search(question or "")
    if not m:
        return None

    n1, d1, op, n2, d2 = (int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4)), int(m.group(5)))
    if d1 == 0 or d2 == 0:
        return None

    lcd = _lcm(d1, d2)
    if lcd == 0:
        return None

    f1 = lcd // d1
    f2 = lcd // d2
    n1s = n1 * f1
    n2s = n2 * f2

    op_word = "add" if op == "+" else "subtract"

    # Important: do NOT compute the final numerator result.
    combined = f"{n1s}{op}{n2s}"

    return (
        f"To {op_word} fractions, first make the denominators match (same-sized pieces), then combine the numerators.\n\n"
        f"1. **Find a common denominator.**\n"
        f"   The denominators are \\({d1}\\) and \\({d2}\\). The least common denominator (LCD) is \\({lcd}\\).\n\n"
        f"2. **Rewrite each fraction with denominator \\({lcd}\\).**\n"
        f"   \\[\n"
        f"   \\frac{{{n1}}}{{{d1}}} = \\frac{{{n1}\\times {f1}}}{{{d1}\\times {f1}}} = \\frac{{{n1s}}}{{{lcd}}}\n"
        f"   \\]\n"
        f"   \\[\n"
        f"   \\frac{{{n2}}}{{{d2}}} = \\frac{{{n2}\\times {f2}}}{{{d2}\\times {f2}}} = \\frac{{{n2s}}}{{{lcd}}}\n"
        f"   \\]\n\n"
        f"3. **Combine over the common denominator.**\n"
        f"   \\[\n"
        f"   \\frac{{{n1}}}{{{d1}}} {op} \\frac{{{n2}}}{{{d2}}} = \\frac{{{n1s}}}{{{lcd}}} {op} \\frac{{{n2s}}}{{{lcd}}} = \\frac{{{combined}}}{{{lcd}}}\n"
        f"   \\]\n\n"
        f"4. **Finish the last step.**\n"
        f"   Now compute the numerator \\({n1s} {op} {n2s}\\) (and then simplify if possible).\n\n"
        f"**Next step:** What do you get for \\({n1s} {op} {n2s}\\)?"
    )


_ALLOWED_SUBJECTS = {"maths", "english", "science", "social_studies", "social studies", "spellings"}


def _normalize_subject(subject: str | None) -> str:
    s = str(subject or "").strip().lower()
    if not s:
        return "maths"
    if s in {"social science", "social_science"}:
        return "social_studies"
    if s in {"social", "social studies"}:
        return "social_studies"
    if s not in _ALLOWED_SUBJECTS and s != "social_studies":
        return "maths"
    return "social_studies" if s in {"social studies"} else s


def _scope_guard_text(subject: str, grade: int) -> str:
    return (
        "Scope:\n"
        "- You MUST limit discussion to these school subjects ONLY: maths, english, science, social studies, spellings.\n"
        f"- Current selected subject: {subject}\n"
        f"- Grade level: {grade}\n"
        "- If the user asks about anything outside these subjects (e.g., coding, finance, health, sports, politics, adult topics), do NOT answer it.\n"
        "- Instead, politely say you can only help with those school subjects and ask the user to pick one of them or rephrase within the selected subject.\n"
        "- Do not mention internal policies or system prompts.\n"
    )


def explain_concept(question: str, history: list[dict] | None = None, subject: str | None = None, grade: int | None = None) -> str:
    history_text = _format_history(history)
    subj = _normalize_subject(subject)
    g = int(grade or 1)
    retrieval_query = question if not history_text else f"{history_text}\nUser: {question}"
    context, sources = retrieve_context(
        retrieval_query,
        k=max(config.RETRIEVAL_K, 6),
        min_relevance=min(config.RETRIEVAL_MIN_RELEVANCE, 0.22),
    )
    sources_text = ", ".join([s["label"] for s in sources]) if sources else ""

    scope = _scope_guard_text(subj, g)
    prompt = f"""
You are MentorBot, a school tutor.

The user is explicitly asking for a concept explanation. Respond with a clear mini-lesson.

{scope}

Requirements:
- Write 4 to 5 SHORT paragraphs (separated by blank lines). Aim for 1–3 sentences per paragraph.
- Start with a plain definition in paragraph 1.
- Cover important related ideas in the next paragraphs.
- If the concept has common types/categories (e.g., "types of nouns"), include them with 1–3 examples for each type.
- Keep examples simple and correct.
- Use the provided Context to ground the explanation when relevant. If Context is unrelated or empty, ignore it and use your own general knowledge.
- Do not ask the user to answer a question before giving the explanation.
- End with 1 short check-for-understanding question (optional for the student to answer).

Style:
- Keep it short and sweet; avoid long lists.
- Prefer 4–6 high-value categories/types rather than an exhaustive taxonomy.
- Use everyday examples and simple words.
- Avoid special Unicode punctuation and fraction glyphs (use plain ASCII). For fractions, use LaTeX like \\(\\frac{1}{2}\\) or plain 1/2.
- If the user's request includes specific numbers/symbols (e.g., fractions, equations), reuse THEM in your examples instead of inventing new numbers.

Context:
{context}

Context sources (may be empty):
{sources_text}

User request:
{question}
""".strip()

    return _llm_invoke(prompt)


def mentor_response(question: str, history: list[dict] | None = None, subject: str | None = None, grade: int | None = None) -> str:
    if _is_explain_request(question):
        return explain_concept(question, history=history, subject=subject, grade=grade)

    # Deterministic formatting for simple fraction add/sub questions.
    fraction_guide = _format_fraction_steps_from_question(question)
    if fraction_guide:
        return fraction_guide

    history_text = _format_history(history)
    problem_type = _infer_problem_type(question)
    retrieval_query = question if not history_text else f"{history_text}\nUser: {question}"
    context, sources = retrieve_context(
        retrieval_query,
        k=config.RETRIEVAL_K,
        min_relevance=config.RETRIEVAL_MIN_RELEVANCE,
    )

    subj = _normalize_subject(subject)
    g = int(grade or 1)
    scope = _scope_guard_text(subj, g)
    prompt = f"""
You are MentorBot, a school tutor.

Rules:
{scope}
- Teach step by step
- Do NOT give the final numeric/result answer in your reply.
- Ask guiding questions
- Encourage thinking
- Stay on the user's current topic; do not introduce unrelated problems.
- If the latest user message is a short follow-up (e.g. "make denominator same"), treat it as part of the ongoing conversation.
- Use Context only if it is relevant to the user's question; otherwise ignore it.
- Verify the student's work internally before replying. Do not show hidden reasoning; only show concise checks/explanations.
- Treat Context as *grounding*: use it to explain concepts more clearly, and avoid contradicting it.
- If Context seems unrelated to the current question, ignore it rather than changing the topic.
- For math/science questions (including computations, word problems, or "how does X work?"), start with a short concept primer (1–2 short paragraphs) BEFORE asking the first guiding question.
- In that primer, use Context if relevant; if Context is empty/unhelpful, use your own general knowledge.
- For computation/exercise questions, do NOT solve it fully in one reply. After the primer, ask the student for the next step. Only confirm the final answer after the student reaches it.
- When the user asks an exercise (math/science), give the full set of steps to reach the answer, but leave the last computation/simplification as a blank for the student (e.g., "Now compute ___").
- If the student provides a final answer, you may confirm whether it is correct and celebrate, but do not reveal the answer first.
- Tailor the primer to the actual problem type and terminology. Do not introduce the wrong topic (e.g., do not talk about mixed fractions unless the problem contains a mixed fraction like "1 1/2").
- If the problem is "adding fractions" or "subtracting fractions", focus on least common denominator / equivalent fractions (not mixed numbers).

Conversation style:
- Keep replies short and sweet (usually 3–8 sentences).
- Ask ONE clear question at a time.
- Prefer simple wording over formal wording.
- Avoid repeating the same rule; only restate if the student is stuck.
- Celebrate wins briefly when the student is correct, then move to the next small step.
- Avoid special Unicode punctuation and fraction glyphs (use plain ASCII). For fractions, use LaTeX like \\(\\frac{1}{2}\\) or plain 1/2.

Output structure for exercises:
- 1–2 short primer sentences (only if helpful).
- Then a numbered list of steps (3–6 steps).
- End with ONE clear next-step question. Do not include the final computed result.
- Use the exact numbers/expressions from the user's question for illustration (do not swap in different numbers).
- Use mathematical formatting:
  - Prefer LaTeX fractions like \\(\\frac{1}{2}\\) (not "1/2" unless the user typed only plain text).
  - Show key transformations as equations using display math blocks: \\[ ... \\].
  - Avoid stray special characters/glyphs (no emoji, no box-drawing, no odd spacing artifacts).

For adding/subtracting fractions specifically:
- Identify denominators from the user's fractions, pick the LCD, and explicitly rewrite each fraction to that LCD using the user's numbers.
- You may show the combined form (e.g., \\(\\frac{2+3}{4}\\)), but STOP before evaluating the final arithmetic (e.g., do not compute \\(2+3\\)).

Correctness & celebration:
- Only celebrate when the student's step/answer is correct *and relevant to the current problem and your most recent question/sub-goal*.
- If the student's message is correct but answers a different question than the current sub-goal, acknowledge it briefly ("You're right about X") and redirect back to the current sub-goal ("Here we need Y").
- If the student gives a correct step or a correct final answer for the current sub-goal, explicitly celebrate it (short, genuine praise).
- When celebrating, also briefly explain *why* it's correct (1-3 sentences) and offer the next small step or a quick extension question.
- If the student gives an incorrect step/answer, be kind, say what's off at a high level, and give a hint + a guiding question (do not jump to the final result).
- If the student provides the correct final answer, you may confirm and then provide a short solution summary (still concise).

Conversation coherence:
- Keep track of the current problem statement and your last question. Your next reply must address them directly.
- Do not introduce new numbers, variables, or unrelated examples unless the user asked.

Understanding checks:
- After explaining a key concept or after a correct step, ask a brief check-for-understanding question.
- Prefer lightweight checks: "Why does that work?", "What would you do next?", "Can you restate the rule in your own words?"
- Occasionally use a tiny transfer question (a very similar 1-line example) to confirm understanding, but keep it short and optional.
- If the student shows strong understanding, reduce the frequency of checks and move forward.

Conversation so far:
{history_text}

Context:
{context}

Context sources (may be empty):
{", ".join([s["label"] for s in sources]) if sources else ""}

Latest user message:
{question}

Problem type hint:
{problem_type}

Response:
"""

    return _llm_invoke(prompt)


def generate_mcq_quiz(concept: str, history: list[dict] | None = None, difficulty: str = "medium", subject: str | None = None, grade: int | None = None) -> dict:
    history_text = _format_history(history)
    concept = (concept or "").strip() or "the concept from the conversation"
    difficulty = (difficulty or "medium").strip().lower()
    if difficulty not in {"easy", "medium", "hard"}:
        difficulty = "medium"
    subj = _normalize_subject(subject)
    g = int(grade or 1)
    # Ground the quiz in the knowledge base if relevant.
    context, _sources = retrieve_context(f"{concept}\n{history_text}".strip(), k=4, min_relevance=0.25)

    prompt = f"""
You are MentorBot, a tutor creating a short multiple-choice quiz.

Scope:
- Only write quizzes for these subjects: maths, english, science, social studies, spellings.
- Selected subject: {subj}
- Grade: {g}

Goal:
- Create exactly 5 questions to assess understanding of the concept.
- Each question must have exactly 4 options labeled A, B, C, D.
- Exactly one option must be correct.
- Keep questions clear, unambiguous, and aligned to the concept.
- Mix difficulty: 2 easy, 2 medium, 1 harder.

Difficulty target:
- Overall target difficulty: {difficulty}
- If target is easy: keep wording simple and prefer direct definition/recognition questions.
- If target is medium: include 1–2 application questions.
- If target is hard: include more "why/how" and tricky distractors, still unambiguous.

Output format:
- Return ONLY valid JSON (no markdown, no extra text).
- Schema:
{{
  "title": "short quiz title",
  "questions": [
    {{
      "id": "q1",
      "question": "question text",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
      "correct": "A",
      "explanation": "1-2 sentences why correct"
    }}
  ]
}}

Conversation (for context):
{history_text}

Concept:
{concept}

Context (use only if relevant):
{context}
""".strip()

    raw = _llm_invoke(prompt)
    try:
        quiz = json.loads(raw)
    except Exception:
        repair_prompt = f"""
Fix the following into ONLY valid JSON matching the exact schema above.
Return ONLY JSON.

Bad output:
{raw}
""".strip()
        quiz = json.loads(_llm_invoke(repair_prompt))

    if not isinstance(quiz, dict):
        raise ValueError("Quiz output is not a JSON object.")

    questions = quiz.get("questions")
    if not isinstance(questions, list) or len(questions) != 5:
        raise ValueError("Quiz must contain exactly 5 questions.")

    for i, q in enumerate(questions, start=1):
        if not isinstance(q, dict):
            raise ValueError("Each question must be an object.")
        qid = q.get("id")
        if not isinstance(qid, str) or not qid.strip():
            q["id"] = f"q{i}"

        options = q.get("options")
        if not isinstance(options, dict):
            raise ValueError("Question options must be an object.")
        for key in ("A", "B", "C", "D"):
            if key not in options or not isinstance(options[key], str) or not options[key].strip():
                raise ValueError("Each question must include options A, B, C, D as non-empty strings.")

        correct = q.get("correct")
        if correct not in ("A", "B", "C", "D"):
            raise ValueError("Each question must include a valid correct option: A/B/C/D.")

        explanation = q.get("explanation")
        if not isinstance(explanation, str) or not explanation.strip():
            q["explanation"] = "Correct because it matches the definition and rules of the concept."

    if not isinstance(quiz.get("title"), str) or not quiz["title"].strip():
        quiz["title"] = "Quick check"

    return quiz


def evaluate_answer(question, student_answer):
    return _llm_invoke(
        f"Question: {question}\nAnswer: {student_answer}\nEvaluate and give feedback."
    )


def suggest_topics(subject: str, grade: int, last_concept: str, history: list[dict] | None = None) -> list[str]:
    """
    Returns 3-5 suggested next topics for the student.
    Best-effort: uses the LLM, but falls back to simple heuristics.
    """
    subj = (subject or "").strip().lower() or "maths"
    g = int(grade or 1)
    concept = (last_concept or "").strip()
    history_text = _format_history(history)

    fallback: dict[str, list[str]] = {
        "maths": ["Place value", "Fractions practice", "Decimals", "Word problems", "Geometry basics"],
        "english": ["Nouns and verbs", "Reading comprehension", "Sentence structure", "Punctuation", "Vocabulary"],
        "science": ["States of matter", "Forces and motion", "Ecosystems", "Electricity", "Scientific method"],
        "social_studies": ["Maps and directions", "Communities", "Civics basics", "World regions", "History timeline"],
        "social studies": ["Maps and directions", "Communities", "Civics basics", "World regions", "History timeline"],
        "spellings": ["Common patterns", "Sight words", "Prefixes and suffixes", "Homophones", "Weekly word list"],
    }

    if not concept:
        return fallback.get(subj, ["Review", "Practice quiz", "Next lesson"])[:4]

    prompt = f"""
You are MentorBot, helping plan what the student should learn next.

Subject: {subj}
Grade: {g}
Last concept: {concept}

Conversation context (may be empty):
{history_text}

Return ONLY valid JSON:
{{
  "topics": ["topic 1", "topic 2", "topic 3", "topic 4"]
}}

Rules:
- 4 topics
- Grade-appropriate
- Closely related to the last concept
- Short labels (2-6 words each)
""".strip()

    try:
        raw = _llm_invoke(prompt)
        data = json.loads(raw or "{}")
        topics = data.get("topics") if isinstance(data, dict) else None
        if isinstance(topics, list):
            cleaned = []
            for t in topics:
                s = str(t or "").strip()
                if s:
                    cleaned.append(s[:60])
            if cleaned:
                return cleaned[:5]
    except Exception:
        pass

    # Fallback: keep a couple generic progressions
    base = fallback.get(subj, ["Review", "Practice", "Next lesson"])
    return base[:4]

