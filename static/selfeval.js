// Self-evaluation page (Phase 2 owns this file).
(async () => {
  const cid = pathId();
  const course = await api(`/api/courses/${cid}`).catch(() => ({ name: 'Course' }));
  renderNav('student', [{ label: 'Courses', href: '/' }, { label: course.name, href: `/course/${cid}` }, { label: 'Self-evaluation' }]);
  document.getElementById('app').innerHTML = comingSoon('Self-evaluation test + which lectures to review', 'Phase 2');
})();
