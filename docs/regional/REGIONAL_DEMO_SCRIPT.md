## Regional 5-minute presentation script (students only)

Roles:
- **Student_A**: main narrator + student demo
- **Student_B**: parent portal + wrap-up

Props (open before the interview):
- Slides: `docs/regional/REGIONAL_PITCH_DECK.md` converted to slides (or screen-share the markdown).
- Browser Tab 1: MentorBot student UI (logged out to show profile picker).
- Browser Tab 2: Parent view ready (on same host, parent button available).
- Prepared roster CSV file ready to upload (see `docs/regional/REGIONAL_DEMO_SETUP.md`).

Timing target: 5:00 total. If anything breaks, skip to “Fallback line”.

---

### Slide 1 — Title + hook (0:00–0:25)
**Student_A (say this):**  
“Hi judges, we’re presenting MentorBot. It’s a mastery-first AI tutor that helps students learn step-by-step and helps parents see progress.”

“The problem is: students can get quick answers, but not always understanding. MentorBot is designed to turn learning into a measurable loop: explain, quiz, and master.”

**Action:** advance slide.

---

### Slide 2 — Who it’s for + what it does (0:25–1:00)
**Student_A:**  
“MentorBot is for students in grades 1 to 12 and for parents.”

“Students use masked profiles with avatars, so their real names are not shown. They ask questions in school subjects: maths, English, science, social studies, and spellings.”

“Parents can import a class roster and see reports that summarize what the student learned.”

**Action:** advance slide.

---

### Slide 3 — The learning loop: explain → quiz → mastery (1:00–1:40)
**Student_A:**  
“Our core feature is mastery gating. When MentorBot explains a concept, it triggers a short quiz.”

“To complete a concept, students need at least 70%. They can skip quizzes a limited number of times per day, but skipped concepts stay pending.”

“If a student performs well, MentorBot increases difficulty.”

**Action:** “Now we’ll show it live.” Switch to Tab 1 (student UI).

---

### Slide 4 — Live demo: student flow + notes (1:40–2:40)
**Student_A (do + say):**
1) **Pick a profile**
   - Click a student profile (masked name + avatar).
   - “This is a masked student profile with a PIN login.”

2) **Ask a real question** (copy/paste to avoid typos)
   - Paste into chat:
     - Grade 6 example: “Explain how to add unlike fractions.”
   - Click **Send**.
   - “MentorBot teaches step-by-step, grade-appropriate.”

3) **Show quiz auto-trigger + mastery**
   - When quiz appears: “After an explanation, it requires a quiz.”
   - Answer quickly using pre-known correct answers (prepared in advance) OR intentionally get 3/5 to show “not yet”.
   - Click **Submit**.
   - Say one sentence depending on result:
     - If pass: “We passed 70%, so the concept is marked understood.”
     - If fail: “If you don’t reach 70%, it encourages review and retry.”

4) **Show notes** (save + scroll + delete)
   - Click **Notes**.
   - “Students can save notes for later.”
   - In the editor:
     - Title: “Unlike fractions”
     - Body: “To add unlike fractions: find LCD, convert, add numerators, simplify.”
   - Click **Save note**.
   - In “Recent notes” list:
     - Scroll briefly to show many notes exist.
     - Click an older note to load it.
     - Click **Delete** → confirm.
   - Close Notes.

**Fallback line (if LLM/network fails):**  
“If the model is unavailable, MentorBot still keeps student data and quiz history, and we can swap LLM providers. We’ll move to the parent tools.”

**Action:** switch back to slides (or keep demo and jump to parent flow).

---

### Slide 5 — What makes it different (2:40–3:30)
**Student_A:**  
“What makes MentorBot different is that it’s not just chat. It’s a mastery workflow with quizzes and completion tracking.”

“It’s also grade-calibrated: younger students get simpler explanations and older students get more advanced explanations.”

**Action:** advance slide.

---

### Slide 6 — Responsible AI + privacy (3:30–4:20)
**Student_B:**  
“MentorBot is restricted to school subjects only. If you ask off-topic questions, it refuses and redirects to allowed subjects.”

“Students are masked, and PINs are hashed. Parent actions require a Parent PIN, and the parent portal can be protected with login at the ingress.”

**Action:** “Now we’ll show the parent view.” Switch to Parent view tab OR click Parent in UI.

---

### Parent flow (quick) (4:20–4:45)
**Student_B (do + say):**
1) Open **Parent view**.
2) “Parents can import a roster CSV.”  
   - Choose the prepared CSV file → click **Upload**.
3) “Parents can generate reports.”  
   - Select a student → select 7 days → click **Generate**.

**Action:** return to slide 8.

---

### Slide 8 — Close (4:45–5:00)
**Student_B:**  
“MentorBot makes learning measurable and safe, while giving parents visibility.”

“Thank you—now we’re ready for questions.”

---

## 10-minute Q&A posture (student behavior)
- Answer in **20–30 seconds**.\n+- If asked for technical depth: give a 1-sentence answer, then offer a deeper follow-up.\n+- Keep the supervising adult silent.\n+

