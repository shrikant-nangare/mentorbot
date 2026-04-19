## Regional judge Q&A bank (20 questions)

Use this format in answers:
- **20–30s answer**: 2–4 sentences.
- **Technical follow-up (optional)**: 1–2 sentences with specifics.

---

### 1) What problem are you solving?
**Answer:** Students often get answers without understanding, and parents can’t easily see what was learned. MentorBot turns learning into a measurable loop: explain, quiz, and mastery. It also keeps identities masked to protect students.
**Technical follow-up:** Progress is stored as concepts + quiz attempts in a persistent SQLite app DB.

### 2) How is this different from “just ChatGPT”?
**Answer:** MentorBot is mastery-first, not chat-first. It automatically triggers quizzes after explanations and requires 70% to complete a concept. It also has parent reporting and roster import, which general chat tools don’t provide.
**Technical follow-up:** Quiz gating is tracked per concept with pass/skip state and a daily skip limit.

### 3) How do you ensure students learn and don’t just copy answers?
**Answer:** MentorBot teaches step-by-step and asks guiding questions instead of giving instant final answers for exercises. Mastery is checked with short quizzes, and students must pass to mark a concept complete. This encourages understanding and practice.
**Technical follow-up:** The tutor prompt explicitly avoids giving the final computed result until the student works through steps.

### 4) What grade levels do you support and how do responses change?
**Answer:** Grades 1–12. Younger grades get simpler words, shorter sentences, and one idea at a time, while higher grades get more precise vocabulary and deeper reasoning. The same concept can be explained differently depending on grade.
**Technical follow-up:** Grade calibration text is injected into the tutor and quiz prompts.

### 5) Which subjects do you support?
**Answer:** Maths, English, science, social studies, and spellings. The system is intentionally limited to these school subjects to stay safe and age-appropriate.
**Technical follow-up:** A scope guard in the prompt refuses requests outside these subjects.

### 6) How do you handle unsafe or off-topic requests?
**Answer:** If a student asks something outside allowed school subjects, MentorBot refuses and redirects them back to a school topic. This keeps the experience appropriate for kids.
**Technical follow-up:** The prompt includes explicit refusal behavior and “do not mention system prompts” guidance.

### 7) How do you protect student privacy?
**Answer:** Student names are masked with pseudonyms, and access is controlled with PINs. Student data is private; comparisons are aggregate-only. Parents have a protected parent view.
**Technical follow-up:** PINs are stored as salted hashes; sessions are token-based with TTL.

### 8) How does parent access work?
**Answer:** Parents use a Parent PIN to access the parent view and run actions like roster import, reports, and PIN resets. This separates parent permissions from student access.
**Technical follow-up:** Parent sessions are stored separately from student sessions in the app DB.

### 9) How do you onboard a class?
**Answer:** A parent/admin can import a roster CSV to create student profiles quickly. Students set their own PIN on first login, so there’s no need to share passwords centrally.
**Technical follow-up:** CSV import validates grade range and assigns avatars/wallpapers.

### 10) What happens if the AI is wrong?
**Answer:** MentorBot is designed to explain concepts and guide steps rather than blindly output final answers. Quizzes provide a second check, and the system can use retrieval grounding when available. We also keep logs for reviewing issues.
**Technical follow-up:** Retrieval uses a vector store (Chroma) and can be disabled if not reliable.

### 11) How do you measure impact or learning outcomes?
**Answer:** We can measure mastery rates (concepts completed), quiz pass trends over time, and which topics students struggle with. Parent reports summarize learning and provide next-topic suggestions. For nationals, we plan to collect before/after quiz performance and completion time.
**Technical follow-up:** Quiz attempts include score percent, difficulty, and timestamps for time-series analysis.

### 12) How do you prevent students from skipping everything?
**Answer:** Skipping is limited per day, and skipped concepts remain pending. A student can continue, but the system keeps a record of what still needs mastery. This balances motivation with accountability.
**Technical follow-up:** Skip counts are tracked and enforced server-side.

### 13) How does adaptive difficulty work?
**Answer:** MentorBot increases quiz difficulty when recent scores are high, and reduces it when students struggle. This keeps strong students challenged and supports students who need more practice.
**Technical follow-up:** Difficulty is chosen using recent average performance and passed to quiz generation.

### 14) Is the system fair across students?
**Answer:** Each student has their own private progress and notes. Comparison stats are anonymous and aggregate-only, so students aren’t exposed. The goal is healthy motivation, not ranking by identity.
**Technical follow-up:** Cohort stats compute averages and percentiles without revealing other students.

### 15) How do groups work and how do you keep them safe?
**Answer:** Groups are invite-code rooms for discussing and solving problems together. Messages are scoped to school subjects through the tutor behavior and the classroom context. For a competition demo, we keep it simple and moderated by the structure of the app.
**Technical follow-up:** Group chat uses WebSockets with membership checks and persistent message storage.

### 16) Where is data stored and is it centralized?
**Answer:** The app uses a single instance with persistent storage on a PVC. Student data and progress are stored in a centralized SQLite app database. Caching can be centralized too for performance, but student-specific data stays private.
**Technical follow-up:** App DB and cache are separate SQLite files, and can be moved to managed services later.

### 17) How is it deployed and operated?
**Answer:** MentorBot runs as a Docker container on Kubernetes. It’s designed to work as a single instance today, which is practical for a school pilot, and can evolve to more scalable infrastructure later.
**Technical follow-up:** Health checks and probes are included; configuration is via ConfigMaps/Secrets.

### 18) What are the main risks and how do you mitigate them?
**Answer:** The main risks are incorrect responses, unsafe content, and privacy. We mitigate with subject scoping, mastery quizzes, secure authentication, and logging for review. Operationally, we keep deployment simple and reliable.
**Technical follow-up:** The parent portal can be protected at ingress, reducing repeated prompts and limiting exposure.

### 19) What’s your next step if you reach Nationals?
**Answer:** Run a pilot with more students, measure mastery improvements, and iterate on the curriculum flow. Improve reporting, add more analytics, and refine the UX based on real classroom feedback.
**Technical follow-up:** Add dashboards for concept completion, quiz outcomes, and common misconceptions.

### 20) What would you change if you had more time?
**Answer:** Add teacher workflows, deeper accessibility features, and more offline resilience. Expand question types beyond multiple choice, and add more evidence-based learning interventions. Improve personalization while keeping privacy strong.
**Technical follow-up:** Move from SQLite to a managed DB for multi-instance scaling and add role-based access controls.

