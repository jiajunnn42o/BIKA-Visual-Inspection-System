/* BIKA Live defect breakdown: paint the existing ring with the current on-screen
 * defect-event counts. No change to AI models, events, or counting logic.
 */
(() => {
  'use strict';
  const page = document.querySelector('[data-live-stream-page]');
  if (!page) return;
  const ring = page.querySelector('[data-ai-ring]');
  const description = page.querySelector('[data-ai-distribution-text]');
  if (!ring || !description) return;

  // Match the established YOLO + v4 mask palette. Normal is not a defect event.
  const classes = [
    {label: 'Fractured', color: '#E6464C'},
    {label: 'Too Dark', color: '#FF00AA'},
    {label: 'Too Short', color: '#48A1E2'},
    {label: 'Bent Snack', color: '#B85DDE'}
  ];
  const empty = '#E5E5E5';
  let previous = null;

  function update() {
    const labelText = description.textContent || '';
    if (labelText === previous) return;
    previous = labelText;
    const counts = classes.map((item) => {
      const match = labelText.match(new RegExp(item.label + '\\s*:\\s*([0-9][0-9,]*)', 'i'));
      return match ? Number(match[1].replaceAll(',', '')) : 0;
    });
    const total = counts.reduce((sum, n) => sum + n, 0);
    if (!total) {
      ring.style.background = `conic-gradient(${empty} 0deg 360deg)`;
      ring.setAttribute('aria-label', 'No defect events yet');
      ring.title = 'No defect events yet';
      ring.classList.remove('bika-donut-has-data');
      return;
    }
    let angle = 0;
    const stops = [];
    for (let index = 0; index < classes.length; index++) {
      if (!counts[index]) continue;
      const next = angle + 360 * counts[index] / total;
      stops.push(`${classes[index].color} ${angle.toFixed(3)}deg ${next.toFixed(3)}deg`);
      angle = next;
    }
    const breakdown = classes.filter((_, i) => counts[i] > 0)
      .map((item) => `${item.label}: ${counts[classes.indexOf(item)]}`).join(', ');
    ring.style.background = `conic-gradient(${stops.join(', ')})`;
    ring.classList.add('bika-donut-has-data');
    ring.setAttribute('aria-label', `${total} provisional defect observations; ${breakdown}. Not verified unique biscuits.`);
    ring.title = breakdown + ' · Provisional observations';
  }

  new MutationObserver(update).observe(description, {
    childList: true, subtree: true, characterData: true
  });
  update();
})();
