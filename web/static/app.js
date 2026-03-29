(() => {
  'use strict';

  const authScreen = document.getElementById('authScreen');
  const profilesGrid = document.getElementById('profilesGrid');
  const authStatus = document.getElementById('authStatus');
  const parentBtn = document.getElementById('parentBtn');
  const parentModal = document.getElementById('parentModal');
  const parentCloseBtn = document.getElementById('parentCloseBtn');
  const parentPinInput = document.getElementById('parentPinInput');
  const parentLoginBtn = document.getElementById('parentLoginBtn');
  const parentSetPinBtn = document.getElementById('parentSetPinBtn');
  const parentAuthStatus = document.getElementById('parentAuthStatus');
  const rosterFile = document.getElementById('rosterFile');
  const rosterUploadBtn = document.getElementById('rosterUploadBtn');
  const rosterStatus = document.getElementById('rosterStatus');
  const reportStudentSelect = document.getElementById('reportStudentSelect');
  const reportDaysSelect = document.getElementById('reportDaysSelect');
  const reportRunBtn = document.getElementById('reportRunBtn');
  const reportOut = document.getElementById('reportOut');
  const pinStudentSelect = document.getElementById('pinStudentSelect');
  const pinNewValue = document.getElementById('pinNewValue');
  const pinResetBtn = document.getElementById('pinResetBtn');
  const pinClearBtn = document.getElementById('pinClearBtn');
  const pinResetStatus = document.getElementById('pinResetStatus');

  const chat = document.getElementById('chat');
  const input = document.getElementById('input');
  const sendBtn = document.getElementById('sendBtn');
  const statusEl = document.getElementById('status');
  const mathStatusEl = document.getElementById('mathStatus');
  const history = [];

  const quizBtn = document.getElementById('quizBtn');
  const quizPanel = document.getElementById('quizPanel');
  const quizTitle = document.getElementById('quizTitle');
  const quizBody = document.getElementById('quizBody');
  const quizStatus = document.getElementById('quizStatus');
  const quizSubmitBtn = document.getElementById('quizSubmitBtn');
  const quizSkipBtn = document.getElementById('quizSkipBtn');
  const quizCloseBtn = document.getElementById('quizCloseBtn');
  const quizRetryBtn = document.getElementById('quizRetryBtn');
  const quizResult = document.getElementById('quizResult');

  const gradeSelect = document.getElementById('gradeSelect');
  const notesBtn = document.getElementById('notesBtn');
  const notesModal = document.getElementById('notesModal');
  const notesCloseBtn = document.getElementById('notesCloseBtn');
  const noteTitle = document.getElementById('noteTitle');
  const noteBody = document.getElementById('noteBody');
  const noteSaveBtn = document.getElementById('noteSaveBtn');
  const noteRefreshBtn = document.getElementById('noteRefreshBtn');
  const notesStatus = document.getElementById('notesStatus');
  const notesList = document.getElementById('notesList');

  const groupsBtn = document.getElementById('groupsBtn');
  const groupsModal = document.getElementById('groupsModal');
  const groupsCloseBtn = document.getElementById('groupsCloseBtn');
  const groupInviteInput = document.getElementById('groupInviteInput');
  const groupJoinBtn = document.getElementById('groupJoinBtn');
  const groupNameInput = document.getElementById('groupNameInput');
  const groupCreateBtn = document.getElementById('groupCreateBtn');
  const groupsStatus = document.getElementById('groupsStatus');
  const groupsList = document.getElementById('groupsList');
  const groupChat = document.getElementById('groupChat');
  const groupChatInput = document.getElementById('groupChatInput');
  const groupSendBtn = document.getElementById('groupSendBtn');

  let currentQuiz = null; // { quizId, title, questions: [{id, question, options}] }
  let sessionToken = localStorage.getItem('mb_session_token') || '';
  let currentProfile = null;
  let parentToken = localStorage.getItem('mb_parent_token') || '';
  let gateActive = false;
  let gateConceptId = '';
  let gateSubject = 'maths';
  let gateGrade = 1;

  function setActiveSubjectImplicit(subj) {
    const s = String(subj || 'maths').toLowerCase();
    gateSubject = s;
  }

  function setGrade(g) {
    const n = Math.max(1, Math.min(12, parseInt(g, 10) || 1));
    gateGrade = n;
    if (gradeSelect) gradeSelect.value = String(n);
  }

  async function persistProfilePrefs() {
    if (!sessionToken) return;
    try {
      await fetch('/me', {
        method: 'PATCH',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ grade: gateGrade })
      });
    } catch (_) {}
  }

  const AVATAR_STYLES = {
    avatar_01: { a: '#7dd3fc', b: '#34d399' },
    avatar_02: { a: '#fb7185', b: '#60a5fa' },
    avatar_03: { a: '#fbbf24', b: '#34d399' },
    avatar_04: { a: '#a78bfa', b: '#22c55e' },
    avatar_05: { a: '#60a5fa', b: '#f97316' },
    avatar_06: { a: '#34d399', b: '#f472b6' },
    avatar_07: { a: '#22c55e', b: '#38bdf8' },
    avatar_08: { a: '#e879f9', b: '#fbbf24' },
    avatar_09: { a: '#fb7185', b: '#a78bfa' },
    avatar_10: { a: '#38bdf8', b: '#fbbf24' },
    avatar_11: { a: '#34d399', b: '#60a5fa' },
    avatar_12: { a: '#f97316', b: '#fb7185' }
  };

  function setWallpaper(key) {
    if (!key) return;
    document.body.dataset.wallpaper = String(key);
  }

  function authHeaders(extra) {
    const h = Object.assign({}, extra || {});
    if (sessionToken) h.Authorization = `Bearer ${sessionToken}`;
    return h;
  }

  function parentHeaders(extra) {
    const h = Object.assign({}, extra || {});
    if (parentToken) h.Authorization = `Bearer ${parentToken}`;
    return h;
  }

  function showAuth(show) {
    if (!authScreen) return;
    authScreen.style.display = show ? 'flex' : 'none';
  }

  function showParentModal(show) {
    if (!parentModal) return;
    parentModal.style.display = show ? 'flex' : 'none';
  }

  function showNotesModal(show) {
    if (!notesModal) return;
    notesModal.style.display = show ? 'flex' : 'none';
  }

  function showGroupsModal(show) {
    if (!groupsModal) return;
    groupsModal.style.display = show ? 'flex' : 'none';
  }

  function avatarSvg(avatarKey, label) {
    const key = String(avatarKey || 'avatar_01');
    const st = AVATAR_STYLES[key] || AVATAR_STYLES.avatar_01;
    const letter = String(label || '?').trim().slice(0, 1).toUpperCase() || '?';
    const svg =
      `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64" role="img" aria-label="Avatar">` +
      `<defs>` +
      `<radialGradient id="g" cx="30%" cy="25%" r="80%">` +
      `<stop offset="0%" stop-color="${st.a}" stop-opacity="1"/>` +
      `<stop offset="60%" stop-color="${st.b}" stop-opacity="0.95"/>` +
      `<stop offset="100%" stop-color="#0b1020" stop-opacity="1"/>` +
      `</radialGradient>` +
      `</defs>` +
      `<rect x="1" y="1" width="62" height="62" rx="18" fill="url(#g)"/>` +
      `<rect x="4" y="4" width="56" height="56" rx="16" fill="none" stroke="rgba(255,255,255,0.18)"/>` +
      `<text x="32" y="40" text-anchor="middle" font-size="22" font-weight="800" fill="rgba(255,255,255,0.92)" font-family="ui-sans-serif, system-ui">${letter}</text>` +
      `</svg>`;
    return svg;
  }

  function renderProfiles(students) {
    if (!profilesGrid) return;
    profilesGrid.innerHTML = '';
    (students || []).forEach((s) => {
      const card = document.createElement('div');
      card.className = 'profileCard';
      const av = document.createElement('div');
      av.className = 'avatar';
      av.innerHTML = avatarSvg(s.avatarKey, s.pseudonym);
      const name = document.createElement('p');
      name.className = 'profileName';
      name.textContent = s.pseudonym || 'Student';
      const meta = document.createElement('p');
      meta.className = 'profileMeta';
      meta.textContent = `Grade ${s.grade || 1} · ${s.pinSet ? 'PIN set' : 'Set PIN'}`;
      card.appendChild(av);
      card.appendChild(name);
      card.appendChild(meta);
      card.addEventListener('click', async () => {
        await loginFlow(s);
      });
      profilesGrid.appendChild(card);
    });
  }

  async function loadProfiles() {
    if (authStatus) authStatus.textContent = 'Loading profiles…';
    const resp = await fetch('/profiles', { method: 'GET' });
    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    const students = (data && data.students) ? data.students : [];
    renderProfiles(students);
    if (authStatus) {
      authStatus.textContent = students.length ? '' : 'No students yet. Use Parent view to import a roster.';
    }
  }

  async function tryResumeSession() {
    if (!sessionToken) return false;
    try {
      const resp = await fetch('/me', { method: 'GET', headers: authHeaders() });
      if (!resp.ok) throw new Error('not ok');
      const data = await resp.json();
      currentProfile = data && data.profile ? data.profile : null;
      if (currentProfile) {
        setWallpaper(currentProfile.wallpaperKey || 'space_01');
        setGrade(currentProfile.grade || 1);
        return true;
      }
    } catch (_) {
      sessionToken = '';
      localStorage.removeItem('mb_session_token');
    }
    return false;
  }

  async function loginFlow(student) {
    const sid = student && student.id ? student.id : '';
    if (!sid) return;

    if (authStatus) authStatus.textContent = '';

    if (!student.pinSet) {
      const newPin = window.prompt(`Set a PIN for ${student.pseudonym} (4-12 digits).`);
      if (!newPin) return;
      if (authStatus) authStatus.textContent = 'Setting PIN…';
      const resp = await fetch('/auth/student/set-pin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ studentId: sid, newPin })
      });
      if (!resp.ok) {
        if (authStatus) authStatus.textContent = await resp.text();
        return;
      }
      const data = await resp.json();
      sessionToken = data.sessionToken || '';
      localStorage.setItem('mb_session_token', sessionToken);
      currentProfile = data.profile || null;
      setWallpaper((currentProfile && currentProfile.wallpaperKey) ? currentProfile.wallpaperKey : 'space_01');
      setGrade((currentProfile && currentProfile.grade) ? currentProfile.grade : (student.grade || 1));
      showAuth(false);
      addMessage('system', 'Welcome', `Hi ${currentProfile && currentProfile.pseudonym ? currentProfile.pseudonym : 'student'}!`);
      return;
    }

    const pin = window.prompt(`Enter PIN for ${student.pseudonym}`);
    if (!pin) return;
    if (authStatus) authStatus.textContent = 'Logging in…';
    const resp = await fetch('/auth/student/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ studentId: sid, pin })
    });
    if (!resp.ok) {
      if (authStatus) authStatus.textContent = await resp.text();
      return;
    }
    const data = await resp.json();
    sessionToken = data.sessionToken || '';
    localStorage.setItem('mb_session_token', sessionToken);
    currentProfile = data.profile || null;
    setWallpaper((currentProfile && currentProfile.wallpaperKey) ? currentProfile.wallpaperKey : 'space_01');
    setGrade((currentProfile && currentProfile.grade) ? currentProfile.grade : (student.grade || 1));
    showAuth(false);
    addMessage('system', 'Welcome', `Hi ${currentProfile && currentProfile.pseudonym ? currentProfile.pseudonym : 'student'}!`);
  }

  function updateMathStatus(status) {
    if (!mathStatusEl) return;
    if (status === 'rendered') {
      mathStatusEl.textContent = 'Math: rendered';
      mathStatusEl.style.color = 'rgba(167, 243, 208, 0.9)';
    } else if (status === 'not_loaded') {
      mathStatusEl.textContent = 'Math: not loaded';
      mathStatusEl.style.color = 'rgba(251, 113, 133, 0.9)';
    } else if (status === 'error') {
      mathStatusEl.textContent = 'Math: error';
      mathStatusEl.style.color = 'rgba(251, 113, 133, 0.9)';
    } else {
      mathStatusEl.textContent = '';
    }
  }

  function renderMath(node) {
    try {
      if (typeof katex === 'undefined') {
        updateMathStatus('not_loaded');
        return;
      }

      const tokens = node.__mbMathTokens || [];
      if (!tokens.length) {
        updateMathStatus('rendered');
        return;
      }

      for (const tok of tokens) {
        const ph = tok.placeholder;
        const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) {
          const t = walker.currentNode;
          const v = t.nodeValue || '';
          const idx = v.indexOf(ph);
          if (idx === -1) continue;

          const before = v.slice(0, idx);
          const after = v.slice(idx + ph.length);
          const parent = t.parentNode;
          if (!parent) break;

          if (before) parent.insertBefore(document.createTextNode(before), t);

          const wrap = document.createElement(tok.display ? 'div' : 'span');
          wrap.className = tok.display ? 'mathBlock' : 'mathInline';
          wrap.innerHTML = katex.renderToString(tok.tex, {
            displayMode: !!tok.display,
            throwOnError: false
          });
          parent.insertBefore(wrap, t);

          if (after) parent.insertBefore(document.createTextNode(after), t);
          parent.removeChild(t);
          break;
        }
      }

      node.__mbMathTokens = [];
      updateMathStatus('rendered');
    } catch (_) {
      updateMathStatus('error');
    }
  }

  function setFormattedText(el, text) {
    const raw = String(text || '').replace(/\r\n/g, '\n');

    // Fix common LLM formatting: "1." on one line, title on next line.
    let normalized = raw.replace(/^(\s*\d+)\.\s*\n\s*(\S)/gm, '$1. $2');

    // Extract TeX blocks BEFORE Markdown parsing so backslashes aren't eaten.
    // We'll replace placeholders with rendered KaTeX after Markdown -> HTML.
    const tokens = [];
    let counter = 0;
    const collapseWs = (s) => String(s || '').replace(/\s+/g, ' ').trim();

    normalized = normalized.replace(/\\\[\s*([\s\S]*?)\s*\\\]/g, (_, body) => {
      const placeholder = `@@MBMATHB${counter++}@@`;
      tokens.push({ placeholder, tex: collapseWs(body), display: true });
      return `\n\n${placeholder}\n\n`;
    });

    normalized = normalized.replace(/\\\(\s*([\s\S]*?)\s*\\\)/g, (_, body) => {
      const placeholder = `@@MBMATHI${counter++}@@`;
      tokens.push({ placeholder, tex: collapseWs(body), display: false });
      return placeholder;
    });

    if (typeof marked === 'undefined' || typeof DOMPurify === 'undefined') {
      el.textContent = normalized;
      return;
    }

    marked.setOptions({ breaks: true, gfm: true });
    const html = marked.parse(normalized);
    el.innerHTML = DOMPurify.sanitize(html);
    el.__mbMathTokens = tokens;
  }

  function addMessage(role, who, text) {
    const row = document.createElement('div');
    row.className = `row ${role}`;

    const left = document.createElement('div');
    left.className = 'who';
    left.innerHTML = `<strong>${who}</strong>`;

    const right = document.createElement('div');
    right.className = 'msg';
    setFormattedText(right, text);

    row.appendChild(left);
    row.appendChild(right);
    chat.appendChild(row);
    chat.scrollTop = chat.scrollHeight;

    renderMath(right);
  }

  function addTopicChips(topics) {
    const list = Array.isArray(topics) ? topics : [];
    if (!list.length) return;

    const row = document.createElement('div');
    row.className = 'row system';

    const left = document.createElement('div');
    left.className = 'who';
    left.innerHTML = '<strong>Next up</strong>';

    const right = document.createElement('div');
    right.className = 'msg';

    const wrap = document.createElement('div');
    wrap.style.display = 'flex';
    wrap.style.flexWrap = 'wrap';
    wrap.style.gap = '8px';
    list.slice(0, 6).forEach((t) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'btnSmall';
      b.textContent = String(t);
      b.style.height = '32px';
      b.style.minWidth = 'auto';
      b.addEventListener('click', () => {
        input.value = String(t);
        input.focus();
      });
      wrap.appendChild(b);
    });
    right.appendChild(wrap);

    row.appendChild(left);
    row.appendChild(right);
    chat.appendChild(row);
    chat.scrollTop = chat.scrollHeight;
  }

  function pushHistory(role, content) {
    if (role !== 'user' && role !== 'assistant') return;
    history.push({ role, content: String(content || '') });
    if (history.length > 24) history.splice(0, history.length - 24);
  }

  function setBusy(busy) {
    chat.setAttribute('aria-busy', busy ? 'true' : 'false');
    sendBtn.disabled = busy;
  }

  function setGate(active, info) {
    gateActive = !!active;
    if (active && info) {
      gateConceptId = info.conceptId || gateConceptId;
      gateSubject = info.subject || gateSubject;
      gateGrade = info.grade || gateGrade;
    }
    const disabled = gateActive;
    sendBtn.disabled = disabled;
    input.disabled = disabled;
    if (disabled) {
      statusEl.textContent = 'Quiz required to continue (pass or skip).';
      statusEl.className = '';
    } else {
      if (statusEl.textContent === 'Quiz required to continue (pass or skip).') statusEl.textContent = '';
    }
  }

  function getLastAssistantMessage() {
    for (let i = history.length - 1; i >= 0; i--) {
      if (history[i].role === 'assistant' && history[i].content && history[i].content.trim()) {
        return history[i].content.trim();
      }
    }
    return '';
  }

  function showQuizPanel(show) {
    quizPanel.style.display = show ? 'block' : 'none';
  }

  function renderQuiz(quiz) {
    currentQuiz = quiz;
    quizTitle.textContent = quiz.title || 'Quick check';
    quizBody.innerHTML = '';
    quizResult.style.display = 'none';
    quizRetryBtn.style.display = 'none';
    quizStatus.textContent = '';

    (quiz.questions || []).forEach((q, idx) => {
      const fs = document.createElement('fieldset');
      const legend = document.createElement('legend');
      legend.textContent = `${idx + 1}. ${q.question}`;
      fs.appendChild(legend);

      ['A','B','C','D'].forEach((key) => {
        const label = document.createElement('label');
        label.className = 'opt';
        const inputEl = document.createElement('input');
        inputEl.type = 'radio';
        inputEl.name = `quiz_${q.id}`;
        inputEl.value = key;
        const span = document.createElement('div');
        span.textContent = `${key}) ${q.options[key]}`;
        label.appendChild(inputEl);
        label.appendChild(span);
        fs.appendChild(label);
      });

      quizBody.appendChild(fs);
    });

    showQuizPanel(true);
  }

  async function generateQuiz() {
    quizBtn.disabled = true;
    quizStatus.textContent = 'Generating…';
    quizStatus.className = '';
    try {
      const concept = getLastAssistantMessage();
      const resp = await fetch('/quiz/generate', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ concept, history, conceptId: gateConceptId || null, subject: gateSubject, grade: gateGrade })
      });
      if (!resp.ok) {
        const txt = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${txt}`);
      }
      const quiz = await resp.json();
      renderQuiz(quiz);
    } catch (err) {
      quizStatus.textContent = 'Failed to generate quiz';
      quizStatus.className = 'error';
      addMessage('system', 'Error', String(err && err.message ? err.message : err));
    } finally {
      quizBtn.disabled = false;
      if (quizStatus.textContent === 'Generating…') quizStatus.textContent = '';
    }
  }

  async function skipQuiz() {
    if (!gateConceptId) {
      quizResult.style.display = 'block';
      quizResult.className = 'quizResult error';
      quizResult.textContent = 'Nothing to skip.';
      return;
    }
    quizSkipBtn.disabled = true;
    quizStatus.textContent = 'Skipping…';
    quizStatus.className = '';
    try {
      const resp = await fetch('/quiz/skip', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ conceptId: gateConceptId, subject: gateSubject, grade: gateGrade })
      });
      if (!resp.ok) {
        const txt = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${txt}`);
      }
      const data = await resp.json();
      quizResult.style.display = 'block';
      quizResult.className = 'quizResult';
      quizResult.textContent = `Skipped. Remaining skips: ${data.remainingSkips}/${data.skipLimit} (last 24h).`;
      setGate(false);
      showQuizPanel(false);
    } catch (err) {
      quizResult.style.display = 'block';
      quizResult.className = 'quizResult error';
      quizResult.textContent = String(err && err.message ? err.message : err);
    } finally {
      quizSkipBtn.disabled = false;
      if (quizStatus.textContent === 'Skipping…') quizStatus.textContent = '';
    }
  }

  async function submitQuiz() {
    if (!currentQuiz) return;
    const answers = [];
    let missing = 0;
    (currentQuiz.questions || []).forEach((q) => {
      const selected = document.querySelector(`input[name="quiz_${q.id}"]:checked`);
      if (!selected) {
        missing += 1;
        return;
      }
      answers.push({ questionId: q.id, choice: selected.value });
    });

    if (missing > 0) {
      quizResult.style.display = 'block';
      quizResult.textContent = `Please answer all questions (${missing} missing).`;
      quizResult.className = 'quizResult error';
      return;
    }

    quizSubmitBtn.disabled = true;
    quizStatus.textContent = 'Submitting…';
    quizStatus.className = '';
    try {
      const resp = await fetch('/quiz/submit', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ quizId: currentQuiz.quizId, answers })
      });
      if (!resp.ok) {
        const txt = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${txt}`);
      }
      const result = await resp.json();

      quizResult.style.display = 'block';
      quizResult.className = 'quizResult';
      quizResult.textContent = `${result.message} (>= ${result.passPercent || 70}% means understood)`;

      addMessage('system', 'Quiz result', `${result.correctCount}/${result.total} correct (${result.scorePercent}%). Understood: ${result.understood ? 'yes' : 'no'}.`);

      if (Array.isArray(result.review)) {
        const lines = result.review.map((r, idx) => {
          const status = r.isCorrect ? '✅' : '❌';
          const user = r.userChoice || '(no answer)';
          return `${idx + 1}) ${status} You: ${user} | Correct: ${r.correct}\n${r.explanation || ''}`;
        });
        addMessage('system', 'Review', lines.join('\n\n'));
      }

      quizRetryBtn.style.display = 'inline-block';
      if (result.understood) {
        setGate(false);
        gateConceptId = '';
      } else {
        setGate(true);
      }

      // Anonymous comparison stats (private, aggregate-only).
      try {
        const resp2 = await fetch(`/stats/compare?subject=${encodeURIComponent(gateSubject)}&grade=${encodeURIComponent(String(gateGrade))}`, {
          method: 'GET',
          headers: authHeaders()
        });
        if (resp2.ok) {
          const s = await resp2.json();
          const your = (s && s.yourAvg != null) ? Number(s.yourAvg).toFixed(1) : '—';
          const avg = (s && s.cohortAvg != null) ? Number(s.cohortAvg).toFixed(1) : '—';
          const pct = (s && s.percentile != null) ? Number(s.percentile).toFixed(0) : '—';
          const n = (s && s.sampleSize != null) ? Number(s.sampleSize) : 0;
          addMessage('system', 'Comparison', `You avg: ${your}% | Others avg: ${avg}% | Percentile: ${pct} (n=${n})`);
        }
      } catch (_) {}
    } catch (err) {
      quizResult.style.display = 'block';
      quizResult.className = 'quizResult error';
      quizResult.textContent = String(err && err.message ? err.message : err);
    } finally {
      quizSubmitBtn.disabled = false;
      if (quizStatus.textContent === 'Submitting…') quizStatus.textContent = '';
    }
  }

  async function sendMessage() {
    const question = input.value.trim();
    if (!question) return;

    input.value = '';
    addMessage('user', 'You', question);
    pushHistory('user', question);
    setBusy(true);
    statusEl.textContent = 'Thinking…';
    statusEl.className = '';

    try {
      const resp = await fetch('/ask', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ question, history, grade: gateGrade })
      });

      if (!resp.ok) {
        const txt = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${txt}`);
      }

      const data = await resp.json();
      const answer = (data && data.answer) ? data.answer : '(empty response)';
      addMessage('bot', 'MentorBot', answer);
      pushHistory('assistant', answer);
      if (data && data.subject) {
        setActiveSubjectImplicit(data.subject);
      }
      if (data && Array.isArray(data.suggestedTopics) && data.suggestedTopics.length) {
        addTopicChips(data.suggestedTopics);
      }
      if (data && data.quizRequired && data.conceptId) {
        setGate(true, { conceptId: data.conceptId, subject: data.subject, grade: data.grade });
        // Auto-quiz for concept explanations
        await generateQuiz();
      }
      statusEl.textContent = '';
    } catch (err) {
      addMessage('system', 'Error', String(err && err.message ? err.message : err));
      statusEl.textContent = 'Request failed';
      statusEl.className = 'error';
    } finally {
      setBusy(false);
      input.focus();
    }
  }

  sendBtn.addEventListener('click', sendMessage);
  quizBtn.addEventListener('click', generateQuiz);
  quizSubmitBtn.addEventListener('click', submitQuiz);
  if (quizSkipBtn) quizSkipBtn.addEventListener('click', skipQuiz);
  quizCloseBtn.addEventListener('click', () => showQuizPanel(false));
  quizRetryBtn.addEventListener('click', generateQuiz);

  if (gradeSelect) {
    gradeSelect.addEventListener('change', () => {
      setGrade(gradeSelect.value);
      persistProfilePrefs();
    });
  }

  if (parentBtn) parentBtn.addEventListener('click', () => showParentModal(true));
  if (parentCloseBtn) parentCloseBtn.addEventListener('click', () => showParentModal(false));

  async function parentSetPin() {
    const pin = (parentPinInput && parentPinInput.value) ? parentPinInput.value.trim() : '';
    if (!pin) return;
    if (parentAuthStatus) parentAuthStatus.textContent = 'Setting parent PIN…';
    const resp = await fetch('/parent/pin/set', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pin })
    });
    parentAuthStatus.textContent = resp.ok ? 'Parent PIN set.' : await resp.text();
  }

  async function parentLogin() {
    const pin = (parentPinInput && parentPinInput.value) ? parentPinInput.value.trim() : '';
    if (!pin) return;
    if (parentAuthStatus) parentAuthStatus.textContent = 'Logging in…';
    const resp = await fetch('/parent/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pin })
    });
    if (!resp.ok) {
      parentAuthStatus.textContent = await resp.text();
      return;
    }
    const data = await resp.json();
    parentToken = data.sessionToken || '';
    localStorage.setItem('mb_parent_token', parentToken);
    parentAuthStatus.textContent = 'Logged in.';
    await loadParentStudents();
  }

  async function loadParentStudents() {
    if (!parentToken) return;
    const resp = await fetch('/parent/students', { method: 'GET', headers: parentHeaders() });
    if (!resp.ok) return;
    const data = await resp.json();
    const students = (data && data.students) ? data.students : [];
    const fill = (sel) => {
      if (!sel) return;
      sel.innerHTML = '';
      students.forEach((s) => {
        const opt = document.createElement('option');
        opt.value = String(s.id);
        opt.textContent = `${s.pseudonym} (Grade ${s.grade})`;
        sel.appendChild(opt);
      });
    };
    fill(reportStudentSelect);
    fill(pinStudentSelect);
  }

  async function runReport() {
    if (!parentToken) return;
    const sid = reportStudentSelect ? reportStudentSelect.value : '';
    const days = reportDaysSelect ? reportDaysSelect.value : '7';
    if (!sid) return;
    if (reportOut) {
      reportOut.style.display = 'block';
      reportOut.className = 'quizResult';
      reportOut.textContent = 'Generating…';
    }
    const resp = await fetch(`/parent/report?studentId=${encodeURIComponent(sid)}&days=${encodeURIComponent(days)}`, {
      method: 'GET',
      headers: parentHeaders()
    });
    if (!resp.ok) {
      if (reportOut) {
        reportOut.className = 'quizResult error';
        reportOut.textContent = await resp.text();
      }
      return;
    }
    const data = await resp.json();
    const s = data.student || {};
    const sum = data.summary || {};
    const subj = Array.isArray(sum.subjectSummaries) ? sum.subjectSummaries : [];
    const lines = [];
    lines.push(`Student: ${s.pseudonym || ''} (Grade ${s.grade || ''})`);
    lines.push(`Range: last ${data.rangeDays || days} day(s)`);
    lines.push(`Quiz attempts: ${sum.attempts || 0} | Understood: ${sum.understoodCount || 0}`);
    if (subj.length) {
      lines.push('');
      lines.push('By subject:');
      subj.forEach((x) => {
        const avg = (x.avgScore != null) ? Number(x.avgScore).toFixed(1) : '—';
        lines.push(`- ${x.subject}: avg ${avg}% (${x.attempts} attempts)`);
      });
    }
    if (reportOut) {
      reportOut.className = 'quizResult';
      reportOut.textContent = lines.join('\n');
    }
  }

  async function resetStudentPin(mode) {
    if (!parentToken) return;
    const sid = pinStudentSelect ? pinStudentSelect.value : '';
    if (!sid) return;
    const newPin = (mode === 'set' && pinNewValue) ? pinNewValue.value.trim() : '';
    if (pinResetStatus) pinResetStatus.textContent = 'Saving…';
    const resp = await fetch('/parent/student/pin/reset', {
      method: 'POST',
      headers: parentHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ studentId: sid, newPin: mode === 'set' ? newPin : null })
    });
    if (!resp.ok) {
      if (pinResetStatus) pinResetStatus.textContent = await resp.text();
      return;
    }
    if (pinResetStatus) pinResetStatus.textContent = mode === 'set' ? 'PIN reset.' : 'PIN cleared (student must set again).';
    if (pinNewValue) pinNewValue.value = '';
    await loadProfiles();
    await loadParentStudents();
  }

  async function rosterUpload() {
    if (!parentToken) {
      rosterStatus.textContent = 'Login in Parent view first.';
      return;
    }
    const f = rosterFile && rosterFile.files && rosterFile.files[0] ? rosterFile.files[0] : null;
    if (!f) {
      rosterStatus.textContent = 'Choose a CSV file.';
      return;
    }
    rosterStatus.textContent = 'Uploading…';
    const fd = new FormData();
    fd.append('file', f, f.name);
    const resp = await fetch('/parent/roster/import', {
      method: 'POST',
      headers: parentHeaders(),
      body: fd
    });
    if (!resp.ok) {
      rosterStatus.textContent = await resp.text();
      return;
    }
    const data = await resp.json();
    const created = data.created || 0;
    const errs = Array.isArray(data.errors) ? data.errors.length : 0;
    rosterStatus.textContent = `Imported ${created} student(s). Errors: ${errs}.`;
    await loadProfiles();
  }

  if (parentSetPinBtn) parentSetPinBtn.addEventListener('click', parentSetPin);
  if (parentLoginBtn) parentLoginBtn.addEventListener('click', parentLogin);
  if (rosterUploadBtn) rosterUploadBtn.addEventListener('click', rosterUpload);
  if (reportRunBtn) reportRunBtn.addEventListener('click', runReport);
  if (pinResetBtn) pinResetBtn.addEventListener('click', () => resetStudentPin('set'));
  if (pinClearBtn) pinClearBtn.addEventListener('click', () => resetStudentPin('clear'));

  async function refreshNotes() {
    if (!sessionToken) return;
    if (notesStatus) notesStatus.textContent = 'Loading notes…';
    const resp = await fetch(`/notes?subject=${encodeURIComponent(gateSubject)}&grade=${encodeURIComponent(String(gateGrade))}`, {
      method: 'GET',
      headers: authHeaders()
    });
    if (!resp.ok) {
      if (notesStatus) notesStatus.textContent = await resp.text();
      return;
    }
    const data = await resp.json();
    const notes = (data && data.notes) ? data.notes : [];
    if (notesList) notesList.innerHTML = '';
    notes.slice(0, 50).forEach((n) => {
      const card = document.createElement('div');
      card.className = 'panel';
      card.style.padding = '10px';
      card.style.cursor = 'pointer';
      card.innerHTML = `<div style="font-weight:800; margin-bottom:4px;">${String(n.title || 'Note')}</div>` +
        `<div class="hint" style="margin-bottom:6px;">${new Date((n.updatedAt || 0) * 1000).toLocaleString()}</div>` +
        `<div style="white-space: pre-wrap; font-size: 13px; color: rgba(255,255,255,0.86);">${String(n.body || '').slice(0, 240)}</div>`;
      card.addEventListener('click', () => {
        if (noteTitle) noteTitle.value = String(n.title || '');
        if (noteBody) noteBody.value = String(n.body || '');
        card.dataset.noteId = String(n.id || '');
        if (notesStatus) notesStatus.textContent = `Loaded note ${String(n.id || '').slice(0, 8)}…`;
      });
      notesList.appendChild(card);
    });
    if (notesStatus) notesStatus.textContent = notes.length ? '' : 'No notes yet.';
  }

  async function saveNote() {
    const title = (noteTitle && noteTitle.value) ? noteTitle.value.trim() : '';
    const body = (noteBody && noteBody.value) ? noteBody.value.trim() : '';
    if (!body) {
      if (notesStatus) notesStatus.textContent = 'Note body is empty.';
      return;
    }
    if (notesStatus) notesStatus.textContent = 'Saving…';
    const resp = await fetch('/notes', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ subject: gateSubject, grade: gateGrade, title: title || 'Note', body, source: 'manual' })
    });
    if (!resp.ok) {
      if (notesStatus) notesStatus.textContent = await resp.text();
      return;
    }
    if (noteTitle) noteTitle.value = '';
    if (noteBody) noteBody.value = '';
    if (notesStatus) notesStatus.textContent = 'Saved.';
    await refreshNotes();
  }

  if (notesBtn) notesBtn.addEventListener('click', async () => {
    showNotesModal(true);
    await refreshNotes();
  });
  if (notesCloseBtn) notesCloseBtn.addEventListener('click', () => showNotesModal(false));
  if (noteSaveBtn) noteSaveBtn.addEventListener('click', saveNote);
  if (noteRefreshBtn) noteRefreshBtn.addEventListener('click', refreshNotes);

  let activeGroup = null; // {id, inviteCode, name}
  let groupWs = null;

  function appendGroupChatLine(who, text) {
    if (!groupChat) return;
    const div = document.createElement('div');
    div.style.whiteSpace = 'pre-wrap';
    div.style.marginBottom = '8px';
    div.innerHTML = `<strong>${DOMPurify ? DOMPurify.sanitize(String(who)) : String(who)}</strong>: ${DOMPurify ? DOMPurify.sanitize(String(text)) : String(text)}`;
    groupChat.appendChild(div);
    groupChat.scrollTop = groupChat.scrollHeight;
  }

  async function refreshGroups() {
    if (!sessionToken) return;
    if (groupsStatus) groupsStatus.textContent = 'Loading groups…';
    const resp = await fetch('/groups', { method: 'GET', headers: authHeaders() });
    if (!resp.ok) {
      if (groupsStatus) groupsStatus.textContent = await resp.text();
      return;
    }
    const data = await resp.json();
    const gs = (data && data.groups) ? data.groups : [];
    if (groupsList) groupsList.innerHTML = '';
    gs.forEach((g) => {
      const card = document.createElement('div');
      card.className = 'panel';
      card.style.padding = '10px';
      card.style.cursor = 'pointer';
      card.innerHTML = `<div style="font-weight:800; margin-bottom:4px;">${String(g.name || 'Group')}</div>` +
        `<div class="hint">Invite: <code>${String(g.inviteCode || '')}</code> · ${String(g.subject || '')} · Grade ${String(g.grade || '')}</div>`;
      card.addEventListener('click', () => {
        openGroup(g);
      });
      groupsList.appendChild(card);
    });
    if (groupsStatus) groupsStatus.textContent = gs.length ? '' : 'No groups yet.';
  }

  function closeGroupWs() {
    try { if (groupWs) groupWs.close(); } catch (_) {}
    groupWs = null;
  }

  function openGroup(g) {
    activeGroup = g;
    if (groupChat) groupChat.innerHTML = '';
    closeGroupWs();
    appendGroupChatLine('System', `Joined "${g.name}"`);
    const wsUrl = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/groups/${encodeURIComponent(g.id)}?token=${encodeURIComponent(sessionToken)}`;
    groupWs = new WebSocket(wsUrl);
    groupWs.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data || '{}');
        if (msg.type === 'history' && Array.isArray(msg.messages)) {
          msg.messages.forEach((m) => appendGroupChatLine(m.studentId.slice(0, 8), m.body));
        } else if (msg.type === 'message' && msg.message) {
          const m = msg.message;
          appendGroupChatLine(String(m.studentId || '').slice(0, 8), m.body);
        }
      } catch (_) {}
    };
    groupWs.onerror = () => appendGroupChatLine('System', 'WebSocket error');
    groupWs.onclose = () => appendGroupChatLine('System', 'Disconnected');
  }

  async function createGroup() {
    const name = (groupNameInput && groupNameInput.value) ? groupNameInput.value.trim() : '';
    if (!name) return;
    if (groupsStatus) groupsStatus.textContent = 'Creating…';
    const resp = await fetch('/groups', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ name, subject: gateSubject, grade: gateGrade })
    });
    if (!resp.ok) {
      if (groupsStatus) groupsStatus.textContent = await resp.text();
      return;
    }
    const g = await resp.json();
    if (groupsStatus) groupsStatus.textContent = `Created. Invite code: ${g.inviteCode}`;
    if (groupNameInput) groupNameInput.value = '';
    await refreshGroups();
    openGroup(g);
  }

  async function joinGroup() {
    const code = (groupInviteInput && groupInviteInput.value) ? groupInviteInput.value.trim() : '';
    if (!code) return;
    if (groupsStatus) groupsStatus.textContent = 'Joining…';
    const resp = await fetch('/groups/join', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ inviteCode: code })
    });
    if (!resp.ok) {
      if (groupsStatus) groupsStatus.textContent = await resp.text();
      return;
    }
    const g = await resp.json();
    if (groupsStatus) groupsStatus.textContent = 'Joined.';
    if (groupInviteInput) groupInviteInput.value = '';
    await refreshGroups();
    openGroup(g);
  }

  function sendGroupMessage() {
    const body = (groupChatInput && groupChatInput.value) ? groupChatInput.value.trim() : '';
    if (!body || !groupWs || groupWs.readyState !== 1) return;
    groupWs.send(JSON.stringify({ body }));
    groupChatInput.value = '';
  }

  if (groupsBtn) groupsBtn.addEventListener('click', async () => {
    showGroupsModal(true);
    await refreshGroups();
  });
  if (groupsCloseBtn) groupsCloseBtn.addEventListener('click', () => {
    showGroupsModal(false);
    closeGroupWs();
  });
  if (groupCreateBtn) groupCreateBtn.addEventListener('click', createGroup);
  if (groupJoinBtn) groupJoinBtn.addEventListener('click', joinGroup);
  if (groupSendBtn) groupSendBtn.addEventListener('click', sendGroupMessage);
  if (groupChatInput) groupChatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      sendGroupMessage();
    }
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  (async () => {
    const ok = await tryResumeSession();
    if (!ok) {
      showAuth(true);
      try {
        await loadProfiles();
      } catch (e) {
        if (authStatus) authStatus.textContent = String(e && e.message ? e.message : e);
      }
    } else {
      showAuth(false);
      addMessage('system', 'Welcome back', `Hi ${currentProfile && currentProfile.pseudonym ? currentProfile.pseudonym : 'student'}!`);
    }
  })();

  addMessage('system', 'Tip', 'Ask anything. MentorBot will respond step-by-step and ask guiding questions.');
  renderMath(chat);
  input.focus();
})();

