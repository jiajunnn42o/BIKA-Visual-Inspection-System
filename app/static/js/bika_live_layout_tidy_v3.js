/* BIKA-LIVE-LAYOUT-TIDY-V3
   Pure UI: mirrors the existing unread-warning label into Current Alerts header.
   The original warning list, acknowledgement and DB notification logic are untouched.
*/
(() => {
  'use strict';
  document.documentElement.classList.add('bika-ui-tidy-v3');

  const card = document.querySelector('.lsi-page .lsi-alerts-card');
  if (!card) return;
  const heading = card.querySelector('.lsi-card-heading');
  if (!heading) return;
  let indicator = heading.querySelector('.bika-tidy-alert-count');
  if (!indicator) {
    indicator = document.createElement('span');
    indicator.className = 'bika-tidy-alert-count';
    indicator.setAttribute('aria-live', 'polite');
    indicator.hidden = true;
    heading.appendChild(indicator);
  }

  const sync = () => {
    const panel = card.querySelector('[data-bika-persisted-live-alerts]');
    const label = panel?.querySelector(':scope > strong');
    const hasAlert = Boolean(panel && !panel.hidden && panel.querySelector('.bika-live-persisted-row'));
    const nextText = hasAlert ? (label?.textContent?.trim() || 'Unacknowledged camera warning') : '';
    if (indicator.textContent !== nextText) indicator.textContent = nextText;
    if (indicator.hidden === hasAlert) indicator.hidden = !hasAlert;
  };
  new MutationObserver(sync).observe(card, {
    childList: true, subtree: true, characterData: true,
    attributes: true, attributeFilter: ['hidden']
  });
  sync();
})();
