// Self-evaluation page (Phase 2). Uses runQuiz / renderReview / scoreRing from quiz.js.
// /selfeval/{cid}               -> intro -> test -> "lectures to review" report
// /selfeval/{cid}?attempt={aid} -> show a past report

(async () => {
  const cid = pathId();
  const app = document.getElementById('app');
  const course = await api(`/api/courses/${cid}`).catch(() => ({ name: 'Course' }));
  renderNav('student', [{ label: 'Courses', href: '/' }, { label: course.name, href: `/course/${cid}` }, { label: 'Self-evaluation' }]);
  document.title = `Self-evaluation · ${course.name}`;

  const attemptParam = new URLSearchParams(location.search).get('attempt');
  if (attemptParam) return showReport(attemptParam);

  const name = getStudentName();
  const lectures = (await api(`/api/courses/${cid}/lectures`)).filter(l => l.status === 'ready');
  app.innerHTML = `
    <div class="rounded-2xl bg-indigo-600 text-white p-6 sm:p-8">
      <div class="text-sm uppercase tracking-wide text-indigo-200">Exam prep · ${escapeHtml(course.name)}</div>
      <h1 class="text-2xl font-semibold mt-1">Where do you stand?</h1>
      <p class="text-indigo-100 mt-3">${lectures.length * 2} questions, 2 from each of the ${lectures.length} class days.
        At the end you'll see which lectures to review, with direct links and the topics you missed.</p>
      <p class="text-indigo-200 text-sm mt-3">Answering as <b class="text-white">${escapeHtml(name)}</b> · takes about ${Math.max(2, lectures.length)} minutes</p>
      <button id="start" class="mt-6 w-full sm:w-auto px-6 py-3 rounded-xl bg-white text-indigo-700 font-semibold hover:bg-indigo-50" ${lectures.length ? '' : 'disabled'}>Start the test</button>
      <p id="err" class="mt-3 text-sm text-rose-200"></p>
    </div>`;

  app.querySelector('#start').onclick = async e => {
    e.target.disabled = true;
    e.target.textContent = 'Preparing…';
    try {
      const { quiz_id } = await api(`/api/courses/${cid}/self-eval`, { method: 'POST', body: { student_name: getStudentName(false) || 'Guest' } });
      const quiz = await api(`/api/quizzes/${quiz_id}`);
      runQuiz(app, quiz, {
        onSubmit: answers => api(`/api/quizzes/${quiz_id}/attempts`, { method: 'POST', body: { student_name: getStudentName(false) || 'Guest', answers } }),
        onDone: result => {
          history.replaceState(null, '', `?attempt=${result.attempt_id}`);
          showReport(result.attempt_id, quiz, result);
        },
      });
    } catch (err) {
      app.querySelector('#err').textContent = err.message;
      e.target.disabled = false;
      e.target.textContent = 'Start the test';
    }
  };

  async function showReport(aid, quiz, result) {
    const rep = await api(`/api/attempts/${aid}/report`);
    const weak = rep.per_lecture.filter(p => p.weak);
    app.innerHTML = `
      <div class="rounded-2xl bg-white border border-stone-200 p-6 flex flex-col sm:flex-row sm:items-center gap-6">
        <div class="text-center sm:text-left">${scoreRing(rep.score, rep.total)}</div>
        <div class="sm:border-l sm:pl-6 border-stone-200">
          <div class="text-lg font-semibold">${weak.length
            ? `Review ${weak.length === 1 ? 'this lecture' : `these ${weak.length} lectures`} before the exam`
            : 'Nice, you are on track for every lecture'}</div>
          <p class="text-stone-500 text-sm mt-1">A lecture is marked for review when you score under 60% on it.</p>
        </div>
      </div>

      <h2 class="mt-8 mb-3 text-sm font-semibold uppercase tracking-wide text-stone-400">By class day</h2>
      <div class="space-y-3">
        ${rep.per_lecture.map(p => `
          <div class="rounded-xl bg-white border ${p.weak ? 'border-rose-200' : 'border-stone-200'} p-4 flex flex-col sm:flex-row sm:items-center gap-3">
            <div class="flex items-center gap-4 flex-1 min-w-0">
              <div class="w-10 h-10 shrink-0 rounded-lg ${p.weak ? 'bg-rose-100 text-rose-700' : 'bg-emerald-100 text-emerald-700'} grid place-items-center font-semibold">${p.number ?? ''}</div>
              <div class="min-w-0">
                <div class="font-medium truncate">${escapeHtml(p.title)}</div>
                <div class="text-sm text-stone-500">${p.score}/${p.total} correct${p.weak_topics.length ? ` · missed: ${p.weak_topics.map(escapeHtml).join(', ')}` : ''}</div>
              </div>
            </div>
            ${p.weak
              ? `<a href="${p.url}" class="shrink-0 text-center px-4 py-2 rounded-lg bg-rose-600 text-white text-sm font-medium hover:bg-rose-700">Review this lecture →</a>`
              : `<a href="${p.url}" class="shrink-0 text-center px-4 py-2 rounded-lg text-sm text-emerald-700 bg-emerald-50">On track ✓</a>`}
          </div>`).join('')}
      </div>
      ${quiz && result ? `
        <details class="mt-8">
          <summary class="cursor-pointer text-sm font-semibold uppercase tracking-wide text-stone-400">See every answer</summary>
          <div class="mt-3 space-y-3">${renderReview(quiz, result)}</div>
        </details>` : ''}
      <div class="mt-8 flex gap-3">
        <a href="/selfeval/${cid}" class="px-4 py-2 rounded-lg border border-stone-300 text-stone-700">Take another test</a>
        <a href="/course/${cid}" class="px-4 py-2 rounded-lg text-stone-500">Back to the course</a>
      </div>`;
    window.scrollTo(0, 0);
  }
})();
