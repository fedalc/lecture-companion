(() => {
  const openButton = document.getElementById('open-grade-calculator');
  if (!openButton || getCurrentUser()?.role !== 'student') return;

  const dialog = document.getElementById('grade-calculator');
  const form = document.getElementById('grade-plan');
  const courses = document.getElementById('grade-courses');
  const courseFeedback = document.getElementById('grade-course-feedback');
  const template = document.getElementById('grade-course-template');
  const addCourseButton = document.getElementById('add-grade-course');
  const examCfuInput = document.getElementById('upcoming-cfu');
  const targetInput = document.getElementById('target-average');
  const examGradeInput = document.getElementById('expected-grade');
  const minGrade = Number(examGradeInput.min);
  const maxGrade = Number(examGradeInput.max);
  const averageFormat = new Intl.NumberFormat(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
  const cfuFormat = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });

  openButton.hidden = false;
  openButton.addEventListener('click', () => dialog.showModal());
  document.getElementById('close-grade-calculator').addEventListener('click', () => dialog.close());

  function addCourse() {
    const row = template.content.firstElementChild.cloneNode(true);
    courses.append(row);
    return row;
  }

  addCourseButton.addEventListener('click', () => addCourse().querySelector('input').focus());
  courses.addEventListener('click', event => {
    const remove = event.target.closest('[data-remove-course]');
    if (!remove) return;
    const row = remove.closest('fieldset');
    const sibling = row.nextElementSibling || row.previousElementSibling;
    row.remove();
    (sibling?.querySelector('input') || addCourseButton).focus();
    updateResults();
  });

  function hasValue(input) {
    return input.value.trim() !== '' || input.validity.badInput;
  }

  function decimalHundredths(input) {
    const text = input.value.trim();
    if (!/^(?:\d+|\d*[.,]\d{1,2})$/.test(text)) return null;
    const value = Math.round(Number(text.replace(',', '.')) * 100);
    return Number.isSafeInteger(value) ? value : null;
  }

  function showResult(id, value, detail) {
    document.getElementById(id).textContent = value;
    document.getElementById(id + '-detail').textContent = detail;
  }

  function updateResults() {
    // Use hundredths of a CFU and of a grade to compare unrounded averages.
    let completedCfu = 0;
    let weightedPoints = 0;
    let excluded = 0;
    for (const row of courses.children) {
      const grade = row.querySelector('[name="grade"]');
      const cfu = row.querySelector('[name="cfu"]');
      const cfuUnits = decimalHundredths(cfu);
      const validGrade = Boolean(grade.value && grade.validity.valid);
      grade.setAttribute('aria-invalid', hasValue(grade) && !validGrade);
      cfu.setAttribute('aria-invalid', hasValue(cfu) && !cfuUnits);
      if (validGrade && cfuUnits) {
        completedCfu += cfuUnits;
        weightedPoints += grade.valueAsNumber * cfuUnits;
      } else if (hasValue(grade) || hasValue(cfu) || row.querySelector('[name="course"]').value.trim()) {
        excluded += 1;
      }
    }

    courseFeedback.hidden = excluded === 0;
    courseFeedback.textContent = excluded
      ? `${excluded} ${excluded === 1 ? 'course is' : 'courses are'} excluded until each has positive CFU and a whole grade from 18 to 30.`
      : '';
    showResult('current-grade-average',
      completedCfu ? averageFormat.format(weightedPoints / completedCfu) + '/30' : '—',
      completedCfu ? cfuFormat.format(completedCfu / 100) + ' completed CFU' : 'No completed CFU entered.');

    const examCfu = decimalHundredths(examCfuInput);
    examCfuInput.setAttribute('aria-invalid', hasValue(examCfuInput) && !examCfu);
    const target = decimalHundredths(targetInput);
    const targetKnown = target !== null && target >= minGrade * 100 && target <= maxGrade * 100;
    targetInput.setAttribute('aria-invalid', hasValue(targetInput) && !targetKnown);
    const examGradeKnown = Boolean(examGradeInput.value && examGradeInput.validity.valid);
    examGradeInput.setAttribute('aria-invalid', hasValue(examGradeInput) && !examGradeKnown);
    if (!examCfu) {
      showResult('needed-grade', '—', 'Enter positive exam CFU, with up to two decimal places.');
      showResult('projected-grade-average', '—', '');
      return;
    }

    const totalCfu = completedCfu + examCfu;
    const targetPoints = targetKnown ? target * totalCfu : null;
    if (!targetKnown) {
      showResult('needed-grade', '—', 'Enter a target average from 18 to 30, with up to two decimal places.');
    } else {
      const needed = Math.max(minGrade, Math.ceil((targetPoints - 100 * weightedPoints) / (100 * examCfu)));
      if (needed > maxGrade) {
        const bestAverage = (weightedPoints + maxGrade * examCfu) / totalCfu;
        showResult('needed-grade', 'Out of reach', `The best possible average is ${averageFormat.format(bestAverage)}/30 with a 30 on the exam.`);
      } else {
        showResult('needed-grade', `${needed}/30`, needed === minGrade ? 'A passing grade is enough.' : 'Minimum whole grade to reach your target.');
      }
    }

    if (!examGradeKnown) {
      showResult('projected-grade-average', '—', hasValue(examGradeInput)
        ? 'Enter a whole grade from 18 to 30.'
        : 'Enter an expected grade to see your new average.');
      return;
    }

    const projectedPoints = weightedPoints + examGradeInput.valueAsNumber * examCfu;
    const projection = averageFormat.format(projectedPoints / totalCfu);
    const targetMet = 100 * projectedPoints >= targetPoints;
    const detail = targetKnown
      ? targetMet ? 'Reaches your target.' : 'Below your target before rounding.'
      : `Across ${cfuFormat.format(totalCfu / 100)} CFU.`;
    showResult('projected-grade-average', projection + '/30', detail);
  }

  form.addEventListener('input', updateResults);
  form.addEventListener('submit', event => event.preventDefault());
  addCourse();
  updateResults();
})();
