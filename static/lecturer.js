// Lecturer page (Phase 3 owns this file). Phase 0: tabs + read-only class list.
renderNav('lecturer', [{ label: 'Lecturer' }]);

document.querySelectorAll('#tabs button').forEach(btn => btn.onclick = () => {
  document.querySelectorAll('#tabs button').forEach(b => {
    const on = b === btn;
    b.classList.toggle('border-indigo-600', on); b.classList.toggle('border-transparent', !on);
    b.classList.toggle('text-stone-900', on); b.classList.toggle('font-medium', on); b.classList.toggle('text-stone-500', !on);
  });
  document.querySelectorAll('[data-panel]').forEach(p => p.classList.toggle('hidden', p.dataset.panel !== btn.dataset.tab));
});

document.querySelector('[data-panel="quizzes"]').innerHTML = comingSoon('Generate homework & live quizzes (with QR code)', 'Phase 3 (+ Phase 2 endpoints)');
document.querySelector('[data-panel="insights"]').innerHTML = comingSoon('Which topics students struggle with most', 'Phase 3');
document.getElementById('upload-slot').innerHTML = comingSoon('Create a course and upload a class day (PDF)', 'Phase 3');

async function loadClasses(cid) {
  const lectures = await api(`/api/courses/${cid}/lectures`);
  document.getElementById('class-list').innerHTML = lectures.map(l => `
    <div class="flex items-center gap-4 rounded-xl bg-white border border-stone-200 p-4">
      <div class="w-10 h-10 rounded-lg bg-stone-100 grid place-items-center font-semibold text-stone-600">${l.number ?? ''}</div>
      <div class="flex-1 min-w-0"><div class="font-medium truncate">${escapeHtml(l.title)}</div>
        <div class="text-sm text-stone-500">${escapeHtml(l.date || '')}</div></div>
      ${statusBadge(l.status)}
      <a href="/lecture/${l.id}" target="_blank" class="text-sm text-indigo-600 hover:underline">Preview as student ↗</a>
    </div>`).join('') || '<p class="text-stone-500">No class days yet.</p>';
}

(async () => {
  const courses = await api('/api/courses');
  const sel = document.getElementById('course-select');
  sel.innerHTML = courses.map(c => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join('');
  sel.onchange = () => loadClasses(sel.value);
  if (courses.length) loadClasses(courses[0].id);
})();
