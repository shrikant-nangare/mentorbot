import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4


PrincipalType = Literal["student", "parent"]


@dataclass(frozen=True)
class AppDbConfig:
    path: str
    session_ttl_s: int


def _now() -> int:
    return int(time.time())


def _sha256_bytes(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


class AppDb:
    def __init__(self, config: AppDbConfig):
        self._path = str(config.path or "").strip()
        if not self._path:
            raise ValueError("App DB path is empty.")
        self._session_ttl_s = int(config.session_ttl_s)
        self._lock = threading.Lock()

        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            conn = _connect(self._path)
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS students (
                      id TEXT PRIMARY KEY,
                      pseudonym TEXT NOT NULL,
                      grade INTEGER NOT NULL,
                      avatar_key TEXT NOT NULL,
                      wallpaper_key TEXT NOT NULL,
                      created_at INTEGER NOT NULL,
                      pin_salt BLOB,
                      pin_hash BLOB,
                      pin_set_at INTEGER,
                      subject_pref TEXT
                    );

                    CREATE TABLE IF NOT EXISTS parent_settings (
                      id INTEGER PRIMARY KEY CHECK (id = 1),
                      pin_salt BLOB,
                      pin_hash BLOB,
                      pin_set_at INTEGER
                    );

                    CREATE TABLE IF NOT EXISTS sessions (
                      token_hash BLOB PRIMARY KEY,
                      principal_type TEXT NOT NULL,
                      principal_id TEXT NOT NULL,
                      created_at INTEGER NOT NULL,
                      expires_at INTEGER NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);

                    CREATE TABLE IF NOT EXISTS concepts (
                      id TEXT PRIMARY KEY,
                      student_id TEXT NOT NULL,
                      subject TEXT NOT NULL,
                      grade INTEGER NOT NULL,
                      concept_text TEXT NOT NULL,
                      created_at INTEGER NOT NULL,
                      status TEXT NOT NULL,
                      last_quiz_at INTEGER,
                      skipped_at INTEGER,
                      FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_concepts_student_status ON concepts(student_id, status);
                    CREATE INDEX IF NOT EXISTS idx_concepts_created_at ON concepts(created_at);

                    CREATE TABLE IF NOT EXISTS quizzes (
                      id TEXT PRIMARY KEY,
                      student_id TEXT NOT NULL,
                      concept_id TEXT NOT NULL,
                      created_at INTEGER NOT NULL,
                      difficulty TEXT NOT NULL,
                      quiz_json TEXT NOT NULL,
                      FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
                      FOREIGN KEY(concept_id) REFERENCES concepts(id) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_quizzes_student_created_at ON quizzes(student_id, created_at);

                    CREATE TABLE IF NOT EXISTS quiz_attempts (
                      id TEXT PRIMARY KEY,
                      quiz_id TEXT NOT NULL,
                      student_id TEXT NOT NULL,
                      concept_id TEXT NOT NULL,
                      created_at INTEGER NOT NULL,
                      score_percent REAL NOT NULL,
                      correct_count INTEGER NOT NULL,
                      total INTEGER NOT NULL,
                      understood INTEGER NOT NULL,
                      difficulty TEXT NOT NULL,
                      FOREIGN KEY(quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE,
                      FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
                      FOREIGN KEY(concept_id) REFERENCES concepts(id) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_attempts_student_created_at ON quiz_attempts(student_id, created_at);
                    CREATE INDEX IF NOT EXISTS idx_attempts_concept_created_at ON quiz_attempts(concept_id, created_at);

                    CREATE TABLE IF NOT EXISTS notes (
                      id TEXT PRIMARY KEY,
                      student_id TEXT NOT NULL,
                      subject TEXT NOT NULL,
                      grade INTEGER NOT NULL,
                      title TEXT NOT NULL,
                      body TEXT NOT NULL,
                      source TEXT NOT NULL,
                      created_at INTEGER NOT NULL,
                      updated_at INTEGER NOT NULL,
                      FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_notes_student_updated_at ON notes(student_id, updated_at);

                    CREATE TABLE IF NOT EXISTS groups (
                      id TEXT PRIMARY KEY,
                      invite_code TEXT NOT NULL UNIQUE,
                      name TEXT NOT NULL,
                      subject TEXT NOT NULL,
                      grade INTEGER NOT NULL,
                      created_at INTEGER NOT NULL,
                      created_by_student_id TEXT NOT NULL,
                      FOREIGN KEY(created_by_student_id) REFERENCES students(id) ON DELETE CASCADE
                    );

                    CREATE TABLE IF NOT EXISTS group_members (
                      group_id TEXT NOT NULL,
                      student_id TEXT NOT NULL,
                      joined_at INTEGER NOT NULL,
                      PRIMARY KEY(group_id, student_id),
                      FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE,
                      FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
                    );

                    CREATE TABLE IF NOT EXISTS group_messages (
                      id TEXT PRIMARY KEY,
                      group_id TEXT NOT NULL,
                      student_id TEXT NOT NULL,
                      body TEXT NOT NULL,
                      created_at INTEGER NOT NULL,
                      FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE,
                      FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_group_messages_group_created_at ON group_messages(group_id, created_at);
                    """.strip()
                )
                conn.execute("INSERT OR IGNORE INTO parent_settings(id) VALUES (1)")
                conn.commit()
            finally:
                conn.close()

    def _purge_expired_sessions(self, conn: sqlite3.Connection, now: int) -> None:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (int(now),))

    # ---------- Students ----------
    def list_students_public(self) -> list[dict[str, Any]]:
        with self._lock:
            conn = _connect(self._path)
            try:
                rows = conn.execute(
                    """
                    SELECT id, pseudonym, grade, avatar_key, wallpaper_key,
                           CASE WHEN pin_hash IS NOT NULL THEN 1 ELSE 0 END AS pin_set
                    FROM students
                    ORDER BY pseudonym COLLATE NOCASE ASC
                    """
                ).fetchall()
                return [
                    {
                        "id": str(r["id"]),
                        "pseudonym": str(r["pseudonym"]),
                        "grade": int(r["grade"]),
                        "avatarKey": str(r["avatar_key"]),
                        "wallpaperKey": str(r["wallpaper_key"]),
                        "pinSet": bool(int(r["pin_set"])),
                    }
                    for r in rows
                ]
            finally:
                conn.close()

    def create_student(
        self,
        *,
        student_id: str,
        pseudonym: str,
        grade: int,
        avatar_key: str,
        wallpaper_key: str,
        subject_pref: str | None = None,
    ) -> None:
        sid = str(student_id or "").strip()
        if not sid:
            raise ValueError("student_id is empty")
        p = str(pseudonym or "").strip()
        if not p:
            raise ValueError("pseudonym is empty")
        g = int(grade)
        if g < 1 or g > 12:
            raise ValueError("grade must be 1..12")
        a = str(avatar_key or "").strip() or "avatar_01"
        w = str(wallpaper_key or "").strip() or "space_01"
        sp = (str(subject_pref).strip() if subject_pref is not None else None) or None

        now = _now()
        with self._lock:
            conn = _connect(self._path)
            try:
                conn.execute(
                    """
                    INSERT INTO students(id, pseudonym, grade, avatar_key, wallpaper_key, created_at, subject_pref)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (sid, p, int(g), a, w, int(now), sp),
                )
                conn.commit()
            finally:
                conn.close()

    def get_student(self, student_id: str) -> dict[str, Any] | None:
        sid = str(student_id or "").strip()
        if not sid:
            return None
        with self._lock:
            conn = _connect(self._path)
            try:
                r = conn.execute(
                    """
                    SELECT id, pseudonym, grade, avatar_key, wallpaper_key, subject_pref,
                           pin_salt, pin_hash, pin_set_at
                    FROM students WHERE id = ?
                    """,
                    (sid,),
                ).fetchone()
                if not r:
                    return None
                return {
                    "id": str(r["id"]),
                    "pseudonym": str(r["pseudonym"]),
                    "grade": int(r["grade"]),
                    "avatarKey": str(r["avatar_key"]),
                    "wallpaperKey": str(r["wallpaper_key"]),
                    "subjectPref": (str(r["subject_pref"]) if r["subject_pref"] is not None else None),
                    "pinSet": bool(r["pin_hash"] is not None),
                    "pinSalt": r["pin_salt"],
                    "pinHash": r["pin_hash"],
                    "pinSetAt": (int(r["pin_set_at"]) if r["pin_set_at"] is not None else None),
                }
            finally:
                conn.close()

    def update_student_profile(
        self,
        student_id: str,
        *,
        grade: int | None = None,
        avatar_key: str | None = None,
        wallpaper_key: str | None = None,
        subject_pref: str | None = None,
    ) -> dict[str, Any]:
        sid = str(student_id or "").strip()
        if not sid:
            raise ValueError("student_id is empty")

        sets: list[str] = []
        vals: list[Any] = []
        if grade is not None:
            g = int(grade)
            if g < 1 or g > 12:
                raise ValueError("grade must be 1..12")
            sets.append("grade = ?")
            vals.append(int(g))
        if avatar_key is not None:
            sets.append("avatar_key = ?")
            vals.append(str(avatar_key or "").strip() or "avatar_01")
        if wallpaper_key is not None:
            sets.append("wallpaper_key = ?")
            vals.append(str(wallpaper_key or "").strip() or "space_01")
        if subject_pref is not None:
            sp = str(subject_pref or "").strip()
            sets.append("subject_pref = ?")
            vals.append(sp or None)

        if not sets:
            out = self.get_student(student_id)
            if not out:
                raise ValueError("student not found")
            return out

        with self._lock:
            conn = _connect(self._path)
            try:
                vals.append(sid)
                conn.execute(f"UPDATE students SET {', '.join(sets)} WHERE id = ?", tuple(vals))
                conn.commit()
            finally:
                conn.close()

        out = self.get_student(student_id)
        if not out:
            raise ValueError("student not found")
        return out

    # ---------- PINs ----------
    def set_student_pin_first_time(self, student_id: str, pin_salt: bytes, pin_hash: bytes) -> None:
        sid = str(student_id or "").strip()
        if not sid:
            raise ValueError("student_id is empty")
        if not pin_salt or not pin_hash:
            raise ValueError("pin_salt/pin_hash are empty")
        now = _now()
        with self._lock:
            conn = _connect(self._path)
            try:
                # First-time set only (prevents silent takeover).
                cur = conn.execute("SELECT pin_hash FROM students WHERE id = ?", (sid,)).fetchone()
                if not cur:
                    raise ValueError("student not found")
                if cur["pin_hash"] is not None:
                    raise ValueError("PIN already set")
                conn.execute(
                    """
                    UPDATE students
                    SET pin_salt = ?, pin_hash = ?, pin_set_at = ?
                    WHERE id = ?
                    """,
                    (pin_salt, pin_hash, int(now), sid),
                )
                conn.commit()
            finally:
                conn.close()

    def set_student_pin_reset(self, student_id: str, pin_salt: bytes, pin_hash: bytes) -> None:
        sid = str(student_id or "").strip()
        if not sid:
            raise ValueError("student_id is empty")
        now = _now()
        with self._lock:
            conn = _connect(self._path)
            try:
                conn.execute(
                    """
                    UPDATE students
                    SET pin_salt = ?, pin_hash = ?, pin_set_at = ?
                    WHERE id = ?
                    """,
                    (pin_salt, pin_hash, int(now), sid),
                )
                conn.commit()
            finally:
                conn.close()

    # ---------- Parent PIN ----------
    def parent_pin_is_set(self) -> bool:
        with self._lock:
            conn = _connect(self._path)
            try:
                r = conn.execute("SELECT pin_hash FROM parent_settings WHERE id = 1").fetchone()
                return bool(r and r["pin_hash"] is not None)
            finally:
                conn.close()

    def get_parent_pin_record(self) -> tuple[bytes | None, bytes | None]:
        with self._lock:
            conn = _connect(self._path)
            try:
                r = conn.execute("SELECT pin_salt, pin_hash FROM parent_settings WHERE id = 1").fetchone()
                if not r:
                    return (None, None)
                return (r["pin_salt"], r["pin_hash"])
            finally:
                conn.close()

    def set_parent_pin(self, pin_salt: bytes, pin_hash: bytes) -> None:
        now = _now()
        with self._lock:
            conn = _connect(self._path)
            try:
                conn.execute(
                    """
                    UPDATE parent_settings
                    SET pin_salt = ?, pin_hash = ?, pin_set_at = ?
                    WHERE id = 1
                    """,
                    (pin_salt, pin_hash, int(now)),
                )
                conn.commit()
            finally:
                conn.close()

    # ---------- Sessions ----------
    def create_session(self, principal_type: PrincipalType, principal_id: str) -> str:
        pid = str(principal_id or "").strip()
        if not pid:
            raise ValueError("principal_id is empty")
        pt = str(principal_type or "").strip()
        if pt not in {"student", "parent"}:
            raise ValueError("principal_type invalid")

        token = secrets.token_urlsafe(32)
        token_hash = _sha256_bytes(token.encode("utf-8"))
        now = _now()
        expires_at = now + max(60, int(self._session_ttl_s))
        with self._lock:
            conn = _connect(self._path)
            try:
                self._purge_expired_sessions(conn, now)
                conn.execute(
                    """
                    INSERT INTO sessions(token_hash, principal_type, principal_id, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (token_hash, pt, pid, int(now), int(expires_at)),
                )
                conn.commit()
            finally:
                conn.close()
        return token

    def delete_session(self, token: str) -> None:
        t = str(token or "").strip()
        if not t:
            return
        token_hash = _sha256_bytes(t.encode("utf-8"))
        with self._lock:
            conn = _connect(self._path)
            try:
                conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
                conn.commit()
            finally:
                conn.close()

    def verify_session(self, token: str) -> tuple[PrincipalType, str] | None:
        t = str(token or "").strip()
        if not t:
            return None
        token_hash = _sha256_bytes(t.encode("utf-8"))
        now = _now()
        with self._lock:
            conn = _connect(self._path)
            try:
                self._purge_expired_sessions(conn, now)
                r = conn.execute(
                    """
                    SELECT principal_type, principal_id, expires_at
                    FROM sessions
                    WHERE token_hash = ?
                    """,
                    (token_hash,),
                ).fetchone()
                if not r:
                    conn.commit()
                    return None
                if int(r["expires_at"]) < now:
                    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
                    conn.commit()
                    return None
                pt = str(r["principal_type"])
                pid = str(r["principal_id"])
                if pt not in {"student", "parent"}:
                    return None
                return (pt, pid)
            finally:
                conn.close()

    # ---------- Concepts / Quizzes / Attempts ----------
    def create_concept(
        self,
        *,
        student_id: str,
        subject: str,
        grade: int,
        concept_text: str,
    ) -> str:
        sid = str(student_id or "").strip()
        if not sid:
            raise ValueError("student_id is empty")
        subj = str(subject or "").strip().lower() or "maths"
        g = int(grade)
        if g < 1 or g > 12:
            raise ValueError("grade must be 1..12")
        text = str(concept_text or "").strip()
        if not text:
            raise ValueError("concept_text is empty")

        cid = str(uuid4())
        now = _now()
        with self._lock:
            conn = _connect(self._path)
            try:
                conn.execute(
                    """
                    INSERT INTO concepts(id, student_id, subject, grade, concept_text, created_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (cid, sid, subj, int(g), text, int(now), "pending"),
                )
                conn.commit()
            finally:
                conn.close()
        return cid

    def get_latest_pending_concept_id(self, student_id: str) -> str | None:
        sid = str(student_id or "").strip()
        if not sid:
            return None
        with self._lock:
            conn = _connect(self._path)
            try:
                r = conn.execute(
                    """
                    SELECT id FROM concepts
                    WHERE student_id = ? AND status = 'pending'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (sid,),
                ).fetchone()
                return str(r["id"]) if r else None
            finally:
                conn.close()

    def count_skips_last_24h(self, student_id: str) -> int:
        sid = str(student_id or "").strip()
        if not sid:
            return 0
        now = _now()
        since = now - 24 * 60 * 60
        with self._lock:
            conn = _connect(self._path)
            try:
                r = conn.execute(
                    """
                    SELECT COUNT(*) AS c
                    FROM concepts
                    WHERE student_id = ? AND skipped_at IS NOT NULL AND skipped_at >= ?
                    """,
                    (sid, int(since)),
                ).fetchone()
                return int(r["c"]) if r else 0
            finally:
                conn.close()

    def mark_concept_skipped(self, student_id: str, concept_id: str) -> None:
        sid = str(student_id or "").strip()
        cid = str(concept_id or "").strip()
        if not sid or not cid:
            raise ValueError("student_id/concept_id is empty")
        now = _now()
        with self._lock:
            conn = _connect(self._path)
            try:
                conn.execute(
                    """
                    UPDATE concepts
                    SET status = 'skipped', skipped_at = ?
                    WHERE id = ? AND student_id = ?
                    """,
                    (int(now), cid, sid),
                )
                conn.commit()
            finally:
                conn.close()

    def mark_concept_passed(self, student_id: str, concept_id: str) -> None:
        sid = str(student_id or "").strip()
        cid = str(concept_id or "").strip()
        if not sid or not cid:
            raise ValueError("student_id/concept_id is empty")
        now = _now()
        with self._lock:
            conn = _connect(self._path)
            try:
                conn.execute(
                    """
                    UPDATE concepts
                    SET status = 'passed', last_quiz_at = ?
                    WHERE id = ? AND student_id = ?
                    """,
                    (int(now), cid, sid),
                )
                conn.commit()
            finally:
                conn.close()

    def record_quiz(self, *, student_id: str, concept_id: str, difficulty: str, quiz: dict) -> str:
        sid = str(student_id or "").strip()
        cid = str(concept_id or "").strip()
        if not sid or not cid:
            raise ValueError("student_id/concept_id is empty")
        diff = str(difficulty or "").strip().lower() or "medium"
        try:
            quiz_json = json.dumps(quiz, ensure_ascii=False)
        except Exception as e:
            raise ValueError(f"quiz is not JSON-serializable: {e}")
        qid = str(uuid4())
        now = _now()
        with self._lock:
            conn = _connect(self._path)
            try:
                conn.execute(
                    """
                    INSERT INTO quizzes(id, student_id, concept_id, created_at, difficulty, quiz_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (qid, sid, cid, int(now), diff, quiz_json),
                )
                conn.execute(
                    "UPDATE concepts SET last_quiz_at = ? WHERE id = ? AND student_id = ?",
                    (int(now), cid, sid),
                )
                conn.commit()
            finally:
                conn.close()
        return qid

    def get_quiz(self, quiz_id: str, student_id: str) -> dict[str, Any] | None:
        qid = str(quiz_id or "").strip()
        sid = str(student_id or "").strip()
        if not qid or not sid:
            return None
        with self._lock:
            conn = _connect(self._path)
            try:
                r = conn.execute(
                    """
                    SELECT id, student_id, concept_id, created_at, difficulty, quiz_json
                    FROM quizzes
                    WHERE id = ? AND student_id = ?
                    """,
                    (qid, sid),
                ).fetchone()
                if not r:
                    return None
                try:
                    quiz = json.loads(str(r["quiz_json"] or "{}"))
                except Exception:
                    quiz = {}
                return {
                    "id": str(r["id"]),
                    "studentId": str(r["student_id"]),
                    "conceptId": str(r["concept_id"]),
                    "createdAt": int(r["created_at"]),
                    "difficulty": str(r["difficulty"]),
                    "quiz": quiz,
                }
            finally:
                conn.close()

    def get_concept_meta(self, student_id: str, concept_id: str) -> dict[str, Any] | None:
        sid = str(student_id or "").strip()
        cid = str(concept_id or "").strip()
        if not sid or not cid:
            return None
        with self._lock:
            conn = _connect(self._path)
            try:
                r = conn.execute(
                    """
                    SELECT id, subject, grade, concept_text, status, created_at
                    FROM concepts
                    WHERE id = ? AND student_id = ?
                    """,
                    (cid, sid),
                ).fetchone()
                if not r:
                    return None
                return {
                    "id": str(r["id"]),
                    "subject": str(r["subject"]),
                    "grade": int(r["grade"]),
                    "conceptText": str(r["concept_text"]),
                    "status": str(r["status"]),
                    "createdAt": int(r["created_at"]),
                }
            finally:
                conn.close()

    def add_attempt(
        self,
        *,
        quiz_id: str,
        student_id: str,
        concept_id: str,
        score_percent: float,
        correct_count: int,
        total: int,
        understood: bool,
        difficulty: str,
    ) -> str:
        aid = str(uuid4())
        now = _now()
        with self._lock:
            conn = _connect(self._path)
            try:
                conn.execute(
                    """
                    INSERT INTO quiz_attempts(
                      id, quiz_id, student_id, concept_id, created_at,
                      score_percent, correct_count, total, understood, difficulty
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        aid,
                        str(quiz_id),
                        str(student_id),
                        str(concept_id),
                        int(now),
                        float(score_percent),
                        int(correct_count),
                        int(total),
                        1 if understood else 0,
                        str(difficulty or "").strip().lower() or "medium",
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return aid

    def recent_performance(self, student_id: str, n: int = 5) -> dict[str, Any]:
        sid = str(student_id or "").strip()
        if not sid:
            return {"avg": None, "count": 0}
        n = max(1, min(int(n), 30))
        with self._lock:
            conn = _connect(self._path)
            try:
                rows = conn.execute(
                    """
                    SELECT score_percent
                    FROM quiz_attempts
                    WHERE student_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (sid, int(n)),
                ).fetchall()
                scores = [float(r["score_percent"]) for r in rows if r and r["score_percent"] is not None]
                if not scores:
                    return {"avg": None, "count": 0}
                return {"avg": sum(scores) / len(scores), "count": len(scores)}
            finally:
                conn.close()

    def compare_stats(self, student_id: str, subject: str, grade: int) -> dict[str, Any]:
        sid = str(student_id or "").strip()
        subj = str(subject or "").strip().lower() or "maths"
        g = int(grade)
        with self._lock:
            conn = _connect(self._path)
            try:
                # Student avg for this subject+grade
                r1 = conn.execute(
                    """
                    SELECT AVG(a.score_percent) AS avg_score, COUNT(*) AS c
                    FROM quiz_attempts a
                    JOIN concepts cpt ON cpt.id = a.concept_id
                    WHERE a.student_id = ? AND cpt.subject = ? AND cpt.grade = ?
                    """,
                    (sid, subj, int(g)),
                ).fetchone()
                your_avg = float(r1["avg_score"]) if r1 and r1["avg_score"] is not None else None

                # Cohort distribution for same subject+grade (all students)
                rows = conn.execute(
                    """
                    SELECT a.student_id AS student_id, AVG(a.score_percent) AS avg_score
                    FROM quiz_attempts a
                    JOIN concepts cpt ON cpt.id = a.concept_id
                    WHERE cpt.subject = ? AND cpt.grade = ?
                    GROUP BY a.student_id
                    """,
                    (subj, int(g)),
                ).fetchall()
                cohort = [float(r["avg_score"]) for r in rows if r and r["avg_score"] is not None]
                sample_size = len(cohort)
                cohort_avg = (sum(cohort) / sample_size) if cohort else None
                percentile = None
                if your_avg is not None and cohort:
                    below = sum(1 for v in cohort if v < your_avg)
                    equal = sum(1 for v in cohort if v == your_avg)
                    # Mid-rank percentile
                    percentile = ((below + 0.5 * equal) / sample_size) * 100.0

                return {
                    "yourAvg": your_avg,
                    "cohortAvg": cohort_avg,
                    "percentile": percentile,
                    "sampleSize": sample_size,
                }
            finally:
                conn.close()

    # ---------- Notes ----------
    def list_notes(self, student_id: str, subject: str, grade: int) -> list[dict[str, Any]]:
        sid = str(student_id or "").strip()
        subj = str(subject or "").strip().lower() or "maths"
        g = int(grade)
        with self._lock:
            conn = _connect(self._path)
            try:
                rows = conn.execute(
                    """
                    SELECT id, title, body, source, created_at, updated_at
                    FROM notes
                    WHERE student_id = ? AND subject = ? AND grade = ?
                    ORDER BY updated_at DESC
                    LIMIT 200
                    """,
                    (sid, subj, int(g)),
                ).fetchall()
                return [
                    {
                        "id": str(r["id"]),
                        "title": str(r["title"]),
                        "body": str(r["body"]),
                        "source": str(r["source"]),
                        "createdAt": int(r["created_at"]),
                        "updatedAt": int(r["updated_at"]),
                    }
                    for r in rows
                ]
            finally:
                conn.close()

    def create_note(self, student_id: str, subject: str, grade: int, title: str, body: str, source: str) -> str:
        sid = str(student_id or "").strip()
        subj = str(subject or "").strip().lower() or "maths"
        g = int(grade)
        t = str(title or "").strip()[:120] or "Note"
        b = str(body or "").strip()
        if not b:
            raise ValueError("Note body is empty")
        src = str(source or "").strip()[:40] or "manual"
        nid = str(uuid4())
        now = _now()
        with self._lock:
            conn = _connect(self._path)
            try:
                conn.execute(
                    """
                    INSERT INTO notes(id, student_id, subject, grade, title, body, source, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (nid, sid, subj, int(g), t, b, src, int(now), int(now)),
                )
                conn.commit()
            finally:
                conn.close()
        return nid

    def update_note(self, student_id: str, note_id: str, title: str | None = None, body: str | None = None) -> None:
        sid = str(student_id or "").strip()
        nid = str(note_id or "").strip()
        if not sid or not nid:
            raise ValueError("student_id/note_id is empty")
        sets: list[str] = []
        vals: list[Any] = []
        if title is not None:
            sets.append("title = ?")
            vals.append((str(title or "").strip()[:120] or "Note"))
        if body is not None:
            b = str(body or "").strip()
            if not b:
                raise ValueError("Note body is empty")
            sets.append("body = ?")
            vals.append(b)
        if not sets:
            return
        sets.append("updated_at = ?")
        vals.append(int(_now()))
        vals.extend([nid, sid])
        with self._lock:
            conn = _connect(self._path)
            try:
                conn.execute(
                    f"UPDATE notes SET {', '.join(sets)} WHERE id = ? AND student_id = ?",
                    tuple(vals),
                )
                conn.commit()
            finally:
                conn.close()

    def delete_note(self, student_id: str, note_id: str) -> None:
        sid = str(student_id or "").strip()
        nid = str(note_id or "").strip()
        with self._lock:
            conn = _connect(self._path)
            try:
                conn.execute("DELETE FROM notes WHERE id = ? AND student_id = ?", (nid, sid))
                conn.commit()
            finally:
                conn.close()

    # ---------- Groups ----------
    def create_group(self, student_id: str, name: str, subject: str, grade: int) -> dict[str, Any]:
        sid = str(student_id or "").strip()
        if not sid:
            raise ValueError("student_id is empty")
        nm = str(name or "").strip()[:60] or "Study group"
        subj = str(subject or "").strip().lower() or "maths"
        g = int(grade)
        if g < 1 or g > 12:
            raise ValueError("grade must be 1..12")
        gid = str(uuid4())
        invite = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8]
        now = _now()
        with self._lock:
            conn = _connect(self._path)
            try:
                conn.execute(
                    """
                    INSERT INTO groups(id, invite_code, name, subject, grade, created_at, created_by_student_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (gid, invite, nm, subj, int(g), int(now), sid),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO group_members(group_id, student_id, joined_at)
                    VALUES (?, ?, ?)
                    """,
                    (gid, sid, int(now)),
                )
                conn.commit()
            finally:
                conn.close()
        return {"id": gid, "inviteCode": invite, "name": nm, "subject": subj, "grade": g}

    def join_group_by_invite(self, student_id: str, invite_code: str) -> dict[str, Any]:
        sid = str(student_id or "").strip()
        code = str(invite_code or "").strip()
        if not sid or not code:
            raise ValueError("student_id/invite_code is empty")
        now = _now()
        with self._lock:
            conn = _connect(self._path)
            try:
                g = conn.execute(
                    "SELECT id, invite_code, name, subject, grade FROM groups WHERE invite_code = ?",
                    (code,),
                ).fetchone()
                if not g:
                    raise ValueError("Invite code not found")
                gid = str(g["id"])
                conn.execute(
                    "INSERT OR IGNORE INTO group_members(group_id, student_id, joined_at) VALUES (?, ?, ?)",
                    (gid, sid, int(now)),
                )
                conn.commit()
                return {
                    "id": gid,
                    "inviteCode": str(g["invite_code"]),
                    "name": str(g["name"]),
                    "subject": str(g["subject"]),
                    "grade": int(g["grade"]),
                }
            finally:
                conn.close()

    def list_groups_for_student(self, student_id: str) -> list[dict[str, Any]]:
        sid = str(student_id or "").strip()
        if not sid:
            return []
        with self._lock:
            conn = _connect(self._path)
            try:
                rows = conn.execute(
                    """
                    SELECT g.id, g.invite_code, g.name, g.subject, g.grade, g.created_at
                    FROM groups g
                    JOIN group_members m ON m.group_id = g.id
                    WHERE m.student_id = ?
                    ORDER BY g.created_at DESC
                    """,
                    (sid,),
                ).fetchall()
                return [
                    {
                        "id": str(r["id"]),
                        "inviteCode": str(r["invite_code"]),
                        "name": str(r["name"]),
                        "subject": str(r["subject"]),
                        "grade": int(r["grade"]),
                        "createdAt": int(r["created_at"]),
                    }
                    for r in rows
                ]
            finally:
                conn.close()

    # ---------- Parent/Admin helpers ----------
    def list_students_admin(self) -> list[dict[str, Any]]:
        with self._lock:
            conn = _connect(self._path)
            try:
                rows = conn.execute(
                    """
                    SELECT id, pseudonym, grade, avatar_key, wallpaper_key,
                           CASE WHEN pin_hash IS NOT NULL THEN 1 ELSE 0 END AS pin_set
                    FROM students
                    ORDER BY pseudonym COLLATE NOCASE ASC
                    """
                ).fetchall()
                return [
                    {
                        "id": str(r["id"]),
                        "pseudonym": str(r["pseudonym"]),
                        "grade": int(r["grade"]),
                        "avatarKey": str(r["avatar_key"]),
                        "wallpaperKey": str(r["wallpaper_key"]),
                        "pinSet": bool(int(r["pin_set"])),
                    }
                    for r in rows
                ]
            finally:
                conn.close()

    def clear_student_pin(self, student_id: str) -> None:
        sid = str(student_id or "").strip()
        if not sid:
            raise ValueError("student_id is empty")
        with self._lock:
            conn = _connect(self._path)
            try:
                conn.execute(
                    """
                    UPDATE students
                    SET pin_salt = NULL, pin_hash = NULL, pin_set_at = NULL
                    WHERE id = ?
                    """,
                    (sid,),
                )
                conn.commit()
            finally:
                conn.close()

    def student_report_data(self, student_id: str, days: int) -> dict[str, Any]:
        sid = str(student_id or "").strip()
        if not sid:
            raise ValueError("student_id is empty")
        days = max(1, min(int(days), 365))
        now = _now()
        since = now - days * 24 * 60 * 60
        with self._lock:
            conn = _connect(self._path)
            try:
                s = conn.execute(
                    "SELECT id, pseudonym, grade, subject_pref FROM students WHERE id = ?",
                    (sid,),
                ).fetchone()
                if not s:
                    raise ValueError("student not found")

                concepts = conn.execute(
                    """
                    SELECT id, subject, grade, concept_text, created_at, status
                    FROM concepts
                    WHERE student_id = ? AND created_at >= ?
                    ORDER BY created_at DESC
                    LIMIT 200
                    """,
                    (sid, int(since)),
                ).fetchall()

                attempts = conn.execute(
                    """
                    SELECT a.created_at, a.score_percent, a.understood, cpt.subject, cpt.grade, cpt.concept_text
                    FROM quiz_attempts a
                    JOIN concepts cpt ON cpt.id = a.concept_id
                    WHERE a.student_id = ? AND a.created_at >= ?
                    ORDER BY a.created_at DESC
                    LIMIT 300
                    """,
                    (sid, int(since)),
                ).fetchall()

                by_subject: dict[str, list[float]] = {}
                understood_count = 0
                for r in attempts:
                    subj = str(r["subject"])
                    by_subject.setdefault(subj, []).append(float(r["score_percent"]))
                    if int(r["understood"]) == 1:
                        understood_count += 1

                subject_summaries = []
                for subj, scores in sorted(by_subject.items(), key=lambda kv: kv[0]):
                    subject_summaries.append(
                        {
                            "subject": subj,
                            "avgScore": (sum(scores) / len(scores)) if scores else None,
                            "attempts": len(scores),
                        }
                    )

                return {
                    "student": {
                        "id": str(s["id"]),
                        "pseudonym": str(s["pseudonym"]),
                        "grade": int(s["grade"]),
                        "subjectPref": (str(s["subject_pref"]) if s["subject_pref"] is not None else None),
                    },
                    "rangeDays": days,
                    "concepts": [
                        {
                            "id": str(c["id"]),
                            "subject": str(c["subject"]),
                            "grade": int(c["grade"]),
                            "conceptText": str(c["concept_text"]),
                            "createdAt": int(c["created_at"]),
                            "status": str(c["status"]),
                        }
                        for c in concepts
                    ],
                    "quizAttempts": [
                        {
                            "createdAt": int(a["created_at"]),
                            "scorePercent": float(a["score_percent"]),
                            "understood": bool(int(a["understood"])),
                            "subject": str(a["subject"]),
                            "grade": int(a["grade"]),
                            "conceptText": str(a["concept_text"]),
                        }
                        for a in attempts
                    ],
                    "summary": {
                        "attempts": len(attempts),
                        "understoodCount": understood_count,
                        "subjectSummaries": subject_summaries,
                    },
                }
            finally:
                conn.close()

    def add_group_message(self, group_id: str, student_id: str, body: str) -> dict[str, Any]:
        gid = str(group_id or "").strip()
        sid = str(student_id or "").strip()
        msg = str(body or "").strip()
        if not gid or not sid or not msg:
            raise ValueError("group_id/student_id/body is empty")
        mid = str(uuid4())
        now = _now()
        with self._lock:
            conn = _connect(self._path)
            try:
                # Ensure membership
                m = conn.execute(
                    "SELECT 1 FROM group_members WHERE group_id = ? AND student_id = ?",
                    (gid, sid),
                ).fetchone()
                if not m:
                    raise ValueError("Not a member of this group")
                conn.execute(
                    "INSERT INTO group_messages(id, group_id, student_id, body, created_at) VALUES (?, ?, ?, ?, ?)",
                    (mid, gid, sid, msg, int(now)),
                )
                conn.commit()
            finally:
                conn.close()
        return {"id": mid, "groupId": gid, "studentId": sid, "body": msg, "createdAt": now}

    def list_group_messages(self, group_id: str, limit: int = 50) -> list[dict[str, Any]]:
        gid = str(group_id or "").strip()
        limit = max(1, min(int(limit), 200))
        with self._lock:
            conn = _connect(self._path)
            try:
                rows = conn.execute(
                    """
                    SELECT id, group_id, student_id, body, created_at
                    FROM group_messages
                    WHERE group_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (gid, int(limit)),
                ).fetchall()
                msgs = [
                    {
                        "id": str(r["id"]),
                        "groupId": str(r["group_id"]),
                        "studentId": str(r["student_id"]),
                        "body": str(r["body"]),
                        "createdAt": int(r["created_at"]),
                    }
                    for r in rows
                ]
                return list(reversed(msgs))
            finally:
                conn.close()

