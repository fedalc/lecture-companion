// Class-day page (Phase 1): AI lecture + slides + tutor chat + highlight-to-ask + notes.
const lid = pathId();
const student = getStudentName();
let highlighted = null;   // passage quoted into the chat
let lectureMd = null;     // markdown of the AI lecture (null until ready)
let notes = [];
let lectureTopics = [];
let topicAnchors = [];
let topicSlidePages = [];
let pdfDocument = null;
let slidePageElements = [];
let syncUntil = 0;
let resizeTimer = null;
let slidesLoadStarted = false;
let activeTopicIndex = -1;

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
  lectureTopics = lec.topics || [];
  $('topics').innerHTML = lectureTopics.map((t, i) =>
    `<button type="button" data-topic="${i}" title="Scroll to ${escapeHtml(t.name)} in the lecture and slides" class="topic-chip text-xs bg-stone-100 text-stone-600 px-2 py-0.5 rounded-full hover:bg-indigo-100 hover:text-indigo-700">${escapeHtml(t.name)}</button>`).join('');
  $('topics').onclick = e => {
    const chip = e.target.closest('[data-topic]');
    if (chip) syncTopic(Number(chip.dataset.topic), true);
  };

  const body = document.querySelector('#lecture .lecture-prose');
  if (lec.status !== 'ready') {
    body.innerHTML = `<p class="text-stone-500">This class day is <b>${escapeHtml(lec.status)}</b>. The lecture appears here when it's ready.</p>`;
    if (lec.status === 'generating' || lec.status === 'uploaded') setTimeout(loadLecture, 3000);
  } else {
    lectureMd = lec.lecture_md || '';
    renderLecture();
  }
  $('slides-open').href = `/api/lectures/${lid}/slides`;
  if (!slidesLoadStarted) { slidesLoadStarted = true; loadSlidePages(); }
}

/** Render the lecture markdown and mark every passage the student has a note on. */
function renderLecture() {
  if (lectureMd === null) return;
  const body = document.querySelector('#lecture .lecture-prose');
  body.innerHTML = marked.parse(lectureMd);
  notes.forEach(n => n.highlighted_text && markPassage(body, n));
  buildTopicAnchors();
}

function normalizeTopic(text) {
  return String(text || '').toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
}

function buildTopicAnchors() {
  const body = document.querySelector('#lecture .lecture-prose');
  if (!body || !lectureTopics.length) return;
  const headings = [...body.querySelectorAll('h1,h2,h3,h4')];
  const blocks = [...body.querySelectorAll('h1,h2,h3,h4,p,li')];
  topicAnchors = lectureTopics.map((topic, i) => {
    const name = normalizeTopic(topic.name);
    let target = headings.find(h => normalizeTopic(h.textContent).includes(name) || name.includes(normalizeTopic(h.textContent)));
    if (!target) target = blocks.find(b => normalizeTopic(b.textContent).includes(name));
    if (!target && blocks.length) target = blocks[Math.round(i * (blocks.length - 1) / Math.max(1, lectureTopics.length - 1))];
    if (target) target.classList.add('topic-anchor');
    return target || body;
  });
}

function topicWords(topic) {
  return [...new Set(normalizeTopic(`${topic.name} ${topic.summary || ''}`).split(' ').filter(w => w.length > 3))];
}

async function loadSlidePages() {
  const viewer = $('slides-viewer');
  if (!window.pdfjsLib) {
    viewer.innerHTML = '<div class="p-4 text-sm text-rose-700">The slide viewer could not load. Use “open PDF” to view the slides.</div>';
    return;
  }
  pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
  viewer.innerHTML = '<div class="p-4 text-sm text-stone-500">Loading slides…</div>';
  try {
    pdfDocument = await pdfjsLib.getDocument(`/api/lectures/${lid}/slides`).promise;
    const pageText = [];
    for (let i = 1; i <= pdfDocument.numPages; i++) {
      const page = await pdfDocument.getPage(i);
      const content = await page.getTextContent();
      pageText.push(content.items.map(item => item.str).join(' '));
    }
    topicSlidePages = lectureTopics.map((topic, index) => {
      const terms = topicWords(topic);
      const scores = pageText.map(text => {
        const normalized = normalizeTopic(text);
        const exact = normalized.includes(normalizeTopic(topic.name)) ? 100 : 0;
        const overlap = terms.filter(word => normalized.includes(word)).length;
        return exact + overlap;
      });
      const best = Math.max(...scores);
      return best > 0 ? scores.indexOf(best) + 1
        : Math.round(index * (pdfDocument.numPages - 1) / Math.max(1, lectureTopics.length - 1)) + 1;
    });
    await renderSlideCanvases();
    viewer.addEventListener('scroll', onSlidesScroll, { passive: true });
    document.querySelector('#lecture').addEventListener('scroll', onLectureScroll, { passive: true });
    window.addEventListener('resize', () => {
      clearTimeout(resizeTimer); resizeTimer = setTimeout(renderSlideCanvases, 180);
    });
    if (lectureTopics.length) syncTopic(0, false);
  } catch (err) {
    slidesLoadStarted = false;
    viewer.innerHTML = `<div class="p-4 text-sm text-rose-700">Could not display slides here. <a class="underline" href="/api/lectures/${lid}/slides" target="_blank">Open the PDF</a>.</div>`;
    console.error('Could not load PDF slides', err);
  }
}

async function renderSlideCanvases() {
  if (!pdfDocument) return;
  const viewer = $('slides-viewer');
  viewer.innerHTML = '';
  slidePageElements = [];
  const availableWidth = Math.max(260, viewer.clientWidth - 24);
  for (let i = 1; i <= pdfDocument.numPages; i++) {
    const page = await pdfDocument.getPage(i);
    const base = page.getViewport({ scale: 1 });
    const scale = Math.min(availableWidth / base.width, 1.6);
    const viewport = page.getViewport({ scale });
    const canvas = document.createElement('canvas');
    canvas.className = 'slide-page'; canvas.dataset.slidePage = i;
    const context = canvas.getContext('2d');
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.floor(viewport.width * ratio);
    canvas.height = Math.floor(viewport.height * ratio);
    canvas.style.width = `${Math.floor(viewport.width)}px`;
    canvas.style.height = `${Math.floor(viewport.height)}px`;
    viewer.appendChild(canvas);
    slidePageElements.push(canvas);
    await page.render({ canvasContext: context, viewport: page.getViewport({ scale: scale * ratio }) }).promise;
  }
}

function scrollWithin(container, target) {
  const top = container.scrollTop + target.getBoundingClientRect().top - container.getBoundingClientRect().top - 18;
  container.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
}

function syncTopic(index, animate = true, source = null) {
  if (index < 0 || index >= lectureTopics.length) return;
  if (source && index === activeTopicIndex) return;
  activeTopicIndex = index;
  syncUntil = Date.now() + (animate ? 220 : 60);
  const anchor = topicAnchors[index];
  if (source !== 'lecture' && anchor) scrollWithin($('lecture'), anchor);
  const page = slidePageElements[topicSlidePages[index] - 1];
  if (source !== 'slides' && page) scrollWithin($('slides-viewer'), page);
  document.querySelectorAll('.topic-chip').forEach((chip, i) => {
    chip.classList.toggle('bg-indigo-100', i === index);
    chip.classList.toggle('text-indigo-700', i === index);
  });
}

function onLectureScroll() {
  if (Date.now() < syncUntil || !topicAnchors.length) return;
  const containerTop = $('lecture').getBoundingClientRect().top + 35;
  let active = 0;
  topicAnchors.forEach((anchor, i) => { if (anchor.getBoundingClientRect().top <= containerTop) active = i; });
  syncTopic(active, true, 'lecture');
}

function onSlidesScroll() {
  if (Date.now() < syncUntil || !slidePageElements.length) return;
  const threshold = $('slides-viewer').getBoundingClientRect().top + $('slides-viewer').clientHeight * 0.32;
  let page = 1;
  slidePageElements.forEach((el, i) => { if (el.getBoundingClientRect().top <= threshold) page = i + 1; });
  let active = 0, best = Infinity;
  topicSlidePages.forEach((topicPage, i) => {
    const distance = Math.abs(topicPage - page);
    if (distance < best) { best = distance; active = i; }
  });
  syncTopic(active, true, 'slides');
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
