/* BIKA-LIVE-UI-REFINEMENT-V2 — frontend presentation only.
   Original data-ai-distribution-text is kept as the source of truth; no
   inference, event insertion, camera health or model behaviour is changed.
*/
(() => {
  'use strict';
  const page = document.querySelector('[data-live-stream-page]');
  if (!page) return;

  const source = page.querySelector('[data-ai-distribution-text]');
  const card = page.querySelector('.lsi-alerts-card');
  const categories = [
    { name: 'Fractured', color: '#E6464C' },
    { name: 'Too Dark', color: '#FF00AA' },
    { name: 'Too Short', color: '#48A1E2' },
    { name: 'Bent Snack', color: '#B85DDE' }
  ];
  const create = (tag, cls, content) => {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (content !== undefined) el.textContent = String(content);
    return el;
  };

  if (source && !page.querySelector('.bika-defect-legend')) {
    source.classList.add('bika-defect-legend-source');
    source.setAttribute('aria-hidden', 'true');
    const wrap = create('div', 'bika-defect-legend');
    wrap.setAttribute('role', 'group');
    wrap.setAttribute('aria-label', 'Defect distribution');
    source.insertAdjacentElement('afterend', wrap);
    let lastText = null;
    function render() {
      const text = source.textContent || '';
      if (text === lastText) return;
      lastText = text;
      const counts = categories.map(c => {
        const matched = text.match(new RegExp(c.name + '\\s*:\\s*([\\d,]+)', 'i'));
        return matched ? Number(matched[1].replace(/,/g, '')) : 0;
      });
      const total = counts.reduce((sum, n) => sum + n, 0);
      wrap.replaceChildren();
      if (!total) {
        wrap.appendChild(create('p', 'bika-defect-legend-empty', 'No defect observations yet.'));
        return;
      }
      const grid = create('div', 'bika-defect-legend-grid');
      categories.forEach((cat, i) => {
        const amount = counts[i];
        const percent = amount / total * 100;
        const tile = create('div', 'bika-defect-legend-item');
        const row = create('div', 'bika-defect-legend-row');
        const dot = create('span', 'bika-defect-legend-dot');
        dot.style.backgroundColor = cat.color;
        row.append(dot, create('span', 'bika-defect-legend-name', cat.name),
                   create('span', 'bika-defect-legend-count', amount));
        const meter = create('div', 'bika-defect-meter');
        const fill = create('span', 'bika-defect-meter-fill');
        fill.style.backgroundColor = cat.color;
        fill.style.width = `${percent.toFixed(2)}%`;
        meter.appendChild(fill);
        tile.append(row, meter, create('span', 'bika-defect-legend-percent', `${percent.toFixed(1)}% of defects`));
        grid.appendChild(tile);
      });
      wrap.append(grid, create('div', 'bika-defect-legend-foot',
        'Provisional Track ID observations · unique products not verified'));
    }
    new MutationObserver(render).observe(source, {characterData:true,childList:true,subtree:true});
    render();
  }

  // Avoid contradictory "No active alerts" when an unacknowledged fault is
  // still listed below. Don't change the health service or notification state.
  if (card) {
    function syncAlerts() {
      const saved = card.querySelector('[data-bika-persisted-live-alerts]');
      const hasUnread = Boolean(saved && !saved.hidden && saved.querySelector('.bika-live-persisted-row'));
      card.classList.toggle('bika-has-unread-warning', hasUnread);
    }
    new MutationObserver(syncAlerts).observe(card, {
      childList:true,subtree:true,attributes:true,attributeFilter:['hidden']
    });
    syncAlerts();
  }
})();
