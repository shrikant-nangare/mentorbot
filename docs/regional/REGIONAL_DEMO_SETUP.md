## Regional demo setup (do this before the interview)

Goal: a demo that works in < 2 minutes with no typing stress.

### 1) Pick the environment
Choose ONE and rehearse only that:
- **Option A (recommended)**: Use the **live cluster URL** (most realistic for judges).
- **Option B**: Local `uvicorn` (only if the network/LLM keys are reliable).

### 2) Pre-stage accounts (students)
Create at least 3 student profiles so you can quickly show grade differences:
- **Demo_G2** (Grade 2): shows simpler language
- **Demo_G6** (Grade 6): main demo student
- **Demo_G10** (Grade 10): shows more advanced terminology

Checklist for each student:
- PIN set and known by the team (do not share it on screen).
- Avatar and wallpaper set (to show customization).

### 3) Pre-stage notes (so scrolling is guaranteed)
For the main demo student (Demo_G6), create **at least 25 notes** (quick method):
- Open Notes → paste short note bodies → Save repeatedly.
- Make titles vary: “Fractions 01…”, “Fractions 02…”, etc.

Then confirm:
- You can **scroll** “Recent notes”.
- You can **select** an old note to load it.
- You can **delete** a note (with confirmation).

### 4) Pre-stage a “fast quiz pass”
Pick one concept explanation prompt that reliably triggers a quiz and is easy to answer:
- Suggested prompt (Grade 6): “Explain how to add unlike fractions.”

Before the interview, do 1 practice run and note:
- Which option is correct for each quiz question (or just rehearse the flow and intentionally fail once).

### 5) Parent view setup
You need:
- Parent PIN (known by team, not shown aloud).
- A roster CSV file ready on disk.

Use the included sample file:
- `docs/regional/demo_roster.csv`

### 6) Screen-share layout (reduce risk)
Have these ready as separate browser tabs:
- Tab 1: Student UI (profile picker visible)
- Tab 2: Parent view modal (or the app page with parent button)
- Tab 3: OpenAPI docs (`/docs`) as a technical backup (optional)

### 7) “Plan B” if anything fails (say this)
If the LLM call fails or a page is slow:
- “If the model is unavailable, the app still keeps student accounts, quiz history, and notes. The system is provider-agnostic, so we can swap LLM providers. We’ll continue with the product flow and reports.”

### 8) Zero-secrets rule
- Do not paste API keys on screen.
- Do not show terminal output with secrets.
- If a login is needed, the student should type it quietly.

