/* BIKA Analytics Header Harmony v5 – only aligns header controls. */
(() => {
  'use strict';
  const page = document.querySelector('[data-analytics-page]');
  if (!page) return;
  const header = page.querySelector('.analytics-head');
  const title = page.querySelector('.analytics-page-heading h1');
  const topbar = document.querySelector('.app-main .app-topbar');
  const theme = topbar?.querySelector('.app-theme-switch');
  if (!header || !title || !topbar || !theme) return;
  let queued = false;
  let previousOffset = 0;
  let resizeObserver = null;
  const isWide = () => window.innerWidth >= 1100;
  const rect = node => node?.getBoundingClientRect();
  const close = (a,b) => Math.abs(a-b) < 0.75;

  function align() {
    const row = header.querySelector('.bika-demo-range-row');
    if (!isWide() || !row || !row.contains(page.querySelector('[data-range-wrap]'))) {
      if (previousOffset !== 0) {
        topbar.style.translate = '';
        previousOffset = 0;
      }
      header.classList.remove('bika-header-stacked-v5');
      header.style.removeProperty('min-height');
      return;
    }
    const titleRect = rect(title);
    const headerRect = rect(header);
    let themeRect = rect(theme);
    const rowRect = rect(row);
    if (!titleRect?.height || !headerRect?.width || !themeRect?.height || !rowRect?.width) return;

    // Center the theme + bell topbar on the actual Data Analytics title line.
    // CSS individual translate is used instead of transform so a pre-existing
    // transform on the global topbar remains untouched.
    const titleCenter = titleRect.top + titleRect.height / 2;
    const themeCenter = themeRect.top + themeRect.height / 2;
    const offset = Math.max(-32, Math.min(32, previousOffset + titleCenter - themeCenter));
    if (!close(offset, previousOffset)) {
      previousOffset = offset;
      topbar.style.translate = `0px ${offset.toFixed(1)}px`;
      themeRect = rect(theme);
    }

    // Align Demo/Period right before Appearance, with a stable 14px gap.
    // Keep the user-selected date text fully visible; never overlap the title.
    const desiredRight = headerRect.right - themeRect.left + 14;
    const desiredTop = titleCenter - headerRect.top - rowRect.height / 2;
    row.style.setProperty('right', `${Math.round(desiredRight)}px`);
    row.style.setProperty('top', `${Math.round(desiredTop)}px`);
    row.style.removeProperty('left');

    const updatedRow = rect(row);
    const titleBlock = rect(page.querySelector('.analytics-page-heading'));
    if (updatedRow.left < titleBlock.right + 18) {
      // Narrow laptop: place the two pills below the heading, avoiding any
      // collision with the four-control top row's limited available width.
      header.classList.add('bika-header-stacked-v5');
      row.style.setProperty('left', '0px');
      row.style.setProperty('right', 'auto');
      row.style.setProperty('top', `${Math.ceil(titleBlock.bottom - headerRect.top + 14)}px`);
      const bottom = row.getBoundingClientRect().bottom - headerRect.top + 8;
      header.style.minHeight = `${Math.ceil(bottom)}px`;
    } else {
      header.classList.remove('bika-header-stacked-v5');
      header.style.removeProperty('min-height');
    }
  }

  function schedule() {
    if (queued) return;
    queued = true;
    // v4's own alignment runs in two animation frames; run afterwards.
    requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(() => {
      queued = false;
      align();
    })));
  }

  window.addEventListener('load', schedule);
  window.addEventListener('resize', schedule, { passive: true });
  document.fonts?.ready?.then(schedule);
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(schedule);
    [title,theme].forEach(node => resizeObserver.observe(node));
    const row = header.querySelector('.bika-demo-range-row');
    if (row) resizeObserver.observe(row);
  }
  if (typeof MutationObserver !== 'undefined') {
    const mo = new MutationObserver(() => {
      const row = header.querySelector('.bika-demo-range-row');
      if (row && resizeObserver) resizeObserver.observe(row);
      schedule();
    });
    mo.observe(header, { childList: true });
    const periodText = header.querySelector('[data-range-label]');
    if (periodText) new MutationObserver(schedule).observe(periodText, {childList:true, characterData:true, subtree:true});
  }
  page.querySelectorAll('[data-range-option],[data-apply-day],[data-apply-range]')
    .forEach(control => control.addEventListener('click', schedule));
  schedule();
})();
