(() => {
  'use strict';

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
  const quizCloseBtn = document.getElementById('quizCloseBtn');
  const quizRetryBtn = document.getElementById('quizRetryBtn');
  const quizResult = document.getElementById('quizResult');

  let currentQuiz = null; // { quizId, title, questions: [{id, question, options}] }

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

  function pushHistory(role, content) {
    if (role !== 'user' && role !== 'assistant') return;
    history.push({ role, content: String(content || '') });
    if (history.length > 24) history.splice(0, history.length - 24);
  }

  function setBusy(busy) {
    chat.setAttribute('aria-busy', busy ? 'true' : 'false');
    sendBtn.disabled = busy;
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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ concept, history })
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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ quizId: currentQuiz.quizId, answers })
      });
      if (!resp.ok) {
        const txt = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${txt}`);
      }
      const result = await resp.json();

      quizResult.style.display = 'block';
      quizResult.className = 'quizResult';
      quizResult.textContent = `${result.message} (>= 60% means understood)`;

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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, history })
      });

      if (!resp.ok) {
        const txt = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${txt}`);
      }

      const data = await resp.json();
      const answer = (data && data.answer) ? data.answer : '(empty response)';
      addMessage('bot', 'MentorBot', answer);
      pushHistory('assistant', answer);
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
  quizCloseBtn.addEventListener('click', () => showQuizPanel(false));
  quizRetryBtn.addEventListener('click', generateQuiz);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  addMessage('system', 'Tip', 'Ask anything. MentorBot will respond step-by-step and ask guiding questions.');
  renderMath(chat);
  input.focus();
})();

