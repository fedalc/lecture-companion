// Shared helpers for every page (Phase 0). Load with <script src="/static/common.js"></script>

/** fetch wrapper: api('/api/courses'), api('/api/x', {method:'POST', body:{...}}) */
async function api(path, opts = {}) {
  const init = { method: opts.method || 'GET', headers: {} };
  if (opts.body instanceof FormData) {
    init.body = opts.body;
  } else if (opts.body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    const err = new Error(`${res.status} ${detail}`);
    err.status = res.status;
    throw err;
  }
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res;
}

// ------------------------------------------------------------------ identity (multi-user showcase)
// No auth: the current user is {id, name, role} kept per tab in sessionStorage (so two tabs can be two
// different people) with localStorage as the default for new tabs. The nav switcher is the only way to change it.
// The user's name is what goes into `student_name`.
const USER_KEY = 'current_user';

function _readUser(store) {
  try { return JSON.parse(store.getItem(USER_KEY) || 'null'); } catch (_) { return null; }
}
function getCurrentUser() { return _readUser(sessionStorage) || _readUser(localStorage); }
function setCurrentUser(u) {
  if (!u) { sessionStorage.removeItem(USER_KEY); localStorage.removeItem(USER_KEY); return; }
  const v = JSON.stringify({ id: u.id, name: u.name, role: u.role });
  sessionStorage.setItem(USER_KEY, v);
  localStorage.setItem(USER_KEY, v);
}

/** The current user's name (sent as student_name). If nobody is selected (and ask=true) it returns
 *  'Guest' and opens the "Who are you?" picker; picking someone reloads the page. */
function getStudentName(ask = true) {
  const u = getCurrentUser();
  if (u) return u.name;
  if (ask) showUserPicker();
  return ask ? 'Guest' : null;
}

/** Kept for older callers: opens the user picker. */
function showNameDialog() { showUserPicker(); }

/** The course the current page belongs to, if any (used to list its students first). */
async function currentCourseId() {
  const [kind, id] = location.pathname.split('/').filter(Boolean);
  try {
    if (kind === 'course' || kind === 'selfeval') return parseInt(id, 10);
    if (kind === 'lecture') return (await api(`/api/lectures/${id}`)).course_id;
    if (kind === 'quiz') return (await api(`/api/quizzes/${id}`)).course_id;
  } catch (_) {}
  return null;
}

/** Where to go after switching to `u`: teachers land on their dashboard, students leave it. */
function afterSwitch(u) {
  const p = location.pathname;
  if (p.startsWith('/people')) location.reload();
  else if (u.role === 'teacher') location.href = '/lecturer';
  else if (p.startsWith('/lecturer')) location.href = '/';
  else location.reload();
}

const ROLE_BADGE = {
  teacher: '<span class="text-[10px] uppercase tracking-wide font-semibold px-1.5 py-0.5 rounded bg-amber-100 text-amber-800">teacher</span>',
  student: '<span class="text-[10px] uppercase tracking-wide font-semibold px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-800">student</span>',
};
function roleBadge(role) { return ROLE_BADGE[role] || ''; }
function initials(name) {
  return String(name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase();
}

/** Modal to pick who you are / switch user. Lists teachers and students (this course's students
 *  first), with search, a "new student" join form and a link to /people. */
async function showUserPicker() {
  if (document.getElementById('user-picker')) return;
  const me = getCurrentUser();
  const d = document.createElement('div');
  d.id = 'user-picker';
  d.className = 'fixed inset-0 z-50 bg-stone-900/30 grid place-items-center p-4';
  d.innerHTML = `<div class="bg-white rounded-2xl shadow-xl w-full max-w-md flex flex-col max-h-[85vh]">
      <div class="p-5 pb-3">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="text-lg font-semibold">${me ? 'Switch user' : 'Who are you?'}</div>
            <p class="text-sm text-stone-500">${me ? 'Act as any student or teacher.' : 'Pick yourself from the list, or join as a new student.'}</p>
          </div>
          ${me ? '<button data-close class="text-stone-400 hover:text-stone-700 text-xl leading-none" aria-label="Close">×</button>' : ''}
        </div>
        <input id="up-search" type="search" placeholder="Search people…" class="mt-3 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
      </div>
      <div id="up-list" class="panel-scroll px-3 pb-2 flex-1 min-h-[6rem] text-sm"><div class="p-3 text-stone-400">Loading…</div></div>
      <form id="up-join" class="border-t border-stone-200 p-4 flex gap-2">
        <input required maxlength="60" class="flex-1 min-w-0 rounded-lg border border-stone-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder="New student? Type your name">
        <button class="rounded-lg bg-indigo-600 text-white px-4 py-2 text-sm font-medium hover:bg-indigo-700">Join</button>
      </form>
      <a href="/people" class="block text-center text-sm text-indigo-600 hover:underline pb-4 -mt-1">Manage people →</a>
    </div>`;
  (document.body || document.documentElement).appendChild(d);
  const close = () => d.remove();
  if (me) {
    d.querySelector('[data-close]').onclick = close;
    d.addEventListener('click', e => { if (e.target === d) close(); });
    document.addEventListener('keydown', function esc(e) { if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc); } });
  }
  const pick = u => { setCurrentUser(u); afterSwitch(u); };

  const [users, cid] = await Promise.all([api('/api/users').catch(() => []), currentCourseId()]);
  const list = d.querySelector('#up-list'), search = d.querySelector('#up-search');
  const row = u => `<button data-uid="${u.id}" class="w-full flex items-center gap-3 px-2 py-1.5 rounded-lg text-left hover:bg-stone-100 ${me && me.id === u.id ? 'bg-indigo-50' : ''}">
      <span class="w-7 h-7 shrink-0 rounded-full ${u.role === 'teacher' ? 'bg-amber-100 text-amber-800' : 'bg-indigo-100 text-indigo-800'} grid place-items-center text-xs font-semibold">${escapeHtml(initials(u.name))}</span>
      <span class="flex-1 min-w-0 truncate">${escapeHtml(u.name)}</span>${me && me.id === u.id ? '<span class="text-xs text-indigo-600">you</span>' : ''}</button>`;
  const section = (title, us) => us.length ? `<div class="px-2 pt-3 pb-1 text-xs font-semibold uppercase tracking-wide text-stone-400">${escapeHtml(title)} · ${us.length}</div>${us.map(row).join('')}` : '';
  const draw = () => {
    const q = search.value.trim().toLowerCase();
    const shown = users.filter(u => !q || u.name.toLowerCase().includes(q));
    const teachers = shown.filter(u => u.role === 'teacher');
    const students = shown.filter(u => u.role === 'student');
    const inCourse = cid ? students.filter(u => u.course_ids.includes(cid)) : [];
    const others = cid ? students.filter(u => !u.course_ids.includes(cid)) : students;
    const html = cid
      ? section('Students in this course', inCourse) + section(inCourse.length ? 'Other students' : 'Students', others) + section('Teachers', teachers)
      : section('Teachers', teachers) + section('Students', students);
    list.innerHTML = html ||`<div class="p-3 text-stone-400">${users.length ? 'Nobody matches.' : 'No people yet. Join below or add some on the People page.'}</div>`;
  };
  draw();
  search.oninput = draw;
  list.onclick = e => {
    const b = e.target.closest('[data-uid]');
    if (b) pick(users.find(u => String(u.id) === b.dataset.uid));
  };
  d.querySelector('#up-join').onsubmit = async e => {
    e.preventDefault();
    const name = e.target.querySelector('input').value.trim();
    if (!name) return;
    try { pick(await api('/api/users/join', { method: 'POST', body: { name, course_id: cid } })); }
    catch (err) { alert(err.message); }
  };
  if (window.matchMedia('(min-width: 640px)').matches) search.focus();
}

/** Re-check the stored user against the server (renamed or deleted on /people). */
async function refreshCurrentUser() {
  const u = getCurrentUser();
  if (!u) return;
  try {
    const fresh = await api(`/api/users/${u.id}`);
    if (fresh.name !== u.name || fresh.role !== u.role) { setCurrentUser(fresh); location.reload(); }
  } catch (err) {
    if (err.status === 404) { setCurrentUser(null); showUserPicker(); }
  }
}

/** id from the URL: /lecture/3 -> 3 */
function pathId() { return parseInt(location.pathname.split('/').filter(Boolean).pop(), 10); }

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

const STATUS_STYLES = {
  ready: 'bg-emerald-100 text-emerald-800',
  generating: 'bg-amber-100 text-amber-800 animate-pulse',
  uploaded: 'bg-slate-100 text-slate-700',
  error: 'bg-rose-100 text-rose-800',
};
function statusBadge(status) {
  return `<span class="text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_STYLES[status] || STATUS_STYLES.uploaded}">${escapeHtml(status)}</span>`;
}

/** Top navigation. role: 'student' | 'lecturer' | 'people' (which view is active).
 *  Right side: links to the views and a chip with the current user that opens the switcher. */
function renderNav(role = 'student', crumbs = []) {
  const nav = document.createElement('header');
  nav.className = 'h-14 shrink-0 border-b border-stone-200 bg-white/90 backdrop-blur flex items-center px-3 sm:px-5 gap-3 sm:gap-4 z-20';
  const crumbHtml = crumbs.map(c => c.href
    ? `<a href="${c.href}" class="hover:text-stone-900">${escapeHtml(c.label)}</a>`
    : `<span class="text-stone-900 font-medium">${escapeHtml(c.label)}</span>`).join('<span class="text-stone-300">/</span>');
  const me = getCurrentUser();
  const tab = (href, label, on) => `<a href="${href}" class="px-2 sm:px-3 py-1 rounded-md ${on ? 'bg-white shadow-sm text-stone-900' : 'text-stone-500 hover:text-stone-900'}">${label}</a>`;
  // only teachers get view tabs; students just have the logo (home) and the user chip
  const views = me && me.role === 'teacher'
    ? [tab('/lecturer', 'Dashboard', role === 'lecturer'), tab('/', 'Student view', role === 'student')] : [];
  nav.innerHTML = `
    <a href="/" class="flex items-center gap-2 font-semibold tracking-tight text-stone-900 shrink-0">
      <span class="w-7 h-7 rounded-lg bg-indigo-600 text-white grid place-items-center text-sm">L</span>
      <span class="hidden lg:inline">Lecture Companion</span>
    </a>
    <nav class="hidden md:flex items-center gap-2 text-sm text-stone-500 min-w-0 truncate">${crumbHtml}</nav>
    <div class="ml-auto flex items-center gap-2 sm:gap-3 text-sm min-w-0">
      ${views.length ? `<div class="flex rounded-lg bg-stone-100 p-0.5 shrink-0">${views.join('')}</div>` : ''}
      <button id="who" title="Switch user" class="flex items-center gap-2 rounded-full border border-stone-200 bg-white pl-1 pr-2 sm:pr-3 py-1 hover:border-indigo-300 min-w-0">
        ${me ? `<span class="w-6 h-6 shrink-0 rounded-full ${me.role === 'teacher' ? 'bg-amber-100 text-amber-800' : 'bg-indigo-100 text-indigo-800'} grid place-items-center text-[11px] font-semibold">${escapeHtml(initials(me.name))}</span>
          <span class="hidden sm:inline truncate max-w-[9rem] text-stone-900">${escapeHtml(me.name)}</span>
          <span class="hidden sm:inline">${roleBadge(me.role)}</span>`
        : '<span class="w-6 h-6 rounded-full bg-stone-100 grid place-items-center text-stone-400">?</span><span class="text-stone-500">Choose user</span>'}
        <svg class="w-3 h-3 text-stone-400 shrink-0" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 4.5 6 7.5 9 4.5"/></svg>
      </button>
    </div>`;
  document.body.prepend(nav);
  nav.querySelector('#who').onclick = showUserPicker;
  refreshCurrentUser();
  startHeartbeat();
}

/** Presence for "friends online": ping the server while this tab is open and visible. */
function startHeartbeat() {
  const beat = () => {
    const u = getCurrentUser();
    if (u && document.visibilityState === 'visible') api(`/api/users/${u.id}/seen`, { method: 'POST' }).catch(() => {});
  };
  beat();
  setInterval(beat, 60000);
  document.addEventListener('visibilitychange', beat);
}

/** Friendly placeholder for features another phase still has to build. */
function comingSoon(what, phase) {
  return `<div class="rounded-xl border border-dashed border-stone-300 bg-stone-50 p-6 text-center text-stone-500">
    <div class="font-medium text-stone-700">${escapeHtml(what)}</div>
    <div class="text-sm mt-1">Coming in ${escapeHtml(phase)}</div></div>`;
}
