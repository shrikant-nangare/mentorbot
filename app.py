from pathlib import Path
import base64
import binascii
import logging
import secrets
import time
from uuid import uuid4
import csv
import io
import os
import sys

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.responses import PlainTextResponse

import config
from mentor import generate_mcq_quiz, get_vectordb, is_explain_request, mentor_response, suggest_topics
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
    auth = str(request.headers.get("authorization", "") or "").strip()
    if not auth.lower().startswith("bearer "):
        return ""
    return auth.split(" ", 1)[1].strip()


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


def _require_student_token(token: str) -> str:
    t = str(token or "").strip()
    sess = _APP_DB.verify_session(t)
    if not sess or sess[0] != "student":
        raise HTTPException(status_code=401, detail="Unauthorized")
    return str(sess[1])


class _GroupHub:
    def __init__(self):
        self._lock = threading.Lock()
        self._conns: dict[str, set[WebSocket]] = {}

    async def join(self, group_id: str, ws: WebSocket) -> None:
        await ws.accept()
        with self._lock:
            self._conns.setdefault(group_id, set()).add(ws)

    def leave(self, group_id: str, ws: WebSocket) -> None:
        with self._lock:
            s = self._conns.get(group_id)
            if not s:
                return
            s.discard(ws)
            if not s:
                self._conns.pop(group_id, None)

    async def broadcast(self, group_id: str, payload: dict) -> None:
        with self._lock:
            conns = list(self._conns.get(group_id, set()))
        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception:
                self.leave(group_id, ws)


import threading

_GROUP_HUB = _GroupHub()

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


@app.post("/ask")
def ask(request: Request, q: Question):
    student_id = _require_student(request)
    student = _APP_DB.get_student(student_id)
    if not student:
        raise HTTPException(status_code=401, detail="Unauthorized")

    subject = (q.subject or student.get("subjectPref") or "maths").strip().lower()
    grade = int(q.grade or student.get("grade") or 1)

    try:
        history = [{"role": m.role, "content": m.content} for m in q.history]
        answer = mentor_response(q.question, history=history)
        quiz_required = bool(is_explain_request(q.question))
        concept_id: str | None = None
        if quiz_required:
            concept_id = _APP_DB.create_concept(
                student_id=student_id,
                subject=subject,
                grade=grade,
                concept_text=str(q.question or "").strip(),
            )
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


@app.post("/quiz/generate")
def quiz_generate(request: Request, req: QuizGenerateRequest):
    student_id = _require_student(request)
    student = _APP_DB.get_student(student_id)
    if not student:
        raise HTTPException(status_code=401, detail="Unauthorized")

    subject = (req.subject or student.get("subjectPref") or "maths").strip().lower()
    grade = int(req.grade or student.get("grade") or 1)

    concept_id = (req.conceptId or "").strip() or _APP_DB.get_latest_pending_concept_id(student_id)
    if not concept_id:
        # Fallback: create a concept from the current context, so the quiz still has a progression anchor.
        concept_text = (req.concept or "the current concept from the conversation").strip()
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
        quiz = generate_mcq_quiz(concept=concept, history=history, difficulty=difficulty)
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


@app.websocket("/ws/groups/{group_id}")
async def ws_groups(group_id: str, ws: WebSocket):
    token = str(ws.query_params.get("token") or "").strip()
    try:
        student_id = _require_student_token(token)
    except HTTPException:
        await ws.close(code=1008)
        return

    try:
        await _GROUP_HUB.join(group_id, ws)
        # Send recent messages on join.
        try:
            msgs = _APP_DB.list_group_messages(group_id=group_id, limit=50)
            await ws.send_json({"type": "history", "messages": msgs})
        except Exception:
            pass

        while True:
            data = await ws.receive_json()
            body = str((data or {}).get("body") or "").strip()
            if not body:
                continue
            msg = _APP_DB.add_group_message(group_id=group_id, student_id=student_id, body=body)
            await _GROUP_HUB.broadcast(group_id, {"type": "message", "message": msg})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("ws_groups failed")
    finally:
        _GROUP_HUB.leave(group_id, ws)


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
