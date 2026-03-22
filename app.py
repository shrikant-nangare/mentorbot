from pathlib import Path
import logging
import time
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from mentor import generate_mcq_quiz, get_vectordb, mentor_response

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
CHAT_HTML_PATH = BASE_DIR / "web" / "chat.html"
STATIC_DIR = BASE_DIR / "web" / "static"


def create_app() -> FastAPI:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()

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


class QuizGenerateRequest(BaseModel):
    concept: str | None = None
    history: list[ChatMessage] = []


class QuizAnswer(BaseModel):
    questionId: str
    choice: str


class QuizSubmitRequest(BaseModel):
    quizId: str
    answers: list[QuizAnswer]


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


@app.get("/health/models")
def health_models():
    return {
        "ollamaEmbedModel": config.OLLAMA_EMBED_MODEL,
        "ollamaLlmModel": config.OLLAMA_LLM_MODEL,
        "ollamaLlmFallbackModel": config.OLLAMA_LLM_FALLBACK_MODEL,
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
def ask(q: Question):
    try:
        answer = mentor_response(
            q.question,
            history=[{"role": m.role, "content": m.content} for m in q.history],
        )
        return {"answer": answer}
    except Exception as e:
        logger.exception("ask failed")
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/quiz/generate")
def quiz_generate(req: QuizGenerateRequest):
    # Opportunistic cleanup to avoid unbounded growth.
    now = time.time()
    expired = [qid for qid, v in QUIZ_STORE.items() if now - float(v.get("created_at", 0)) > QUIZ_TTL_SECONDS]
    for qid in expired:
        QUIZ_STORE.pop(qid, None)
    if len(QUIZ_STORE) > QUIZ_MAX_ITEMS:
        oldest = sorted(QUIZ_STORE.items(), key=lambda kv: float(kv[1].get("created_at", 0)))[: max(1, len(QUIZ_STORE) - QUIZ_MAX_ITEMS)]
        for qid, _ in oldest:
            QUIZ_STORE.pop(qid, None)

    history = [{"role": m.role, "content": m.content} for m in req.history]
    concept = (req.concept or "").strip()
    if not concept:
        # Best-effort: use most recent assistant message as "concept"
        for msg in reversed(history):
            if str(msg.get("role", "")).lower() in {"assistant", "bot"}:
                concept = str(msg.get("content", "")).strip()
                break
    if not concept:
        concept = "the current concept from the conversation"

    try:
        quiz = generate_mcq_quiz(concept=concept, history=history)
    except Exception as e:
        logger.exception("quiz_generate failed")
        raise HTTPException(status_code=503, detail=str(e))
    quiz_id = str(uuid4())
    QUIZ_STORE[quiz_id] = {"quiz": quiz, "created_at": now}

    public_questions = []
    for q in quiz["questions"]:
        public_questions.append(
            {
                "id": q["id"],
                "question": q["question"],
                "options": q["options"],
            }
        )

    return {"quizId": quiz_id, "title": quiz.get("title", "Quick check"), "questions": public_questions}


@app.post("/quiz/submit")
def quiz_submit(req: QuizSubmitRequest):
    record = QUIZ_STORE.get(req.quizId)
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

    if understood:
        message = f"Nice work — {correct_count}/{total} correct ({score_percent}%). Concept understood!"
    else:
        message = f"Good effort — {correct_count}/{total} correct ({score_percent}%). Not quite 60% yet; let's review and try again."

    return {
        "quizId": req.quizId,
        "correctCount": correct_count,
        "total": total,
        "scorePercent": score_percent,
        "understood": understood,
        "message": message,
        "review": review,
    }
