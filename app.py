from pathlib import Path
import base64
import binascii
import json
import logging
import re
import secrets
import time
from uuid import uuid4
import csv
import io
import os
import sys
import warnings

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.responses import PlainTextResponse

# Silence a noisy dependency warning when running on Python 3.14+ locally.
# (Production container uses Python 3.12.)
warnings.filterwarnings(
    "ignore",
    message=r"Core Pydantic V1 functionality isn't compatible with Python 3\.14 or greater\.",
    category=UserWarning,
)

import config
from mentor import (
    classify_subject,
    generate_mcq_quiz,
    get_vectordb,
    group_study_explanation,
    is_explain_request,
    mentor_response,
    suggest_topics,
)
from app_db import AppDb, AppDbConfig
from security import hash_pin, verify_pin

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
CHAT_HTML_PATH = BASE_DIR / "web" / "chat.html"
STATIC_DIR = BASE_DIR / "web" / "static"


def create_app() -> FastAPI:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()


_APP_DB = AppDb(AppDbConfig(path=config.APP_DB_PATH, session_ttl_s=int(config.SESSION_TTL_S)))

# Optional bootstrap Parent PIN from env (one-time).
if str(getattr(config, "PARENT_PIN", "") or "").strip() and not _APP_DB.parent_pin_is_set():
    salt, digest = hash_pin(str(config.PARENT_PIN))
    _APP_DB.set_parent_pin(salt, digest)


def _get_bearer_token(request: Request) -> str:
    # IMPORTANT: When HTTP Basic Auth is enabled, the Authorization header is used for Basic,
    # so session tokens must not rely on Authorization or they will conflict.
    # Prefer X-Mentorbot-Session for app sessions, but keep Bearer as fallback.
    token = str(request.headers.get("x-mentorbot-session", "") or "").strip()
    if token:
        return token
    auth = str(request.headers.get("authorization", "") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return ""


def _require_student(request: Request) -> str:
    token = _get_bearer_token(request)
    sess = _APP_DB.verify_session(token)
    if not sess or sess[0] != "student":
        raise HTTPException(status_code=401, detail="Unauthorized")
    return str(sess[1])


def _require_parent(request: Request) -> str:
    token = _get_bearer_token(request)
    sess = _APP_DB.verify_session(token)
    if not sess or sess[0] != "parent":
        raise HTTPException(status_code=401, detail="Unauthorized")
    return str(sess[1])


def _infer_subject_from_text(text: str, *, default_subject: str = "maths") -> str:
    t = (text or "").strip().lower()
    if not t:
        d = str(default_subject or "").strip().lower() or "maths"
        return d if d in {"maths", "english", "science", "social_studies", "spellings"} else "maths"

    # Explicit override: "English: ...", "Science: ..."
    m = re.match(r"^\s*(math|maths|english|science|spellings|social studies|social_studies|history|geography)\s*:\s*", t)
    if m:
        k = str(m.group(1) or "").strip().lower()
        if k in {"math", "maths"}:
            return "maths"
        if k in {"social studies", "social_studies", "history", "geography"}:
            return "social_studies"
        return k

    # Maths (explicit detection so we don't fall back to a non-maths default)
    # If the user included digits/operators or common maths keywords, treat it as maths.
    if re.search(r"\d", t) and re.search(r"[\+\-\*/=^]|\b(solve|equation|simplify|factor)\b", t):
        return "maths"
    if any(
        k in t
        for k in [
            "fraction",
            "fractions",
            "numerator",
            "denominator",
            "decimal",
            "decimals",
            "percent",
            "percentage",
            "ratio",
            "proportion",
            "algebra",
            "variable",
            "equation",
            "inequality",
            "simplify",
            "expand",
            "factor",
            "multiply",
            "division",
            "divide",
            "addition",
            "add",
            "subtraction",
            "subtract",
            "geometry",
            "angle",
            "angles",
            "perimeter",
            "area",
            "volume",
            "graph",
            "coordinate",
        ]
    ):
        return "maths"

    # Spellings
    if any(k in t for k in ["spell", "spelling", "syllable", "phonics", "sound it out"]):
        return "spellings"

    # English / language arts
    if any(
        k in t
        for k in [
            "noun",
            "verb",
            "adjective",
            "adverb",
            "grammar",
            "punctuation",
            "sentence",
            "paragraph",
            "synonym",
            "antonym",
            "reading",
            "comprehension",
            "pronoun",
            "preposition",
            "conjunction",
            "metaphor",
            "simile",
            "alliteration",
            "theme",
            "character",
            "plot",
            "essay",
            "poem",
            "book report",
        ]
    ):
        return "english"

    # Science
    if any(
        k in t
        for k in [
            "photosynthesis",
            "atom",
            "molecule",
            "cell",
            "energy",
            "force",
            "gravity",
            "electricity",
            "ecosystem",
            "experiment",
            "chemical",
            "evaporation",
            "condensation",
            "water cycle",
            "weather",
            "planet",
            "solar system",
            "moon",
            "dna",
            "bacteria",
            "virus",
            "climate",
        ]
    ):
        return "science"

    # Social studies / social science
    if any(
        k in t
        for k in [
            "history",
            "geography",
            "map",
            "continent",
            "country",
            "capital",
            "government",
            "civics",
            "constitution",
            "democracy",
            "community",
            "culture",
            "war",
            "timeline",
            "president",
            "prime minister",
            "election",
            "parliament",
            "revolution",
            "independence",
            "empire",
            "ancient",
            "medieval",
        ]
    ):
        return "social_studies"

    # Ambiguous: ask the LLM to classify (best-effort), then fall back.
    try:
        guessed = classify_subject(text)
        if guessed:
            return guessed
    except Exception:
        pass

    d = str(default_subject or "").strip().lower() or "maths"
    return d if d in {"maths", "english", "science", "social_studies", "spellings"} else "maths"


def _require_student_token(token: str) -> str:
    t = str(token or "").strip()
    sess = _APP_DB.verify_session(t)
    if not sess or sess[0] != "student":
        raise HTTPException(status_code=401, detail="Unauthorized")
    return str(sess[1])


class _GroupHub:
    def __init__(self):
        self._lock = threading.Lock()
        # group_id -> { websocket -> student_id }
        self._conns: dict[str, dict[WebSocket, str]] = {}

    async def join(self, group_id: str, ws: WebSocket, *, student_id: str) -> None:
        await ws.accept()
        with self._lock:
            self._conns.setdefault(group_id, {})[ws] = str(student_id)

    def leave(self, group_id: str, ws: WebSocket) -> str | None:
        with self._lock:
            m = self._conns.get(group_id)
            if not m:
                return None
            sid = m.pop(ws, None)
            if not m:
                self._conns.pop(group_id, None)
            return sid

    def participants(self, group_id: str) -> set[str]:
        with self._lock:
            m = self._conns.get(group_id) or {}
            return set(str(sid) for sid in m.values() if str(sid).strip())

    def participant_count(self, group_id: str) -> int:
        return len(self.participants(group_id))

    async def broadcast(self, group_id: str, payload: dict) -> None:
        with self._lock:
            conns = list((self._conns.get(group_id) or {}).keys())
        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception:
                self.leave(group_id, ws)


import threading

_GROUP_HUB = _GroupHub()

_CHAT_LOG_LOCK = threading.Lock()


def _day_str(ts: int) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(int(ts)))


_GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|hiya|yo|sup|howdy|good\s+morning|good\s+afternoon|good\s+evening)\s*[!.?]*\s*$",
    re.IGNORECASE,
)


def _is_greeting(text: str) -> bool:
    t = str(text or "").strip()
    if not t:
        return True
    return bool(_GREETING_RE.match(t))


def _is_meta_or_app_usage(text: str) -> bool:
    t = str(text or "").strip().lower()
    if not t:
        return True
    meta_keywords = [
        "mentorbot",
        "who are you",
        "what are you",
        "what can you do",
        "help me use",
        "how to use",
        "login",
        "sign in",
        "sign up",
        "pin",
        "password",
        "parent",
        "admin",
        "roster",
        "upload",
        "csv",
        "group",
        "invite code",
        "notes",
        "theme",
        "wallpaper",
        "avatar",
        "report",
        "dashboard",
        "cluster",
        "kubernetes",
        "docker",
        "argocd",
    ]
    return any(k in t for k in meta_keywords)


def _should_suggest_topics(text: str) -> bool:
    t = str(text or "").strip()
    if not t:
        return False
    if _is_greeting(t) or _is_meta_or_app_usage(t):
        return False

    tl = t.lower()
    # Avoid suggestions for very short / vague prompts.
    if len(tl) < 10:
        return False

    if "?" in tl:
        return True

    # Allow non-question prompts that still look like a real maths/exercise request.
    if re.search(r"\b(explain|solve|find|calculate|simplify|factor|expand|prove|derive|convert|compare)\b", tl):
        return True
    if re.search(r"[\d\+\-\*/=]", tl):
        return True
    if re.search(r"\b(fraction|fractions|decimal|decimals|percent|percentage|algebra|equation|angle|triangle|graph|mean|median|mode)\b", tl):
        return True

    return False


def _append_daily_chat_log(payload: dict) -> None:
    if not bool(getattr(config, "CHAT_LOG_ENABLED", True)):
        return
    log_dir = str(getattr(config, "CHAT_LOG_DIR", "") or "").strip() or str(Path(config.DB_DIR) / "chat_logs")
    day = str(payload.get("day") or "").strip()
    if not day:
        day = _day_str(int(payload.get("createdAt") or int(time.time())))
        payload["day"] = day
    os.makedirs(log_dir, exist_ok=True)
    p = Path(log_dir) / f"{day}.jsonl"
    line = json.dumps(payload, ensure_ascii=False)
    with _CHAT_LOG_LOCK:
        with open(p, "a", encoding="utf-8") as f:
            f.write(line + "\n")

# Basic auth middleware (protects all routes including static), with /health* open for probes.
@app.middleware("http")
async def basic_auth_middleware(request, call_next):
    if not bool(getattr(config, "BASIC_AUTH_ENABLED", False)):
        return await call_next(request)

    path = str(getattr(request, "url", "").path or "")
    if path.startswith("/health"):
        return await call_next(request)

    username = str(getattr(config, "BASIC_AUTH_USERNAME", "") or "")
    password = str(getattr(config, "BASIC_AUTH_PASSWORD", "") or "")
    if not username or not password:
        return PlainTextResponse("Basic auth enabled but credentials not set.", status_code=500)

    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("basic "):
        return PlainTextResponse(
            "Unauthorized",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="mentorbot", charset="UTF-8"'},
        )

    try:
        b64 = auth.split(" ", 1)[1].strip()
        decoded = base64.b64decode(b64.encode("utf-8"), validate=True).decode("utf-8")
        supplied_user, supplied_pass = decoded.split(":", 1)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return PlainTextResponse(
            "Unauthorized",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="mentorbot", charset="UTF-8"'},
        )

    if not (secrets.compare_digest(supplied_user, username) and secrets.compare_digest(supplied_pass, password)):
        return PlainTextResponse(
            "Unauthorized",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="mentorbot", charset="UTF-8"'},
        )

    return await call_next(request)

# quiz_id -> {"quiz": <quiz>, "created_at": <epoch_seconds>}
QUIZ_STORE: dict[str, dict] = {}
QUIZ_TTL_SECONDS = 60 * 60  # 1 hour
QUIZ_MAX_ITEMS = 200


class ChatMessage(BaseModel):
    role: str
    content: str


class Question(BaseModel):
    question: str
    history: list[ChatMessage] = []
    subject: str | None = None
    grade: int | None = None


class QuizGenerateRequest(BaseModel):
    concept: str | None = None
    history: list[ChatMessage] = []
    conceptId: str | None = None
    subject: str | None = None
    grade: int | None = None


class QuizAnswer(BaseModel):
    questionId: str
    choice: str


class QuizSubmitRequest(BaseModel):
    quizId: str
    answers: list[QuizAnswer]


class QuizSkipRequest(BaseModel):
    conceptId: str
    subject: str | None = None
    grade: int | None = None


class StudentLoginRequest(BaseModel):
    studentId: str
    pin: str


class StudentSetPinRequest(BaseModel):
    studentId: str
    newPin: str


class ParentLoginRequest(BaseModel):
    pin: str


class ParentSetPinRequest(BaseModel):
    pin: str


class ProfilePatchRequest(BaseModel):
    grade: int | None = None
    avatarKey: str | None = None
    wallpaperKey: str | None = None
    subjectPref: str | None = None


class NoteCreateRequest(BaseModel):
    subject: str
    grade: int
    title: str
    body: str
    source: str | None = None


class NotePatchRequest(BaseModel):
    title: str | None = None
    body: str | None = None


class GroupCreateRequest(BaseModel):
    name: str
    subject: str
    grade: int


class GroupJoinRequest(BaseModel):
    inviteCode: str


class GroupMessageRequest(BaseModel):
    body: str


class ParentResetStudentPinRequest(BaseModel):
    studentId: str
    newPin: str | None = None


@app.get("/")
def chat_ui():
    return FileResponse(
        CHAT_HTML_PATH,
        media_type="text/html",
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
        },
    )


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/health/app")
def health_app():
    routes = []
    group_routes = []
    for r in getattr(app, "routes", []) or []:
        path = getattr(r, "path", None)
        if not isinstance(path, str):
            continue
        routes.append(path)
        if path.startswith("/groups") or path.startswith("/ws/groups"):
            group_routes.append(path)
    routes_set = sorted(set(routes))
    group_routes_set = sorted(set(group_routes))
    return {
        "ok": True,
        "appFile": __file__,
        "cwd": os.getcwd(),
        "python": sys.version.split()[0],
        "routesCount": len(routes_set),
        "hasGroupsRoutes": bool(group_routes_set),
        "groupsRoutes": group_routes_set,
    }


@app.get("/health/models")
def health_models():
    return {
        "llmApiStyle": getattr(config, "LLM_API_STYLE", None),
        "llmBaseUrl": getattr(config, "LLM_BASE_URL", None),
        "llmModel": getattr(config, "LLM_MODEL", None),
        "llmTimeoutS": getattr(config, "LLM_TIMEOUT_S", None),
        "ollamaEmbedModel": config.OLLAMA_EMBED_MODEL,
        "ollamaLlmModel": config.OLLAMA_LLM_MODEL,
        "ollamaLlmFallbackModel": config.OLLAMA_LLM_FALLBACK_MODEL,
        "ollamaBaseUrl": getattr(config, "OLLAMA_BASE_URL", None),
        "dbDir": config.DB_DIR,
    }


@app.get("/health/vectordb")
def health_vectordb():
    try:
        db = get_vectordb()
        _ = db._collection.count()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"vectordb unavailable: {e}")


@app.get("/apple-touch-icon.png", include_in_schema=False)
@app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
def apple_touch_icon():
    # Some browsers request these by default. We don't ship PNG icons, so redirect to the SVG logo.
    return RedirectResponse(url="/static/logo.svg")


@app.post("/ask")
def ask(request: Request, q: Question):
    student_id = _require_student(request)
    student = _APP_DB.get_student(student_id)
    if not student:
        raise HTTPException(status_code=401, detail="Unauthorized")

    grade = int(q.grade or student.get("grade") or 1)
    subject_pref = str(student.get("subjectPref") or "").strip().lower() or "maths"
    subject = _infer_subject_from_text(q.question, default_subject=subject_pref)

    try:
        history_msgs = _APP_DB.list_chat_messages(student_id=student_id, limit=24)
        history = [{"role": str(m.get("role")), "content": str(m.get("content"))} for m in history_msgs]

        user_ts = int(time.time())
        user_msg_id = _APP_DB.add_chat_message(
            student_id=student_id,
            role="user",
            content=str(q.question or "").strip(),
            subject=subject,
            grade=grade,
            quiz_required=False,
            created_at=user_ts,
        )
        _append_daily_chat_log(
            {
                "id": user_msg_id,
                "studentId": student_id,
                "pseudonym": str(student.get("pseudonym") or ""),
                "role": "user",
                "content": str(q.question or "").strip(),
                "subject": subject,
                "grade": grade,
                "conceptId": None,
                "quizRequired": False,
                "createdAt": user_ts,
                "day": _day_str(user_ts),
            }
        )

        answer = mentor_response(q.question, history=history, subject=subject, grade=grade)
        quiz_required = bool(is_explain_request(q.question))
        concept_id: str | None = None
        if quiz_required:
            concept_id = _APP_DB.create_concept(
                student_id=student_id,
                subject=subject,
                grade=grade,
                concept_text=str(q.question or "").strip(),
            )
        asst_ts = int(time.time())
        asst_msg_id = _APP_DB.add_chat_message(
            student_id=student_id,
            role="assistant",
            content=str(answer or "").strip(),
            subject=subject,
            grade=grade,
            concept_id=concept_id,
            quiz_required=quiz_required,
            created_at=asst_ts,
        )
        _append_daily_chat_log(
            {
                "id": asst_msg_id,
                "studentId": student_id,
                "pseudonym": str(student.get("pseudonym") or ""),
                "role": "assistant",
                "content": str(answer or "").strip(),
                "subject": subject,
                "grade": grade,
                "conceptId": concept_id,
                "quizRequired": quiz_required,
                "createdAt": asst_ts,
                "day": _day_str(asst_ts),
            }
        )
        suggested = []
        if _should_suggest_topics(str(q.question or "")):
            suggested = suggest_topics(subject=subject, grade=grade, last_concept=str(q.question or ""), history=history)
        return {
            "answer": answer,
            "quizRequired": quiz_required,
            "conceptId": concept_id,
            "subject": subject,
            "grade": grade,
            "suggestedTopics": suggested,
        }
    except Exception as e:
        logger.exception("ask failed")
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/me/chatlogs")
def me_chatlogs(request: Request, day: str | None = None, limit: int = 200):
    student_id = _require_student(request)
    d = (str(day or "").strip() or None) if day is not None else None
    if not d:
        d = _day_str(int(time.time()))
    msgs = _APP_DB.list_chat_messages(student_id=student_id, day=d, limit=int(limit))
    return {"day": d, "messages": msgs}


@app.get("/me/chatlogs/days")
def me_chatlog_days(request: Request, limit: int = 60):
    student_id = _require_student(request)
    days = _APP_DB.list_chat_days(student_id=student_id, limit=int(limit))
    return {"days": days}


@app.get("/parent/chatlogs")
def parent_chatlogs(request: Request, studentId: str, day: str | None = None, limit: int = 200):
    _ = _require_parent(request)
    sid = str(studentId or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="studentId is required")
    d = (str(day or "").strip() or None) if day is not None else None
    if not d:
        d = _day_str(int(time.time()))
    msgs = _APP_DB.list_chat_messages(student_id=sid, day=d, limit=int(limit))
    return {"studentId": sid, "day": d, "messages": msgs}


@app.get("/parent/chatlogs/days")
def parent_chatlog_days(request: Request, studentId: str, limit: int = 60):
    _ = _require_parent(request)
    sid = str(studentId or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="studentId is required")
    days = _APP_DB.list_chat_days(student_id=sid, limit=int(limit))
    return {"studentId": sid, "days": days}


@app.post("/quiz/generate")
def quiz_generate(request: Request, req: QuizGenerateRequest):
    student_id = _require_student(request)
    student = _APP_DB.get_student(student_id)
    if not student:
        raise HTTPException(status_code=401, detail="Unauthorized")

    concept_text = (req.concept or "").strip()
    concept_id = (req.conceptId or "").strip()

    if not concept_id:
        # If the client provided a concept text (manual quiz), generate a quiz for THAT concept.
        # Do NOT silently attach to an older pending concept (which can be a different subject).
        if concept_text:
            subject = _infer_subject_from_text(concept_text, default_subject=str(student.get("subjectPref") or "maths"))
            grade = int(req.grade or student.get("grade") or 1)
            concept_id = _APP_DB.create_concept(
                student_id=student_id,
                subject=subject,
                grade=grade,
                concept_text=concept_text,
            )
        else:
            concept_id = _APP_DB.get_latest_pending_concept_id(student_id) or ""

    if concept_id:
        meta = _APP_DB.get_concept_meta(student_id=student_id, concept_id=concept_id)
        grade = int((meta or {}).get("grade") or req.grade or student.get("grade") or 1)
        subject = str(
            (meta or {}).get("subject")
            or _infer_subject_from_text(req.concept or "", default_subject=str(student.get("subjectPref") or "maths"))
        ).strip().lower() or "maths"
    else:
        # Fallback: create a concept from the current context, so the quiz still has a progression anchor.
        concept_text = (req.concept or "the current concept from the conversation").strip()
        subject = _infer_subject_from_text(concept_text, default_subject=str(student.get("subjectPref") or "maths"))
        grade = int(req.grade or student.get("grade") or 1)
        concept_id = _APP_DB.create_concept(
            student_id=student_id,
            subject=subject,
            grade=grade,
            concept_text=concept_text,
        )

    history = [{"role": m.role, "content": m.content} for m in req.history]
    concept = (req.concept or "").strip()
    if not concept:
        for msg in reversed(history):
            if str(msg.get("role", "")).lower() in {"assistant", "bot"}:
                concept = str(msg.get("content", "")).strip()
                break
    if not concept:
        concept = "the current concept from the conversation"

    perf = _APP_DB.recent_performance(student_id, n=5)
    avg = perf.get("avg")
    if avg is None:
        difficulty = "medium"
    elif float(avg) >= 88.0:
        difficulty = "hard"
    elif float(avg) >= 75.0:
        difficulty = "medium"
    else:
        difficulty = "easy"

    try:
        quiz = generate_mcq_quiz(concept=concept, history=history, difficulty=difficulty, subject=subject, grade=grade)
    except TypeError:
        # Backward compatibility if generate_mcq_quiz doesn't accept difficulty yet.
        quiz = generate_mcq_quiz(concept=concept, history=history)
        difficulty = "medium"
    except Exception as e:
        logger.exception("quiz_generate failed")
        raise HTTPException(status_code=503, detail=str(e))

    quiz_id = _APP_DB.record_quiz(student_id=student_id, concept_id=concept_id, difficulty=difficulty, quiz=quiz)

    public_questions = [{"id": q["id"], "question": q["question"], "options": q["options"]} for q in quiz["questions"]]
    return {
        "quizId": quiz_id,
        "conceptId": concept_id,
        "title": quiz.get("title", "Quick check"),
        "difficulty": difficulty,
        "questions": public_questions,
    }


@app.post("/quiz/submit")
def quiz_submit(request: Request, req: QuizSubmitRequest):
    student_id = _require_student(request)
    record = _APP_DB.get_quiz(req.quizId, student_id=student_id)
    if not record:
        raise HTTPException(status_code=404, detail="Quiz not found (it may have expired or the server restarted).")
    quiz = record.get("quiz")
    if not isinstance(quiz, dict):
        raise HTTPException(status_code=500, detail="Stored quiz is invalid.")

    answers_map: dict[str, str] = {}
    for a in req.answers:
        answers_map[a.questionId] = (a.choice or "").strip().upper()

    questions = quiz.get("questions", [])
    if not isinstance(questions, list) or len(questions) != 5:
        raise HTTPException(status_code=500, detail="Stored quiz is invalid.")

    correct_count = 0
    review = []
    for q in questions:
        qid = q["id"]
        correct = str(q["correct"]).strip().upper()
        user_choice = answers_map.get(qid, "")
        is_correct = user_choice == correct
        if is_correct:
            correct_count += 1
        review.append(
            {
                "id": qid,
                "question": q.get("question", ""),
                "options": q.get("options", {}),
                "userChoice": user_choice,
                "correct": correct,
                "isCorrect": is_correct,
                "explanation": q.get("explanation", ""),
            }
        )

    total = len(questions)
    score_percent = round((correct_count / total) * 100, 1)
    understood = score_percent >= float(config.QUIZ_PASS_PERCENT)

    pass_percent = float(config.QUIZ_PASS_PERCENT)
    if understood:
        message = f"Nice work — {correct_count}/{total} correct ({score_percent}%). Concept understood!"
    else:
        message = f"Good effort — {correct_count}/{total} correct ({score_percent}%). Not quite {pass_percent:g}% yet; let's review and try again."

    try:
        _APP_DB.add_attempt(
            quiz_id=str(record.get("id")),
            student_id=student_id,
            concept_id=str(record.get("conceptId")),
            score_percent=float(score_percent),
            correct_count=int(correct_count),
            total=int(total),
            understood=bool(understood),
            difficulty=str(record.get("difficulty") or "medium"),
        )
        if understood:
            _APP_DB.mark_concept_passed(student_id, str(record.get("conceptId")))
    except Exception:
        logger.exception("failed to persist attempt")

    suggested = []
    if understood:
        try:
            meta = _APP_DB.get_concept_meta(student_id=student_id, concept_id=str(record.get("conceptId")))
            subj = str((meta or {}).get("subject") or "maths")
            g = int((meta or {}).get("grade") or 1)
            concept_text = str((meta or {}).get("conceptText") or "").strip()
            history_msgs = _APP_DB.list_chat_messages(student_id=student_id, limit=24)
            history = [{"role": str(m.get("role")), "content": str(m.get("content"))} for m in history_msgs]
            if _should_suggest_topics(concept_text or ""):
                suggested = suggest_topics(subject=subj, grade=g, last_concept=concept_text or "the concept from the quiz", history=history)
        except Exception:
            logger.exception("failed to generate suggested topics after quiz")

    return {
        "quizId": req.quizId,
        "conceptId": str(record.get("conceptId")),
        "correctCount": correct_count,
        "total": total,
        "scorePercent": score_percent,
        "understood": understood,
        "message": message,
        "review": review,
        "passPercent": pass_percent,
        "suggestedTopics": suggested,
    }


@app.post("/quiz/skip")
def quiz_skip(request: Request, body: QuizSkipRequest):
    student_id = _require_student(request)
    skipped = _APP_DB.count_skips_last_24h(student_id)
    limit = int(getattr(config, "QUIZ_SKIP_PER_DAY", 5))
    if skipped >= limit:
        raise HTTPException(status_code=429, detail=f"Skip limit reached ({limit}/day).")
    try:
        _APP_DB.mark_concept_skipped(student_id, body.conceptId)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    remaining = max(0, limit - (skipped + 1))
    return {"ok": True, "remainingSkips": remaining, "skipLimit": limit}


@app.get("/stats/compare")
def stats_compare(request: Request, subject: str = "maths", grade: int = 1):
    student_id = _require_student(request)
    return _APP_DB.compare_stats(student_id=student_id, subject=subject, grade=int(grade))


@app.get("/notes")
def notes_list(request: Request, subject: str = "maths", grade: int = 1):
    student_id = _require_student(request)
    return {"notes": _APP_DB.list_notes(student_id=student_id, subject=subject, grade=int(grade))}


@app.post("/notes")
def notes_create(request: Request, body: NoteCreateRequest):
    student_id = _require_student(request)
    try:
        nid = _APP_DB.create_note(
            student_id=student_id,
            subject=body.subject,
            grade=int(body.grade),
            title=body.title,
            body=body.body,
            source=body.source or "manual",
        )
        return {"id": nid}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/notes/{note_id}")
def notes_patch(request: Request, note_id: str, body: NotePatchRequest):
    student_id = _require_student(request)
    try:
        _APP_DB.update_note(student_id=student_id, note_id=note_id, title=body.title, body=body.body)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/notes/{note_id}")
def notes_delete(request: Request, note_id: str):
    student_id = _require_student(request)
    _APP_DB.delete_note(student_id=student_id, note_id=note_id)
    return {"ok": True}


@app.get("/groups")
def groups_list(request: Request):
    student_id = _require_student(request)
    return {"groups": _APP_DB.list_groups_for_student(student_id)}


@app.post("/groups")
def groups_create(request: Request, body: GroupCreateRequest):
    student_id = _require_student(request)
    try:
        g = _APP_DB.create_group(student_id=student_id, name=body.name, subject=body.subject, grade=int(body.grade))
        return g
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/groups/join")
def groups_join(request: Request, body: GroupJoinRequest):
    student_id = _require_student(request)
    try:
        g = _APP_DB.join_group_by_invite(student_id=student_id, invite_code=body.inviteCode)
        return g
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/groups/{group_id}/messages")
def groups_messages(request: Request, group_id: str, limit: int = 50):
    _ = _require_student(request)
    return {"messages": _APP_DB.list_group_messages(group_id=group_id, limit=int(limit))}


def _format_group_study_fallback(*, options: dict, correct: str, results: dict) -> str:
    dist = results.get("distribution") or {}
    def _line(k: str) -> str:
        d = dist.get(k) or {}
        return f"{k}: {float(d.get('percent') or 0.0):g}% ({int(d.get('users') or 0)} users)"

    correct_opt = str(correct or results.get("correct") or "").strip().upper()
    correct_count = int(results.get("correctCount") or 0)
    total = int(results.get("total") or 0)
    opt_text = str((options or {}).get(correct_opt) or "").strip()

    return (
        "📊 Results:\n"
        f"{_line('A')}\n"
        f"{_line('B')}\n"
        f"{_line('C')}\n"
        f"{_line('D')}\n\n"
        f"✅ Correct Answer: {correct_opt}\n\n"
        "🎯 Performance:\n"
        f"- {correct_count} out of {total} users answered correctly\n\n"
        "🧠 Explanation:\n"
        f"The correct answer is {correct_opt}. {('It matches: ' + opt_text) if opt_text else 'It best matches the concept tested.'}\n"
    )


@app.websocket("/ws/groups/{group_id}")
async def ws_groups(group_id: str, ws: WebSocket):
    token = str(ws.query_params.get("token") or "").strip()
    try:
        student_id = _require_student_token(token)
    except HTTPException:
        await ws.close(code=1008)
        return

    try:
        await _GROUP_HUB.join(group_id, ws, student_id=student_id)
        # Send recent messages on join.
        try:
            msgs = _APP_DB.list_group_messages(group_id=group_id, limit=50)
            await ws.send_json({"type": "history", "messages": msgs})
        except Exception:
            pass

        # Send current group study state on join.
        try:
            queued = _APP_DB.count_group_study_queued(group_id)
            open_quiz = _APP_DB.get_open_group_study_quiz(group_id)
            await ws.send_json({"type": "study_queue", "queuedCount": int(queued)})
            if open_quiz:
                required = list(open_quiz.get("requiredParticipants") or [])
                answers = _APP_DB.list_group_study_answers(open_quiz["id"])
                required_set = set(str(x) for x in required if str(x).strip())
                answered_set = {str(a.get("studentId")) for a in answers if str(a.get("studentId")) in required_set}
                await ws.send_json(
                    {
                        "type": "study_open",
                        "quizId": open_quiz["id"],
                        "question": open_quiz.get("question"),
                        "options": open_quiz.get("options") or {},
                        "requiredParticipantCount": len(required_set),
                    }
                )
                await ws.send_json(
                    {
                        "type": "study_progress",
                        "quizId": open_quiz["id"],
                        "answeredCount": len(answered_set),
                        "requiredParticipantCount": len(required_set),
                    }
                )
        except Exception:
            pass

        while True:
            data = await ws.receive_json()
            typ = str((data or {}).get("type") or "").strip().lower()

            # Backward-compat: plain chat payloads without type.
            if not typ or typ == "message":
                body = str((data or {}).get("body") or "").strip()
                if not body:
                    continue
                msg = _APP_DB.add_group_message(group_id=group_id, student_id=student_id, body=body)
                await _GROUP_HUB.broadcast(group_id, {"type": "message", "message": msg})
                continue

            if typ == "study_start":
                mode = str((data or {}).get("mode") or "").strip().lower()
                if mode not in {"generate", "manual"}:
                    await ws.send_json({"type": "study_error", "message": "mode must be generate|manual"})
                    continue

                # One open quiz at a time; others queue.
                open_quiz = _APP_DB.get_open_group_study_quiz(group_id)
                status = "queued" if open_quiz else "open"
                required = sorted(_GROUP_HUB.participants(group_id)) if status == "open" else []

                if mode == "manual":
                    qtext = str((data or {}).get("question") or "").strip()
                    options = (data or {}).get("options") or {}
                    correct = str((data or {}).get("correct") or "").strip().upper()
                    try:
                        quiz_id = _APP_DB.create_group_study_quiz(
                            group_id=group_id,
                            created_by_student_id=student_id,
                            status=status,
                            source="manual",
                            question=qtext,
                            options={k: str(options.get(k) or "").strip() for k in ("A", "B", "C", "D")},
                            correct=correct,
                            required_participants=required,
                        )
                    except Exception as e:
                        await ws.send_json({"type": "study_error", "message": str(e)})
                        continue
                else:
                    # Generate from recent group chat + group meta (subject/grade).
                    meta = _APP_DB.get_group_meta(group_id) or {}
                    subject = str(meta.get("subject") or "maths")
                    grade = int(meta.get("grade") or 1)
                    msgs = _APP_DB.list_group_messages(group_id=group_id, limit=20)
                    concept = "Group study topic"
                    if msgs:
                        concept = " ".join([str(m.get("body") or "") for m in msgs[-10:]]).strip() or concept
                    try:
                        quiz = generate_mcq_quiz(concept=concept, history=None, difficulty="medium", subject=subject, grade=grade)
                        q0 = (quiz.get("questions") or [])[0] if isinstance(quiz.get("questions"), list) and quiz.get("questions") else None
                        if not isinstance(q0, dict):
                            raise ValueError("Generated quiz is invalid")
                        quiz_id = _APP_DB.create_group_study_quiz(
                            group_id=group_id,
                            created_by_student_id=student_id,
                            status=status,
                            source="generated",
                            question=str(q0.get("question") or "").strip(),
                            options={k: str((q0.get("options") or {}).get(k) or "").strip() for k in ("A", "B", "C", "D")},
                            correct=str(q0.get("correct") or "").strip().upper(),
                            required_participants=required,
                            llm_metadata={"subject": subject, "grade": grade},
                        )
                    except Exception as e:
                        await ws.send_json({"type": "study_error", "message": str(e)})
                        continue

                queued = _APP_DB.count_group_study_queued(group_id)
                await _GROUP_HUB.broadcast(group_id, {"type": "study_queue", "queuedCount": int(queued)})

                # If we opened a quiz, broadcast it now.
                if status == "open":
                    oq = _APP_DB.get_open_group_study_quiz(group_id)
                    if oq:
                        required_set = set(str(x) for x in (oq.get("requiredParticipants") or []) if str(x).strip())
                        await _GROUP_HUB.broadcast(
                            group_id,
                            {
                                "type": "study_open",
                                "quizId": oq["id"],
                                "question": oq.get("question"),
                                "options": oq.get("options") or {},
                                "requiredParticipantCount": len(required_set),
                            },
                        )
                        await _GROUP_HUB.broadcast(
                            group_id,
                            {
                                "type": "study_progress",
                                "quizId": oq["id"],
                                "answeredCount": 0,
                                "requiredParticipantCount": len(required_set),
                            },
                        )
                continue

            if typ == "study_answer":
                quiz_id = str((data or {}).get("quizId") or "").strip()
                choice = str((data or {}).get("choice") or "").strip().upper()
                if not quiz_id:
                    await ws.send_json({"type": "study_error", "message": "quizId is required"})
                    continue
                try:
                    _APP_DB.record_group_study_answer(quiz_id=quiz_id, group_id=group_id, student_id=student_id, choice=choice)
                except Exception as e:
                    await ws.send_json({"type": "study_error", "message": str(e)})
                    continue

                open_quiz = _APP_DB.get_open_group_study_quiz(group_id)
                if not open_quiz or str(open_quiz.get("id")) != quiz_id:
                    continue

                required_set = set(str(x) for x in (open_quiz.get("requiredParticipants") or []) if str(x).strip())
                answers = _APP_DB.list_group_study_answers(quiz_id)
                answered_set = {str(a.get("studentId")) for a in answers if str(a.get("studentId")) in required_set}
                await _GROUP_HUB.broadcast(
                    group_id,
                    {
                        "type": "study_progress",
                        "quizId": quiz_id,
                        "answeredCount": len(answered_set),
                        "requiredParticipantCount": len(required_set),
                    },
                )

                # Reveal when everyone required has answered (or no one is required anymore).
                if (not required_set) or answered_set.issuperset(required_set):
                    results = _APP_DB.compute_group_study_results(quiz_id)
                    meta = _APP_DB.get_group_meta(group_id) or {}
                    subject = str(meta.get("subject") or "maths")
                    grade = int(meta.get("grade") or 1)
                    # Map responses to pseudonyms for the LLM.
                    ur = []
                    for r in results.get("responses") or []:
                        sid = str((r or {}).get("studentId") or "").strip()
                        choice2 = str((r or {}).get("choice") or "").strip().upper()
                        s = _APP_DB.get_student(sid) or {}
                        ur.append({"user": str(s.get("pseudonym") or sid[:8] or "Student"), "answer": choice2})
                    try:
                        explanation_text = group_study_explanation(
                            question=str(open_quiz.get("question") or ""),
                            options=(open_quiz.get("options") or {}),
                            correct=str(open_quiz.get("correct") or ""),
                            user_responses=ur,
                            subject=subject,
                            grade=grade,
                        )
                    except Exception:
                        explanation_text = _format_group_study_fallback(
                            options=(open_quiz.get("options") or {}),
                            correct=str(open_quiz.get("correct") or ""),
                            results=results,
                        )
                    _APP_DB.finalize_group_study_reveal(quiz_id, results=results, explanation_text=explanation_text)
                    await _GROUP_HUB.broadcast(
                        group_id,
                        {
                            "type": "study_results",
                            "quizId": quiz_id,
                            "distribution": results.get("distribution") or {},
                            "correct": results.get("correct") or "",
                            "correctCount": results.get("correctCount") or 0,
                            "total": results.get("total") or 0,
                            "explanationText": explanation_text,
                        },
                    )

                    # Open next queued quiz (if any) using current participants snapshot.
                    next_required = sorted(_GROUP_HUB.participants(group_id))
                    _ = _APP_DB.open_next_group_study_quiz_if_any(group_id, required_participants=next_required)
                    queued = _APP_DB.count_group_study_queued(group_id)
                    await _GROUP_HUB.broadcast(group_id, {"type": "study_queue", "queuedCount": int(queued)})
                    oq = _APP_DB.get_open_group_study_quiz(group_id)
                    if oq:
                        req2 = set(str(x) for x in (oq.get("requiredParticipants") or []) if str(x).strip())
                        await _GROUP_HUB.broadcast(
                            group_id,
                            {
                                "type": "study_open",
                                "quizId": oq["id"],
                                "question": oq.get("question"),
                                "options": oq.get("options") or {},
                                "requiredParticipantCount": len(req2),
                            },
                        )
                        await _GROUP_HUB.broadcast(
                            group_id,
                            {
                                "type": "study_progress",
                                "quizId": oq["id"],
                                "answeredCount": 0,
                                "requiredParticipantCount": len(req2),
                            },
                        )
                continue

            # Unknown type
            await ws.send_json({"type": "study_error", "message": f"Unknown message type: {typ}"})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("ws_groups failed")
    finally:
        left_sid = _GROUP_HUB.leave(group_id, ws)
        # If someone leaves during an open study quiz, remove them from required participants and re-check reveal.
        try:
            if left_sid:
                oq = _APP_DB.get_open_group_study_quiz(group_id)
                if oq:
                    required = [str(x) for x in (oq.get("requiredParticipants") or [])]
                    if str(left_sid) in required:
                        required2 = [x for x in required if x != str(left_sid)]
                        _APP_DB.set_required_participants(oq["id"], student_ids=required2)
                        required_set = set(required2)
                        answers = _APP_DB.list_group_study_answers(oq["id"])
                        answered_set = {str(a.get("studentId")) for a in answers if str(a.get("studentId")) in required_set}
                        await _GROUP_HUB.broadcast(
                            group_id,
                            {
                                "type": "study_progress",
                                "quizId": oq["id"],
                                "answeredCount": len(answered_set),
                                "requiredParticipantCount": len(required_set),
                            },
                        )
                        if (not required_set) or answered_set.issuperset(required_set):
                            results = _APP_DB.compute_group_study_results(oq["id"])
                            meta = _APP_DB.get_group_meta(group_id) or {}
                            subject = str(meta.get("subject") or "maths")
                            grade = int(meta.get("grade") or 1)
                            ur = []
                            for r in results.get("responses") or []:
                                sid = str((r or {}).get("studentId") or "").strip()
                                choice2 = str((r or {}).get("choice") or "").strip().upper()
                                s = _APP_DB.get_student(sid) or {}
                                ur.append({"user": str(s.get("pseudonym") or sid[:8] or "Student"), "answer": choice2})
                            try:
                                explanation_text = group_study_explanation(
                                    question=str(oq.get("question") or ""),
                                    options=(oq.get("options") or {}),
                                    correct=str(oq.get("correct") or ""),
                                    user_responses=ur,
                                    subject=subject,
                                    grade=grade,
                                )
                            except Exception:
                                explanation_text = _format_group_study_fallback(
                                    options=(oq.get("options") or {}),
                                    correct=str(oq.get("correct") or ""),
                                    results=results,
                                )
                            _APP_DB.finalize_group_study_reveal(oq["id"], results=results, explanation_text=explanation_text)
                            await _GROUP_HUB.broadcast(
                                group_id,
                                {
                                    "type": "study_results",
                                    "quizId": oq["id"],
                                    "distribution": results.get("distribution") or {},
                                    "correct": results.get("correct") or "",
                                    "correctCount": results.get("correctCount") or 0,
                                    "total": results.get("total") or 0,
                                    "explanationText": explanation_text,
                                },
                            )
        except Exception:
            pass


@app.get("/profiles")
def profiles():
    return {"students": _APP_DB.list_students_public()}


@app.post("/auth/student/set-pin")
def auth_student_set_pin(req: StudentSetPinRequest):
    student = _APP_DB.get_student(req.studentId)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    if bool(student.get("pinSet")):
        raise HTTPException(status_code=409, detail="PIN already set.")
    salt, digest = hash_pin(req.newPin)
    try:
        _APP_DB.set_student_pin_first_time(req.studentId, salt, digest)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    token = _APP_DB.create_session("student", req.studentId)
    s = _APP_DB.get_student(req.studentId) or {}
    return {
        "sessionToken": token,
        "profile": {
            "id": s.get("id"),
            "pseudonym": s.get("pseudonym"),
            "grade": s.get("grade"),
            "avatarKey": s.get("avatarKey"),
            "wallpaperKey": s.get("wallpaperKey"),
            "subjectPref": s.get("subjectPref"),
        },
    }


@app.post("/auth/student/login")
def auth_student_login(req: StudentLoginRequest):
    student = _APP_DB.get_student(req.studentId)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    if not bool(student.get("pinSet")):
        raise HTTPException(status_code=409, detail="PIN not set. Use /auth/student/set-pin first.")
    if not verify_pin(req.pin, student.get("pinSalt") or b"", student.get("pinHash") or b""):
        raise HTTPException(status_code=401, detail="Invalid PIN.")
    token = _APP_DB.create_session("student", req.studentId)
    return {
        "sessionToken": token,
        "profile": {
            "id": student.get("id"),
            "pseudonym": student.get("pseudonym"),
            "grade": student.get("grade"),
            "avatarKey": student.get("avatarKey"),
            "wallpaperKey": student.get("wallpaperKey"),
            "subjectPref": student.get("subjectPref"),
        },
    }


@app.post("/auth/logout")
def auth_logout(request: Request):
    token = _get_bearer_token(request)
    _APP_DB.delete_session(token)
    return {"ok": True}


@app.get("/me")
def me(request: Request):
    student_id = _require_student(request)
    s = _APP_DB.get_student(student_id)
    if not s:
        raise HTTPException(status_code=404, detail="Student not found.")
    return {
        "profile": {
            "id": s.get("id"),
            "pseudonym": s.get("pseudonym"),
            "grade": s.get("grade"),
            "avatarKey": s.get("avatarKey"),
            "wallpaperKey": s.get("wallpaperKey"),
            "subjectPref": s.get("subjectPref"),
        }
    }


@app.patch("/me")
def patch_me(request: Request, body: ProfilePatchRequest):
    student_id = _require_student(request)
    try:
        s = _APP_DB.update_student_profile(
            student_id,
            grade=body.grade,
            avatar_key=body.avatarKey,
            wallpaper_key=body.wallpaperKey,
            subject_pref=body.subjectPref,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "profile": {
            "id": s.get("id"),
            "pseudonym": s.get("pseudonym"),
            "grade": s.get("grade"),
            "avatarKey": s.get("avatarKey"),
            "wallpaperKey": s.get("wallpaperKey"),
            "subjectPref": s.get("subjectPref"),
        }
    }


@app.post("/parent/pin/set")
def parent_pin_set(body: ParentSetPinRequest):
    if _APP_DB.parent_pin_is_set():
        raise HTTPException(status_code=409, detail="Parent PIN already set.")
    salt, digest = hash_pin(body.pin)
    _APP_DB.set_parent_pin(salt, digest)
    return {"ok": True}


@app.post("/parent/login")
def parent_login(body: ParentLoginRequest):
    salt, digest = _APP_DB.get_parent_pin_record()
    if not salt or not digest:
        raise HTTPException(status_code=409, detail="Parent PIN not set yet. Use /parent/pin/set.")
    if not verify_pin(body.pin, salt, digest):
        raise HTTPException(status_code=401, detail="Invalid PIN.")
    token = _APP_DB.create_session("parent", "parent")
    return {"sessionToken": token}


@app.get("/parent/students")
def parent_students(request: Request):
    _ = _require_parent(request)
    return {"students": _APP_DB.list_students_admin()}


@app.post("/parent/student/pin/reset")
def parent_student_pin_reset(request: Request, body: ParentResetStudentPinRequest):
    _ = _require_parent(request)
    sid = str(body.studentId or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="studentId is required")
    if body.newPin is None or not str(body.newPin).strip():
        _APP_DB.clear_student_pin(sid)
        return {"ok": True, "mode": "cleared"}
    salt, digest = hash_pin(str(body.newPin))
    _APP_DB.set_student_pin_reset(sid, salt, digest)
    return {"ok": True, "mode": "set"}


@app.get("/parent/report")
def parent_report(request: Request, studentId: str, days: int = 7):
    _ = _require_parent(request)
    try:
        data = _APP_DB.student_report_data(student_id=studentId, days=int(days))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data


def _sanitize_pseudonym(p: str) -> str:
    v = str(p or "").strip()
    v = " ".join(v.split())
    return v[:40].strip()


def _unique_pseudonym(existing: set[str], desired: str) -> str:
    base = _sanitize_pseudonym(desired) or "Student"
    existing_lower = {e.lower() for e in existing}
    if base.lower() not in existing_lower:
        existing.add(base)
        return base
    i = 2
    while True:
        cand = f"{base} {i}"
        if cand.lower() not in existing_lower:
            existing.add(cand)
            return cand
        i += 1


@app.post("/parent/roster/import")
async def parent_roster_import(request: Request, file: UploadFile = File(...)):
    _ = _require_parent(request)

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except Exception:
        raise HTTPException(status_code=400, detail="Roster must be UTF-8 encoded CSV.")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV must have a header row.")

    existing = set()
    for s in _APP_DB.list_students_public():
        existing.add(str(s.get("pseudonym") or ""))

    created = 0
    errors: list[dict] = []
    for idx, row in enumerate(reader, start=2):  # header is line 1
        try:
            pseudonym = _unique_pseudonym(existing, row.get("pseudonym") or row.get("name") or "")
            grade_raw = (row.get("grade") or "").strip()
            grade = int(grade_raw) if grade_raw else 1
            avatar_key = (row.get("avatarKey") or row.get("avatar_key") or "").strip() or "avatar_01"
            wallpaper_key = (row.get("wallpaperKey") or row.get("wallpaper_key") or "").strip() or "space_01"
            subject_pref = (row.get("subjectPref") or row.get("subject_pref") or "").strip() or None
            student_id = (row.get("studentId") or row.get("id") or "").strip() or str(uuid4())
            _APP_DB.create_student(
                student_id=student_id,
                pseudonym=pseudonym,
                grade=int(grade),
                avatar_key=avatar_key,
                wallpaper_key=wallpaper_key,
                subject_pref=subject_pref,
            )
            created += 1
        except Exception as e:
            errors.append({"line": idx, "error": str(e), "row": row})

    return {"created": created, "errors": errors, "students": _APP_DB.list_students_public()}
