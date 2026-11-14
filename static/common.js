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

/** The student's name, stored in localStorage. If missing (and ask=true) it returns 'Guest'
 *  and shows a small non-blocking dialog; saving a name reloads the page. */
function getStudentName(ask = true) {
  const name = localStorage.getItem('student_name');
  if (!name && ask) { showNameDialog(); return 'Guest'; }
  return name;
}

function showNameDialog() {
  if (document.getElementById('name-dialog')) return;
  const d = document.createElement('div');
  d.id = 'name-dialog';
  d.className = 'fixed inset-0 z-50 bg-stone-900/30 grid place-items-center p-4';
  d.innerHTML = `<form class="bg-white rounded-2xl shadow-xl p-6 w-full max-w-sm">
      <div class="text-lg font-semibold">Welcome! What's your name?</div>
      <p class="text-sm text-stone-500 mt-1">Used to keep your notes and progress. No account needed.</p>
      <input required autofocus class="mt-4 w-full rounded-lg border border-stone-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder="e.g. Giulia">
      <button class="mt-4 w-full rounded-lg bg-indigo-600 text-white py-2 font-medium hover:bg-indigo-700">Continue</button>
    </form>`;
  d.querySelector('form').onsubmit = e => {
    e.preventDefault();
    setStudentName(d.querySelector('input').value.trim() || 'Guest');
    location.reload();
  };
  (document.body || document.documentElement).appendChild(d);
}

function setStudentName(name) { localStorage.setItem('student_name', name); }

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

/** Top navigation. role: 'student' | 'lecturer' */
function renderNav(role = 'student', crumbs = []) {
  const nav = document.createElement('header');
  nav.className = 'h-14 shrink-0 border-b border-stone-200 bg-white/90 backdrop-blur flex items-center px-5 gap-4 z-20';
  const crumbHtml = crumbs.map(c => c.href
    ? `<a href="${c.href}" class="hover:text-stone-900">${escapeHtml(c.label)}</a>`
    : `<span class="text-stone-900 font-medium">${escapeHtml(c.label)}</span>`).join('<span class="text-stone-300">/</span>');
  const name = role === 'student' ? getStudentName(false) : null;
  nav.innerHTML = `
    <a href="/" class="flex items-center gap-2 font-semibold tracking-tight text-stone-900">
      <span class="w-7 h-7 rounded-lg bg-indigo-600 text-white grid place-items-center text-sm">L</span>
      Lecture Companion
    </a>
    <nav class="flex items-center gap-2 text-sm text-stone-500 min-w-0 truncate">${crumbHtml}</nav>
    <div class="ml-auto flex items-center gap-3 text-sm">
      ${role === 'student' ? `<button id="who" class="text-stone-500 hover:text-stone-900">${name ? 'Studying as <b>' + escapeHtml(name) + '</b>' : 'Set your name'}</button>` : ''}
      <div class="flex rounded-lg bg-stone-100 p-0.5">
        <a href="/" class="px-3 py-1 rounded-md ${role === 'student' ? 'bg-white shadow-sm text-stone-900' : 'text-stone-500'}">Student</a>
        <a href="/lecturer" class="px-3 py-1 rounded-md ${role === 'lecturer' ? 'bg-white shadow-sm text-stone-900' : 'text-stone-500'}">Lecturer</a>
      </div>
    </div>`;
  document.body.prepend(nav);
  const who = nav.querySelector('#who');
  if (who) who.onclick = showNameDialog;
}

/** Friendly placeholder for features another phase still has to build. */
function comingSoon(what, phase) {
  return `<div class="rounded-xl border border-dashed border-stone-300 bg-stone-50 p-6 text-center text-stone-500">
    <div class="font-medium text-stone-700">${escapeHtml(what)}</div>
    <div class="text-sm mt-1">Coming in ${escapeHtml(phase)}</div></div>`;
}
