// Lecturer page (Phase 3): class days + upload, quizzes, insights dashboard.
renderNav('lecturer', [{ label: 'Lecturer' }]);
const me = getCurrentUser();
const isTeacher = !!me && me.role === 'teacher';

const $ = s => document.querySelector(s);
const state = { cid: null, tab: 'class', lectures: [], insights: null, chart: null, pollTimer: null, liveTimer: null };
// categorical palette (fixed order, validated): class day N -> slot N
const SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#7c5cd6', '#9a6b3e'];
const lecColor = n => SERIES[((n || 1) - 1) % SERIES.length];
const pct = x => (x == null ? '–' : Math.round(x * 100) + '%');
const ago = s => {
  const d = (Date.now() - new Date(s.replace(' ', 'T') + 'Z')) / 1000;
  if (isNaN(d)) return '';
  if (d < 60) return 'just now';
  if (d < 3600) return Math.floor(d / 60) + ' min ago';
  if (d < 86400) return Math.floor(d / 3600) + ' h ago';
  return Math.floor(d / 86400) + ' d ago';
};

// ------------------------------------------------------------------ tabs
function showTab(tab) {
  state.tab = tab;
  document.querySelectorAll('#tabs button').forEach(b => {
    const on = b.dataset.tab === tab;
    b.classList.toggle('border-indigo-600', on); b.classList.toggle('border-transparent', !on);
    b.classList.toggle('text-stone-900', on); b.classList.toggle('font-medium', on); b.classList.toggle('text-stone-500', !on);
  });
  document.querySelectorAll('[data-panel]').forEach(p => p.classList.toggle('hidden', p.dataset.panel !== tab));
  history.replaceState(null, '', '#' + tab);
  refreshTab();
}
document.querySelectorAll('#tabs button').forEach(btn => btn.onclick = () => showTab(btn.dataset.tab));

function refreshTab() {
  if (!state.cid) return;
  if (state.tab === 'class') loadClasses();
  if (state.tab === 'quizzes') loadQuizzes();
  if (state.tab === 'insights') loadInsights();
}

// ------------------------------------------------------------------ courses
async function loadCourses(selectId) {
  const courses = await api(`/api/courses?teacher_id=${me.id}`);
  const sel = $('#course-select');
  sel.innerHTML = courses.map(c => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join('')
    || '<option value="">No courses yet</option>';
  const saved = selectId || localStorage.getItem('lecturer_course');
  if (courses.some(c => String(c.id) === String(saved))) sel.value = saved;
  state.cid = sel.value || null;
  if (!courses.length) $('#new-course-form').classList.remove('hidden');
  $('#no-course').classList.toggle('hidden', courses.length > 0);
  document.querySelectorAll('[data-panel], #tabs').forEach(el => el.classList.toggle('invisible', !courses.length));
}
$('#course-select').onchange = e => {
  state.cid = e.target.value; localStorage.setItem('lecturer_course', state.cid);
  if (state.chart) { state.chart.destroy(); state.chart = null; }
  refreshTab();
};
$('#new-course-btn').onclick = () => $('#new-course-form').classList.toggle('hidden');
$('#new-course-cancel').onclick = () => $('#new-course-form').classList.add('hidden');
$('#new-course-form').onsubmit = async e => {
  e.preventDefault();
  const f = new FormData(e.target);
  const c = await api('/api/courses', { method: 'POST', body: { name: f.get('name'), teacher_id: me.id } });
  e.target.reset(); e.target.classList.add('hidden');
  localStorage.setItem('lecturer_course', c.id);
  await loadCourses(c.id);
  showTab('class');
};

// ------------------------------------------------------------------ class tab
$('#upload-form').date.value = new Date().toISOString().slice(0, 10);
$('#upload-form').onsubmit = async e => {
  e.preventDefault();
  if (!state.cid) return;
  const form = e.target, btn = form.querySelector('button'), msg = $('#upload-msg');
  btn.disabled = true; msg.className = 'text-sm mt-2 text-stone-500'; msg.textContent = 'Uploading…';
  try {
    const r = await api(`/api/courses/${state.cid}/lectures`, { method: 'POST', body: new FormData(form) });
    msg.className = 'text-sm mt-2 text-emerald-700';
    msg.textContent = `Class day ${r.number} uploaded. The AI is preparing it, this page updates by itself.`;
    form.title.value = ''; form.file.value = '';
    loadClasses();
  } catch (err) {
    msg.className = 'text-sm mt-2 text-rose-700'; msg.textContent = 'Upload failed: ' + err.message;
  } finally { btn.disabled = false; }
};

async function loadClasses() {
  const cid = state.cid;
  const lectures = await api(`/api/courses/${cid}/lectures`);
  if (cid !== state.cid) return;
  state.lectures = lectures;
  $('#class-list').innerHTML = lectures.map(l => `
    <div class="flex flex-wrap items-center gap-4 rounded-xl bg-white border border-stone-200 p-4">
      <div class="w-10 h-10 rounded-lg bg-stone-100 grid place-items-center font-semibold text-stone-600">${l.number ?? ''}</div>
      <div class="flex-1 min-w-[10rem]"><div class="font-medium truncate">${escapeHtml(l.title)}</div>
        <div class="text-sm text-stone-500">${escapeHtml(l.date || '')}${l.status === 'generating' ? ' · AI is writing the lecture…' : ''}${l.status === 'error' ? ' · processing failed' : ''}</div></div>
      ${statusBadge(l.status)}
      ${l.status === 'error' ? `<button data-regen="${l.id}" class="text-sm text-rose-700 hover:underline">Retry</button>` : ''}
      ${l.status === 'ready'
        ? `<a href="/lecture/${l.id}" target="_blank" class="text-sm text-indigo-600 hover:underline">Preview as student ↗</a>`
        : `<a href="/api/lectures/${l.id}/slides" target="_blank" class="text-sm text-stone-500 hover:underline">Slides ↗</a>`}
    </div>`).join('') || '<p class="text-stone-500">No class days yet. Upload the first one above.</p>';
  document.querySelectorAll('[data-regen]').forEach(b => b.onclick = async () => {
    await api(`/api/lectures/${b.dataset.regen}/regenerate`, { method: 'POST' }); loadClasses();
  });
  // poll while something is still being processed
  clearTimeout(state.pollTimer);
  if (lectures.some(l => l.status === 'uploaded' || l.status === 'generating'))
    state.pollTimer = setTimeout(() => { if (state.tab === 'class') loadClasses(); }, 2000);
}

// ------------------------------------------------------------------ quizzes tab
async function loadQuizzes() {
  const cid = state.cid;
  const [lectures, quizzes] = await Promise.all([api(`/api/courses/${cid}/lectures`), api(`/api/courses/${cid}/quizzes`)]);
  if (cid !== state.cid) return;
  state.lectures = lectures;
  $('#gen-list').innerHTML = lectures.map(l => `
    <div class="rounded-xl bg-white border border-stone-200 p-4">
      <div class="flex items-center gap-2"><span class="w-2.5 h-2.5 rounded-full" style="background:${lecColor(l.number)}"></span>
        <span class="text-sm text-stone-500">Class ${l.number}</span>${l.status !== 'ready' ? statusBadge(l.status) : ''}</div>
      <div class="font-medium truncate">${escapeHtml(l.title)}</div>
      <div class="mt-3 flex flex-wrap items-center gap-2">
        <select data-n="${l.id}" class="rounded-lg border border-stone-300 px-2 py-1.5 text-sm bg-white" ${l.status !== 'ready' ? 'disabled' : ''}>
          ${[3, 5, 8, 10].map(n => `<option ${n === 5 ? 'selected' : ''}>${n}</option>`).join('')}</select>
        <span class="text-sm text-stone-500">questions</span>
        <button data-gen="${l.id}" data-kind="homework" ${l.status !== 'ready' ? 'disabled' : ''}
          class="rounded-lg bg-indigo-600 text-white px-3 py-1.5 text-sm font-medium hover:bg-indigo-700 disabled:opacity-40">Homework</button>
        <button data-gen="${l.id}" data-kind="live" ${l.status !== 'ready' ? 'disabled' : ''}
          class="rounded-lg border border-indigo-600 text-indigo-700 px-3 py-1.5 text-sm font-medium hover:bg-indigo-50 disabled:opacity-40">Live quiz</button>
      </div>
      <div data-genmsg="${l.id}" class="text-sm mt-2"></div>
    </div>`).join('') || '<p class="text-stone-500">Add a class day first.</p>';
  document.querySelectorAll('[data-gen]').forEach(b => b.onclick = () => generateQuiz(b));
  renderQuizList(quizzes);
}

async function generateQuiz(btn) {
  const lid = btn.dataset.gen, kind = btn.dataset.kind, msg = document.querySelector(`[data-genmsg="${lid}"]`);
  const n = parseInt(document.querySelector(`[data-n="${lid}"]`).value, 10);
  document.querySelectorAll(`[data-gen="${lid}"]`).forEach(b => b.disabled = true);
  msg.className = 'text-sm mt-2 text-stone-500'; msg.textContent = 'The AI is writing the questions…';
  try {
    const r = await api(`/api/lectures/${lid}/quizzes`, { method: 'POST', body: { kind, n } });
    msg.className = 'text-sm mt-2 text-emerald-700';
    msg.innerHTML = kind === 'live'
      ? `Live quiz ready. <a class="underline" target="_blank" href="/quiz/${r.quiz_id}?present=1">Show QR on the projector ↗</a>`
      : `Homework quiz created and open. Students see it on the course page.`;
    const quizzes = await api(`/api/courses/${state.cid}/quizzes`);
    renderQuizList(quizzes, r.quiz_id);
  } catch (err) {
    msg.className = 'text-sm mt-2 text-rose-700';
    msg.textContent = err.status === 404 || err.status === 405 ? 'Quiz generation isn\'t available yet (Phase 2 endpoint missing).' : 'Failed: ' + err.message;
  } finally {
    document.querySelectorAll(`[data-gen="${lid}"]`).forEach(b => b.disabled = false);
  }
}

function renderQuizList(quizzes, highlightId) {
  $('#quiz-list').innerHTML = quizzes.map(q => `
    <div class="flex flex-wrap items-center gap-3 rounded-xl bg-white border ${q.id === highlightId ? 'border-indigo-400 ring-2 ring-indigo-100' : 'border-stone-200'} p-3">
      <span class="text-xs font-medium px-2 py-0.5 rounded-full ${q.kind === 'live' ? 'bg-violet-100 text-violet-800' : 'bg-sky-100 text-sky-800'}">${q.kind === 'live' ? 'Live' : 'Homework'}</span>
      <div class="flex-1 min-w-[10rem]">
        <div class="font-medium text-sm truncate">${escapeHtml(q.title || 'Quiz')}</div>
        <div class="text-xs text-stone-500">${q.n_questions} questions · ${q.n_attempts} attempt${q.n_attempts === 1 ? '' : 's'}${q.avg_score != null ? ' · avg ' + pct(q.avg_score) : ''}</div>
      </div>
      <label class="flex items-center gap-2 text-sm cursor-pointer select-none">
        <input type="checkbox" data-toggle="${q.id}" ${q.is_open ? 'checked' : ''} class="sr-only peer">
        <span class="w-9 h-5 rounded-full bg-stone-300 peer-checked:bg-emerald-500 relative transition after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:w-4 after:h-4 after:rounded-full after:bg-white after:transition peer-checked:after:translate-x-4"></span>
        <span class="w-12 ${q.is_open ? 'text-emerald-700' : 'text-stone-500'}">${q.is_open ? 'Open' : 'Closed'}</span>
      </label>
      <a href="/quiz/${q.id}?present=1" target="_blank" class="text-sm rounded-lg border border-stone-300 px-2.5 py-1 hover:bg-stone-50">QR / results ↗</a>
      <a href="/quiz/${q.id}" target="_blank" class="text-sm text-indigo-600 hover:underline">Open ↗</a>
    </div>`).join('') || '<p class="text-stone-500 text-sm">No quizzes yet.</p>';
  document.querySelectorAll('[data-toggle]').forEach(cb => cb.onchange = async () => {
    try { await api(`/api/quizzes/${cb.dataset.toggle}`, { method: 'PATCH', body: { is_open: cb.checked } }); }
    catch (err) { alert('Could not update: ' + err.message); }
    renderQuizList(await api(`/api/courses/${state.cid}/quizzes`));
  });
}

// ------------------------------------------------------------------ insights tab
async function loadInsights() {
  const cid = state.cid;
  clearTimeout(state.liveTimer);
  let d;
  try { d = await api(`/api/courses/${cid}/insights`); }
  catch (err) { $('#kpis').innerHTML = `<p class="text-rose-700 col-span-4">Could not load insights: ${escapeHtml(err.message)}</p>`; return; }
  if (cid !== state.cid) return;
  state.insights = d;
  renderKpis(d.totals);
  renderChart(d.topics);
  renderTable(d.topics);
  renderMisTopics(d.topics);
  renderList('#flagged', d.flagged_questions, true);
  renderList('#recent', d.recent_questions, false);
  // keep it live while the tab is open (so a newly flagged question shows up during the demo)
  state.liveTimer = setTimeout(() => { if (state.tab === 'insights' && !document.hidden) loadInsights(); else state.liveTimer = null; }, 8000);
}
document.addEventListener('visibilitychange', () => { if (!document.hidden && state.tab === 'insights') loadInsights(); });

function renderKpis(t) {
  const tiles = [
    ['Active students', t.n_students],
    ['Quiz attempts', t.n_attempts],
    ['Tutor questions', t.n_chat],
    ['Not covered (flagged)', t.n_flagged, t.n_refused ? `${t.n_refused} homework answers withheld` : ''],
  ];
  $('#kpis').innerHTML = tiles.map(([label, v, sub]) => `
    <div class="rounded-xl bg-white border border-stone-200 p-4">
      <div class="text-xs text-stone-500">${label}</div>
      <div class="text-2xl font-semibold tabular-nums mt-1">${v ?? 0}</div>
      ${sub ? `<div class="text-xs text-stone-500 mt-0.5">${sub}</div>` : ''}
    </div>`).join('');
}

function renderChart(topics) {
  const top = topics.slice(0, 12);
  const lecs = [...new Map(topics.map(t => [t.lecture_number, t.lecture_title])).entries()].sort((a, b) => a[0] - b[0]);
  $('#legend').innerHTML = lecs.map(([n, title]) =>
    `<span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-sm" style="background:${lecColor(n)}"></span>Class ${n}: ${escapeHtml(title)}</span>`).join('');
  $('#chart-wrap').style.height = Math.max(160, top.length * 30 + 40) + 'px';
  if (!top.length) { $('#chart-wrap').innerHTML = '<p class="text-stone-500 text-sm">No topics yet.</p>'; return; }
  if (!$('#chart')) $('#chart-wrap').innerHTML = '<canvas id="chart"></canvas>';
  const data = {
    labels: top.map(t => t.name),
    datasets: [{
      data: top.map(t => t.struggle_score),
      backgroundColor: top.map(t => lecColor(t.lecture_number)),
      borderRadius: 4, borderSkipped: 'start', barThickness: 16,
    }],
  };
  if (state.chart) { state.chart.data = data; state.chart.$topics = top; state.chart.update('none'); return; }
  state.chart = new Chart($('#chart'), {
    type: 'bar', data,
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
      scales: {
        x: { min: 0, max: 1, grid: { color: '#f0efec' }, border: { display: false },
             ticks: { color: '#78716c', callback: v => v.toFixed(1) },
             title: { display: true, text: 'Struggle score (0–1)', color: '#78716c' } },
        y: { grid: { display: false }, border: { display: false }, ticks: { color: '#1c1917', font: { size: 12 } } },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1c1917', padding: 10, displayColors: false,
          callbacks: {
            title: items => items[0].label,
            label: item => {
              const t = state.chart.$topics[item.dataIndex];
              return [`Class ${t.lecture_number}: ${t.lecture_title}`, `Struggle score: ${t.struggle_score.toFixed(2)}`,
                `Quiz error rate: ${pct(t.error_rate)} of ${t.n_answers} answers`,
                `Tutor questions: ${t.n_questions}`, `Not covered: ${t.n_flagged}`];
            },
          },
        },
      },
    },
  });
  state.chart.$topics = top;
}

function renderTable(topics) {
  const byLec = [...topics].sort((a, b) => a.lecture_number - b.lecture_number || b.struggle_score - a.struggle_score);
  $('#topic-table').innerHTML = `<table class="w-full text-sm">
    <thead class="text-left text-stone-500 text-xs"><tr><th class="py-1 pr-3">Class</th><th class="pr-3">Topic</th>
      <th class="pr-3 text-right">Score</th><th class="pr-3 text-right">Error rate</th><th class="pr-3 text-right">Answers</th>
      <th class="pr-3 text-right">Questions</th><th class="text-right">Flagged</th></tr></thead>
    <tbody>${byLec.map(t => `<tr class="border-t border-stone-100">
      <td class="py-1.5 pr-3 whitespace-nowrap"><span class="inline-block w-2 h-2 rounded-sm mr-1.5" style="background:${lecColor(t.lecture_number)}"></span>${t.lecture_number}</td>
      <td class="pr-3">${escapeHtml(t.name)}</td><td class="pr-3 text-right tabular-nums font-medium">${t.struggle_score.toFixed(2)}</td>
      <td class="pr-3 text-right tabular-nums">${pct(t.error_rate)}</td><td class="pr-3 text-right tabular-nums">${t.n_answers}</td>
      <td class="pr-3 text-right tabular-nums">${t.n_questions}</td><td class="text-right tabular-nums">${t.n_flagged}</td></tr>`).join('')}</tbody></table>`;
}
$('#toggle-table').onclick = () => {
  const show = $('#topic-table').classList.toggle('hidden') === false;
  $('#chart-wrap').classList.toggle('hidden', show); $('#legend').classList.toggle('hidden', show);
  $('#toggle-table').textContent = show ? 'Chart view' : 'Table view';
};

function renderMisTopics(topics) {
  const sel = $('#mis-topic'), prev = sel.value;
  sel.innerHTML = topics.map(t => `<option value="${t.topic_id}">${escapeHtml(t.name)} (class ${t.lecture_number})</option>`).join('');
  if (prev && topics.some(t => String(t.topic_id) === prev)) sel.value = prev;
}
$('#mis-btn').onclick = async () => {
  const btn = $('#mis-btn'), out = $('#mis-out');
  btn.disabled = true; out.innerHTML = '<p class="text-stone-500">The AI is reading the wrong answers and questions…</p>';
  try {
    const r = await api(`/api/courses/${state.cid}/insights/misconceptions`, { method: 'POST', body: { topic_id: parseInt($('#mis-topic').value, 10) || null } });
    out.innerHTML = `<div class="text-xs text-stone-500 not-prose mb-1">${escapeHtml(r.topic_name)} · ${escapeHtml(r.lecture_title || '')}</div>` + marked.parse(escapeHtml(r.summary));
  } catch (err) {
    out.innerHTML = `<p class="text-rose-700">Failed: ${escapeHtml(err.message)}</p>`;
  } finally { btn.disabled = false; }
};

function renderList(sel, items, flagged) {
  $(sel).innerHTML = items.map(m => `
    <li class="py-2.5">
      <div class="text-sm text-stone-900">${escapeHtml(m.content)}</div>
      ${m.highlighted_text ? `<div class="text-xs text-stone-500 italic mt-0.5 line-clamp-1">on: "${escapeHtml(m.highlighted_text)}"</div>` : ''}
      <div class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-stone-500">
        <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-sm" style="background:${lecColor(m.lecture_number)}"></span>
          <a href="/lecture/${m.lecture_id}" target="_blank" class="hover:underline">Class ${m.lecture_number}</a></span>
        ${m.topic_name ? `<span>· ${escapeHtml(m.topic_name)}</span>` : ''}
        ${!flagged && m.flagged ? '<span class="px-1.5 rounded bg-amber-100 text-amber-800">not covered</span>' : ''}
        ${m.refused ? '<span class="px-1.5 rounded bg-rose-100 text-rose-800">homework answer withheld</span>' : ''}
        <span class="ml-auto">${ago(m.created_at)}</span>
      </div>
    </li>`).join('') || `<li class="py-3 text-sm text-stone-500">${flagged ? 'Nothing flagged yet.' : 'No questions yet.'}</li>`;
}

// ------------------------------------------------------------------ start
const startTab = ['class', 'quizzes', 'insights'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'class';
if (isTeacher) {
  $('#teacher-name').textContent = me.name;
  loadCourses().then(() => showTab(startTab));
} else {
  // the dashboard belongs to a teacher: ask who
  document.querySelector('main').innerHTML = `
    <div class="max-w-md mx-auto mt-10 rounded-2xl bg-white border border-stone-200 p-6 text-center">
      <div class="text-lg font-semibold">The dashboard is for teachers</div>
      <p class="text-stone-500 mt-1">${me ? `You're acting as the student <b>${escapeHtml(me.name)}</b> right now.` : 'Nobody is selected yet.'} Pick a teacher to continue.</p>
      <button id="teacher-pick" class="mt-4 rounded-lg bg-indigo-600 text-white px-4 py-2 text-sm font-medium hover:bg-indigo-700">Switch user</button>
    </div>`;
  $('#teacher-pick').onclick = showUserPicker;
}
window.addEventListener('hashchange', () => {
  const t = location.hash.slice(1);
  if (['class', 'quizzes', 'insights'].includes(t) && t !== state.tab) showTab(t);
});
