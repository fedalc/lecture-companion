// Class-day page (Phase 1): AI lecture + slides + tutor chat + highlight-to-ask + notes.
const lid = pathId();
const student = getStudentName();
let highlighted = null;   // passage quoted into the chat
let lectureMd = null;     // markdown of the AI lecture (null until ready)
let notes = [];

const $ = id => document.getElementById(id);
const studentQ = `student_name=${encodeURIComponent(student)}`;

// ---------------------------------------------------------------- lecture
async function loadLecture() {
  const lec = await api(`/api/lectures/${lid}`);
  const course = await api(`/api/courses/${lec.course_id}`);
  if (!document.querySelector('body > header')) {
    renderNav('student', [
      { label: 'Courses', href: '/' },
      { label: course.name, href: `/course/${course.id}` },
      { label: `Class ${lec.number ?? ''}` },
    ]);
  }
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
    lectureMd = lec.lecture_md || '';
    renderLecture();
  }
  $('slides').src = `/api/lectures/${lid}/slides`;
  $('slides-open').href = `/api/lectures/${lid}/slides`;
}

/** Render the lecture markdown and mark every passage the student has a note on. */
function renderLecture() {
  if (lectureMd === null) return;
  const body = document.querySelector('#lecture .lecture-prose');
  body.innerHTML = marked.parse(lectureMd);
  notes.forEach(n => n.highlighted_text && markPassage(body, n));
}

/** Wrap the first occurrence of the note's passage (inside one text node) in a <mark>. */
function markPassage(root, note) {
  const needle = note.highlighted_text.replace(/\s+/g, ' ').trim();
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node; (node = walker.nextNode());) {
    if (node.parentElement.closest('mark')) continue;
    const i = node.nodeValue.indexOf(needle);
    if (i < 0) continue;
    const range = document.createRange();
    range.setStart(node, i);
    range.setEnd(node, i + needle.length);
    const mark = document.createElement('mark');
    mark.className = 'note-mark';
    mark.dataset.noteId = note.id;
    mark.title = note.content;
    range.surroundContents(mark);
    mark.onclick = () => { showTab('notes'); flash(document.querySelector(`[data-note-card="${note.id}"]`)); };
    return;
  }
}

function flash(el) {
  if (!el) return;
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.classList.add('flash', 'ring-2', 'ring-amber-400');
  setTimeout(() => el.classList.remove('flash', 'ring-2', 'ring-amber-400'), 1200);
}

// ---------------------------------------------------------------- tabs
function showTab(name) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('tab-active', b.dataset.tab === name));
  $('chat-pane').classList.toggle('hidden', name !== 'chat');
  $('notes-pane').classList.toggle('hidden', name !== 'notes');
}
document.querySelectorAll('.tab-btn').forEach(b => b.onclick = () => showTab(b.dataset.tab));

// ---------------------------------------------------------------- chat
function addMessage(role, html) {
  const div = document.createElement('div');
  div.className = role === 'system' ? 'msg-system' : `msg-${role} rounded-2xl px-3.5 py-2.5`;
  div.innerHTML = html;
  $('messages').appendChild(div);
  $('messages').scrollTop = $('messages').scrollHeight;
  return div;
}

function userHtml(message, quote) {
  return (quote ? `<div class="text-indigo-200 text-xs italic mb-1">“${escapeHtml(quote.slice(0, 140))}${quote.length > 140 ? '…' : ''}”</div>` : '')
    + escapeHtml(message);
}

function assistantHtml(m) {
  let html = marked.parse(m.content || m.reply || '');
  if (m.refused) html += '<div class="mt-2 text-xs text-amber-700 font-medium">🛡 Open homework question: I can guide you, but not give the answer.</div>';
  if (m.flagged) html += '<div class="mt-2 text-xs text-indigo-700 font-medium">📨 Not covered in the material, so it was passed on to your lecturer.</div>';
  return html;
}

async function loadHistory() {
  try {
    const msgs = await api(`/api/lectures/${lid}/chat?${studentQ}`);
    msgs.forEach(m => addMessage(m.role, m.role === 'assistant' ? assistantHtml(m) : userHtml(m.content, m.highlighted_text)));
  } catch (err) { console.error(err); }
  if (!$('messages').children.length) {
    addMessage('assistant', 'Hi! I can explain anything from this class. Select a passage in the lecture and choose <b>Ask about this</b>, or type a question.');
  }
}
// the right-hand grid settles after fonts/iframe load, so scroll the chat to the end a few times
function scrollChatToEnd() {
  [0, 300, 1000].forEach(ms => setTimeout(() => { $('messages').scrollTop = $('messages').scrollHeight; }, ms));
}

$('chat-form').onsubmit = async e => {
  e.preventDefault();
  const message = $('chat-input').value.trim();
  if (!message) return;
  const quote = highlighted;
  addMessage('user', userHtml(message, quote));
  $('chat-input').value = '';
  clearQuote();
  const pending = addMessage('assistant', '<span class="animate-pulse text-stone-400">Thinking…</span>');
  const btn = e.target.querySelector('button');
  btn.disabled = $('chat-input').disabled = true;
  try {
    const r = await api(`/api/lectures/${lid}/chat`, { method: 'POST', body: { student_name: student, message, highlighted_text: quote } });
    pending.innerHTML = assistantHtml(r);
  } catch (err) {
    pending.className = 'msg-system';
    pending.textContent = `Sorry, the tutor had a problem (${err.message}). Please try again.`;
  } finally {
    btn.disabled = $('chat-input').disabled = false;
    $('chat-input').focus();
    $('messages').scrollTop = $('messages').scrollHeight;
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
$('lecture').addEventListener('mouseup', () => {
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
  showTab('chat');
  setQuote(popup.dataset.text);
  if (!$('chat-input').value) $('chat-input').value = 'Can you explain this part?';
  popup.style.display = 'none';
};

// ---------------------------------------------------------------- notes
let noteQuote = null;

$('sel-note').onclick = () => {
  noteQuote = popup.dataset.text;
  popup.style.display = 'none';
  window.getSelection().removeAllRanges();
  showTab('notes');
  $('note-quote').textContent = `“${noteQuote}”`;
  $('note-form').classList.remove('hidden');
  $('note-input').value = '';
  $('note-input').focus();
};
$('note-cancel').onclick = () => $('note-form').classList.add('hidden');

$('note-form').onsubmit = async e => {
  e.preventDefault();
  const content = $('note-input').value.trim();
  if (!content) return;
  try {
    const note = await api(`/api/lectures/${lid}/notes`, { method: 'POST', body: { student_name: student, highlighted_text: noteQuote, content } });
    notes.unshift(note);
    $('note-form').classList.add('hidden');
    renderNotes();
    renderLecture();
  } catch (err) {
    alert(`Could not save the note: ${err.message}`);
  }
};

async function loadNotes() {
  try { notes = await api(`/api/lectures/${lid}/notes?${studentQ}`); } catch (err) { console.error(err); notes = []; }
  renderNotes();
  renderLecture();
}

function renderNotes() {
  $('notes-count').textContent = notes.length;
  $('notes-list').innerHTML = notes.length ? notes.map(n => `
    <div data-note-card="${n.id}" class="group rounded-lg border border-stone-200 p-3 hover:border-amber-300 cursor-pointer">
      ${n.highlighted_text ? `<div class="text-xs italic text-stone-500 border-l-4 border-amber-300 pl-2 mb-1.5 line-clamp-2">“${escapeHtml(n.highlighted_text)}”</div>` : ''}
      <div class="whitespace-pre-wrap text-stone-800">${escapeHtml(n.content)}</div>
      <div class="mt-1.5 flex text-xs text-stone-400">
        <span>${escapeHtml((n.created_at || '').slice(0, 16))}</span>
        <button data-del="${n.id}" class="ml-auto opacity-0 group-hover:opacity-100 hover:text-rose-600">Delete</button>
      </div>
    </div>`).join('')
    : '<p class="text-stone-400 text-center mt-6">No notes yet. Select a passage in the lecture and choose <b>Add note</b>.</p>';

  $('notes-list').querySelectorAll('[data-note-card]').forEach(card => card.onclick = e => {
    const del = e.target.closest('[data-del]');
    if (del) { deleteNote(+del.dataset.del); return; }
    flash(document.querySelector(`mark[data-note-id="${card.dataset.noteCard}"]`));
  });
}

async function deleteNote(id) {
  if (!confirm('Delete this note?')) return;
  await api(`/api/notes/${id}?${studentQ}`, { method: 'DELETE' });
  notes = notes.filter(n => n.id !== id);
  renderNotes();
  renderLecture();
}

loadLecture().then(() => Promise.all([loadHistory(), loadNotes()])).then(scrollChatToEnd).catch(err => {
  $('title').textContent = 'Class day not found';
  console.error(err);
});
