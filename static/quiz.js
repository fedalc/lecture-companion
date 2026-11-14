// Quiz page (Phase 2). Also defines the shared quiz runner used by selfeval.js:
//   runQuiz(el, quiz, {onSubmit(answers) -> Promise<attemptResult>, onDone(result)})
// /quiz/{qid}             -> take the quiz (homework, live)
// /quiz/{qid}?present=1   -> fullscreen QR + live results for the projector

const LETTERS = ['A', 'B', 'C', 'D', 'E', 'F'];

/** One question at a time. Calls opts.onSubmit(answers) at the end and passes the result to opts.onDone. */
function runQuiz(el, quiz, opts) {
  const answers = {};
  let i = 0;

  function render() {
    const q = quiz.questions[i];
    const last = i === quiz.questions.length - 1;
    const pct = Math.round((i / quiz.questions.length) * 100);
    el.innerHTML = `
      <div class="flex items-center justify-between text-sm text-stone-500">
        <span>Question ${i + 1} of ${quiz.questions.length}</span>
        ${q.lecture_title ? `<span class="truncate ml-3">${escapeHtml(q.lecture_title)}</span>` : ''}
      </div>
      <div class="mt-2 h-1.5 rounded-full bg-stone-200 overflow-hidden"><div class="h-full bg-indigo-600 transition-all" style="width:${pct}%"></div></div>
      <h2 class="mt-6 text-lg sm:text-xl font-semibold leading-snug">${escapeHtml(q.text)}</h2>
      <div class="mt-5 space-y-3">
        ${q.options.map((o, k) => `
          <button data-k="${k}" class="opt w-full text-left flex gap-3 items-start rounded-xl border-2 p-4 transition
              ${answers[q.id] === k ? 'border-indigo-600 bg-indigo-50' : 'border-stone-200 bg-white hover:border-indigo-300'}">
            <span class="shrink-0 w-7 h-7 rounded-lg grid place-items-center text-sm font-semibold
              ${answers[q.id] === k ? 'bg-indigo-600 text-white' : 'bg-stone-100 text-stone-600'}">${LETTERS[k]}</span>
            <span class="pt-0.5">${escapeHtml(o)}</span>
          </button>`).join('')}
      </div>
      <div class="mt-6 flex gap-3">
        <button id="back" class="px-4 py-3 rounded-xl border border-stone-300 text-stone-600 ${i === 0 ? 'invisible' : ''}">Back</button>
        <button id="next" class="flex-1 py-3 rounded-xl bg-indigo-600 text-white font-medium disabled:opacity-40" ${answers[q.id] === undefined ? 'disabled' : ''}>
          ${last ? 'Submit answers' : 'Next'}</button>
      </div>
      <p id="err" class="mt-3 text-sm text-rose-600"></p>`;
    el.querySelectorAll('.opt').forEach(b => b.onclick = () => { answers[q.id] = +b.dataset.k; render(); });
    el.querySelector('#back').onclick = () => { i--; render(); };
    el.querySelector('#next').onclick = async e => {
      if (!last) { i++; render(); return; }
      e.target.disabled = true;
      e.target.textContent = 'Submitting…';
      try {
        const payload = quiz.questions.map(x => ({ question_id: x.id, chosen_index: answers[x.id] ?? null }));
        const result = await opts.onSubmit(payload);
        opts.onDone(result, answers);
      } catch (err) {
        el.querySelector('#err').textContent = err.message;
        e.target.disabled = false;
        e.target.textContent = 'Submit answers';
      }
    };
  }
  render();
}

/** Per-question review: chosen vs correct + explanation. */
function renderReview(quiz, result) {
  const byId = Object.fromEntries(result.results.map(r => [r.question_id, r]));
  return quiz.questions.map((q, n) => {
    const r = byId[q.id] || {};
    return `
      <div class="rounded-xl border ${r.is_correct ? 'border-emerald-200' : 'border-rose-200'} bg-white p-4">
        <div class="flex gap-2 items-start">
          <span class="shrink-0 mt-0.5 w-6 h-6 rounded-full grid place-items-center text-xs font-bold text-white ${r.is_correct ? 'bg-emerald-500' : 'bg-rose-500'}">${r.is_correct ? '✓' : '✗'}</span>
          <div class="font-medium">${n + 1}. ${escapeHtml(q.text)}</div>
        </div>
        <ul class="mt-3 space-y-1.5 text-sm">
          ${q.options.map((o, k) => {
            const correct = k === r.correct_index, chosen = k === r.chosen_index;
            const cls = correct ? 'bg-emerald-50 text-emerald-900 font-medium' : chosen ? 'bg-rose-50 text-rose-900 line-through' : 'text-stone-500';
            return `<li class="rounded-lg px-3 py-1.5 ${cls}">${LETTERS[k]}. ${escapeHtml(o)}${chosen ? ' <span class="no-underline text-xs">(your answer)</span>' : ''}</li>`;
          }).join('')}
        </ul>
        ${r.explanation ? `<p class="mt-3 text-sm text-stone-600"><b>Why:</b> ${escapeHtml(r.explanation)}</p>` : ''}
      </div>`;
  }).join('');
}

function scoreRing(score, total) {
  const pct = total ? Math.round((score / total) * 100) : 0;
  const color = pct >= 80 ? 'text-emerald-600' : pct >= 60 ? 'text-amber-600' : 'text-rose-600';
  return `<div class="text-5xl font-bold ${color}">${score}<span class="text-2xl text-stone-400">/${total}</span></div>
          <div class="text-stone-500 mt-1">${pct}% correct</div>`;
}

// ------------------------------------------------------------------ /quiz/{qid}

async function quizPage() {
  const app = document.getElementById('app');
  const qid = pathId();
  let quiz;
  try { quiz = await api(`/api/quizzes/${qid}`); }
  catch (e) {
    renderNav('student', [{ label: 'Courses', href: '/' }, { label: 'Quiz' }]);
    app.innerHTML = `<div class="text-center text-stone-500">Quiz not found.</div>`;
    return;
  }
  const crumbs = [{ label: 'Courses', href: '/' }];
  if (quiz.course_name) crumbs.push({ label: quiz.course_name, href: `/course/${quiz.course_id}` });
  crumbs.push({ label: quiz.title || 'Quiz' });

  if (new URLSearchParams(location.search).has('present')) return presentView(quiz, crumbs);

  renderNav('student', crumbs);
  document.title = `${quiz.title} · Lecture Companion`;
  const kindLabel = { homework: 'Homework', live: 'Live quiz', self_eval: 'Self-evaluation', bank: 'Practice' }[quiz.kind] || 'Quiz';

  if (!quiz.is_open) {
    app.innerHTML = `<div class="rounded-2xl bg-white border border-stone-200 p-8 text-center">
      <div class="text-xl font-semibold">${escapeHtml(quiz.title)}</div>
      <p class="text-stone-500 mt-2">This quiz is closed.</p>
      ${quiz.lecture_id ? `<a href="/lecture/${quiz.lecture_id}" class="mt-4 inline-block text-indigo-600 font-medium">Go to the class day →</a>` : ''}</div>`;
    return;
  }

  const name = getStudentName();  // shows the name dialog if missing
  app.innerHTML = `
    <div class="rounded-2xl bg-white border border-stone-200 p-6 sm:p-8">
      <span class="text-xs font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full ${quiz.kind === 'live' ? 'bg-rose-100 text-rose-700' : 'bg-indigo-100 text-indigo-700'}">${kindLabel}</span>
      <h1 class="mt-3 text-2xl font-semibold tracking-tight">${escapeHtml(quiz.title)}</h1>
      ${quiz.lecture_title ? `<p class="text-stone-500 mt-1">Class day: ${escapeHtml(quiz.lecture_title)}</p>` : ''}
      <p class="mt-4 text-stone-600">${quiz.questions.length} multiple-choice questions, one at a time. You'll see the right answers and why at the end.</p>
      <p class="mt-2 text-sm text-stone-500">Answering as <b>${escapeHtml(name)}</b></p>
      <button id="start" class="mt-6 w-full py-3 rounded-xl bg-indigo-600 text-white font-medium hover:bg-indigo-700">Start</button>
      ${quiz.kind !== 'self_eval' ? `<a href="?present=1" class="mt-3 block text-center text-sm text-stone-500 hover:text-stone-800">Show QR code for the class</a>` : ''}
    </div>`;
  app.querySelector('#start').onclick = () => runQuiz(app, quiz, {
    onSubmit: answers => api(`/api/quizzes/${qid}/attempts`, { method: 'POST', body: { student_name: getStudentName(false) || 'Guest', answers } }),
    onDone: result => {
      app.innerHTML = `
        <div class="rounded-2xl bg-white border border-stone-200 p-6 text-center">
          <div class="text-sm uppercase tracking-wide text-stone-400">Your score</div>
          <div class="mt-2">${scoreRing(result.score, result.total)}</div>
          ${quiz.lecture_id ? `<a href="/lecture/${quiz.lecture_id}" class="mt-5 inline-block px-4 py-2 rounded-lg bg-indigo-600 text-white font-medium">Review the class day</a>` : ''}
        </div>
        <h2 class="mt-8 mb-3 text-sm font-semibold uppercase tracking-wide text-stone-400">Answers</h2>
        <div class="space-y-3">${renderReview(quiz, result)}</div>`;
      window.scrollTo(0, 0);
    },
  });
}

// ------------------------------------------------------------------ projector view

function presentView(quiz, crumbs) {
  renderNav('lecturer', crumbs);
  const main = document.getElementById('app');
  main.className = 'flex-1 w-full max-w-6xl mx-auto px-6 py-8 grid lg:grid-cols-2 gap-10 items-center';
  main.innerHTML = `
    <div class="text-center">
      <div class="text-sm uppercase tracking-widest text-stone-400">Scan to join</div>
      <h1 class="mt-2 text-3xl font-bold tracking-tight">${escapeHtml(quiz.title)}</h1>
      <img src="/api/quizzes/${quiz.id}/qr" alt="QR code" class="mt-6 mx-auto w-full max-w-md aspect-square rounded-2xl bg-white p-3 shadow-sm border border-stone-200">
      <div class="mt-4 font-mono text-lg text-stone-700 break-all">${escapeHtml(quiz.join_url)}</div>
      <p class="mt-1 text-sm text-stone-400">Phones must be on the same Wi-Fi network.</p>
    </div>
    <div class="rounded-2xl bg-white border border-stone-200 p-6">
      <div class="flex items-baseline justify-between">
        <h2 class="font-semibold">Live results</h2>
        <button id="fs" class="text-sm text-stone-500 hover:text-stone-900">Fullscreen</button>
      </div>
      <div id="live" class="mt-4 text-stone-500">Waiting for answers…</div>
    </div>`;
  main.querySelector('#fs').onclick = () => document.documentElement.requestFullscreen?.();

  async function poll() {
    try {
      const r = await api(`/api/quizzes/${quiz.id}/results`);
      document.getElementById('live').innerHTML = `
        <div class="flex gap-8">
          <div><div class="text-4xl font-bold text-stone-900">${r.n_attempts}</div><div class="text-sm">students answered</div></div>
          <div><div class="text-4xl font-bold text-stone-900">${Math.round(r.avg_score * 100)}%</div><div class="text-sm">average score</div></div>
        </div>
        <div class="mt-6 space-y-3">
          ${r.questions.map((q, n) => {
            const pct = Math.round(q.pct_correct * 100);
            const bar = pct >= 70 ? 'bg-emerald-500' : pct >= 40 ? 'bg-amber-500' : 'bg-rose-500';
            return `<div>
              <div class="flex justify-between text-sm gap-3"><span class="truncate text-stone-700">${n + 1}. ${escapeHtml(q.text)}</span><span class="shrink-0">${q.n_answers ? pct + '%' : '–'}</span></div>
              <div class="mt-1 h-2 rounded-full bg-stone-100 overflow-hidden"><div class="h-full ${bar}" style="width:${q.n_answers ? pct : 0}%"></div></div>
            </div>`;
          }).join('')}
        </div>`;
    } catch (_) {}
  }
  poll();
  setInterval(poll, 3000);
}

if (location.pathname.startsWith('/quiz/')) quizPage();
