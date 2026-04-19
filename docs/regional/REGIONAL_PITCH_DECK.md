## Regional interview pitch deck (5 minutes)

Audience: judges in a 15-minute Zoom interview (5-minute presentation + 10-minute Q&A).  
Division: middle school (students speak; supervising adult present + silent).

### Slide 1 — Title + hook (0:00–0:25)
- **Title**: MentorBot — Mastery-first AI tutor for school subjects
- **One-liner**: A kid-friendly tutor that teaches step-by-step, checks mastery with short quizzes, and helps parents see progress.
- **Problem**:
  - Students get “answers” but not understanding.
  - Parents can’t easily see what was learned.
- **Goal**: Make learning measurable, safe, and motivating.

### Slide 2 — Who it’s for + what it does (0:25–1:00)
- **Students (Grades 1–12)**:
  - Ask questions in school subjects (maths, english, science, social studies, spellings).
  - Get explanations and guided practice.
- **Parents**:
  - Import roster, reset PINs, and view learning reports.
- **Privacy**:
  - Masked student names + PIN login.

### Slide 3 — The learning loop: explain → quiz → mastery (1:00–1:40)
- **Concept explanations trigger a quiz** automatically (or “Quiz now”).
- **Mastery rule**: concept is complete only at **70%+**.
- **Soft gate**: students may skip quizzes up to a daily limit; skipped concepts remain pending.
- **Adaptive difficulty**: if a student performs well, quiz difficulty increases.

### Slide 4 — Live demo (1:40–2:40)
Demo flow (fast, scripted):
- Pick a masked profile with avatar.
- Ask a real grade-level question.
- Show quiz gating + mastery.
- Show notes: save, list/scroll, delete.
- Show suggestions only after a real question (not “hi”).
- Optional: group room invite-code chat (quick flash).

### Slide 5 — What makes MentorBot different (2:40–3:30)
- **Mastery-first, not chat-first**: learning is measurable (quizzes + completion status).
- **Grade-calibrated answers**: younger grades get simpler language; higher grades get more advanced depth.
- **Parent visibility**: reports summarize learning + recommendations.
- **Real classroom constraints**: roster import, PIN reset, single-instance deployment.

### Slide 6 — Responsible AI + safety + privacy (3:30–4:20)
- **Subject scope guard**: refuses off-topic/non-school requests.
- **Privacy by design**:
  - Masked identities; hashed PINs; sessions.
  - Parent view protected by Parent PIN (and ingress Basic Auth if enabled).
- **Transparency**: daily chat logs available for reference/audit (optional feature).

### Slide 7 — Implementation + reliability (4:20–4:45)
- **Tech**: FastAPI + SQLite (on PVC) + optional retrieval (Chroma) + LLM provider.
- **Deployment**: Docker + Kubernetes (single instance; designed to evolve).
- **Why this matters**: predictable ops, low cost, easy to run.

### Slide 8 — Close + ask (4:45–5:00)
- **Impact**: students learn step-by-step; parents see progress; schools can onboard from a roster.
- **Next**:
  - Add metrics dashboard (mastery rate, concept completion trends).
  - Expand reporting + classroom workflows.
- **Ask**: We’d love to advance to Nationals to test MentorBot with more students and quantify learning outcomes.

## Speaker notes (single slide footer)
- Keep each slide to **1 short sentence** + 2–4 bullets.
- Don’t type long prompts live—use copy/paste from the demo script.
- If anything fails: switch to the backup demo clip.

