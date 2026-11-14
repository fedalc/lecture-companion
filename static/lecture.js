// Class-day page (Phase 1 owns this file). Phase 0 gives a working base to extend.
const lid = pathId();
const student = getStudentName();
let highlighted = null;

const $ = id => document.getElementById(id);

async function loadLecture() {
  const lec = await api(`/api/lectures/${lid}`);
  const course = await api(`/api/courses/${lec.course_id}`);
  renderNav('student', [
    { label: 'Courses', href: '/' },
    { label: course.name, href: `/course/${course.id}` },
    { label: `Class ${lec.number ?? ''}` },
  ]);
  document.title = `${lec.title} · Lecture Companion`;
  $('meta').textContent = `${course.name} · Class ${lec.number ?? ''}${lec.date ? ' · ' + lec.date : ''}`;
  $('title').textContent = lec.title;
  $('topics').innerHTML = lec.topics.map(t =>
    `<span title="${escapeHtml(t.summary)}" class="text-xs bg-stone-100 text-stone-600 px-2 py-0.5 rounded-full">${escapeHtml(t.name)}</span>`).join('');

  const body = document.querySelector('#lecture .lecture-prose');
  if (lec.status !== 'ready') {
    body.innerHTML = `<p class="text-stone-500">This class day is <b>${escapeHtml(lec.status)}</b>. The lecture appears here when it's ready.</p>`;
    if (lec.status === 'generating' || lec.status === 'uploaded') setTimeout(loadLecture, 3000);
  } else {
    body.innerHTML = marked.parse(lec.lecture_md || '');
  }
  $('slides').src = `/api/lectures/${lid}/slides`;
  $('slides-open').href = `/api/lectures/${lid}/slides`;
}

// ---------------------------------------------------------------- chat
function addMessage(role, html) {
  const div = document.createElement('div');
  div.className = role === 'system' ? 'msg-system' : `msg-${role} rounded-2xl px-3.5 py-2.5`;
  div.innerHTML = html;
  $('messages').appendChild(div);
  $('messages').scrollTop = $('messages').scrollHeight;
  return div;
}

async function loadHistory() {
  try {
    const msgs = await api(`/api/lectures/${lid}/chat?student_name=${encodeURIComponent(student)}`);
    msgs.forEach(m => addMessage(m.role, m.role === 'assistant' ? marked.parse(m.content) : escapeHtml(m.content)));
  } catch (_) { /* endpoint not built yet (Phase 1) */ }
  if (!$('messages').children.length) {
    addMessage('assistant', 'Hi! I can explain anything from this class. Select a passage in the lecture and choose <b>Ask about this</b>, or type a question.');
  }
}

$('chat-form').onsubmit = async e => {
  e.preventDefault();
  const message = $('chat-input').value.trim();
  if (!message) return;
  const quote = highlighted;
  addMessage('user', (quote ? `<div class="text-indigo-200 text-xs italic mb-1">“${escapeHtml(quote.slice(0, 140))}”</div>` : '') + escapeHtml(message));
  $('chat-input').value = '';
  clearQuote();
  const pending = addMessage('assistant', '<span class="animate-pulse text-stone-400">Thinking…</span>');
  const btn = e.target.querySelector('button');
  btn.disabled = true;
  try {
    const r = await api(`/api/lectures/${lid}/chat`, { method: 'POST', body: { student_name: student, message, highlighted_text: quote } });
    pending.innerHTML = marked.parse(r.reply || '');
    if (r.refused) pending.insertAdjacentHTML('beforeend', '<div class="mt-1 text-xs text-amber-700">🛡 I can guide you, but not give homework answers.</div>');
    if (r.flagged) pending.insertAdjacentHTML('beforeend', '<div class="mt-1 text-xs text-indigo-700">📨 Not covered in the material, so it was passed on to your lecturer.</div>');
  } catch (err) {
    pending.className = 'msg-system';
    pending.textContent = err.status === 404 || err.status === 405
      ? 'The tutor is not connected yet (Phase 1 builds POST /api/lectures/{id}/chat).'
      : `Error: ${err.message}`;
  } finally {
    btn.disabled = false;
  }
};

// ---------------------------------------------------------------- highlight-to-ask
function setQuote(text) {
  highlighted = text;
  $('quote-text').textContent = `“${text}”`;
  $('quote').classList.remove('hidden');
  $('chat-input').focus();
}
function clearQuote() { highlighted = null; $('quote').classList.add('hidden'); }
$('quote-clear').onclick = clearQuote;

const popup = $('sel-popup');
document.getElementById('lecture').addEventListener('mouseup', () => {
  setTimeout(() => {
    const sel = window.getSelection();
    const text = sel.toString().trim();
    if (text.length < 3) { popup.style.display = 'none'; return; }
    const rect = sel.getRangeAt(0).getBoundingClientRect();
    popup.style.left = `${Math.max(8, rect.left + rect.width / 2 - 90)}px`;
    popup.style.top = `${Math.max(8, rect.top - 44)}px`;
    popup.style.display = 'flex';
    popup.dataset.text = text;
  }, 0);
});
document.addEventListener('mousedown', e => { if (!popup.contains(e.target)) popup.style.display = 'none'; });

$('sel-ask').onclick = () => {
  setQuote(popup.dataset.text);
  if (!$('chat-input').value) $('chat-input').value = 'Can you explain this part?';
  popup.style.display = 'none';
};
$('sel-note').onclick = async () => {
  const text = popup.dataset.text;
  popup.style.display = 'none';
  const content = prompt('Your note:');
  if (!content) return;
  try {
    await api(`/api/lectures/${lid}/notes`, { method: 'POST', body: { student_name: student, highlighted_text: text, content } });
    addMessage('system', 'Note saved.');
  } catch (_) {
    addMessage('system', 'Notes are not connected yet (Phase 1 builds /api/lectures/{id}/notes).');
  }
};

loadLecture().then(loadHistory).catch(err => {
  $('title').textContent = 'Class day not found';
  console.error(err);
});
