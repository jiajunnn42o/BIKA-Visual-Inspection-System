/* BIKA global, persistent Live camera health warnings. Uses the existing bell DB. */
(() => {
  'use strict';
  const bell = document.querySelector('[data-notification-root]');
  if (!bell) return; // Only signed-in pages with the shared top bar
  const api = '/notifications/api/live-system-health';
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const seenKey = 'bika-live-health-alerts-seen-v1';
  let seen = new Set();
  try { seen = new Set(JSON.parse(sessionStorage.getItem(seenKey) || '[]')); } catch (_) {}
  let lastSignature = '';
  let busy = false;
  let audioContext = null;
  let audioPermitted = false;
  const saveSeen = () => { try { sessionStorage.setItem(seenKey, JSON.stringify([...seen].slice(-100))); } catch (_) {} };

  // User gesture unlocks the sound; browsers otherwise block automatic audio.
  function unlockAudio() {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      if (!audioContext) audioContext = new AudioCtx();
      audioContext.resume().then(() => { audioPermitted = audioContext.state === 'running'; }).catch(() => {});
    } catch (_) {}
  }
  window.addEventListener('pointerdown', unlockAudio, {passive:true});
  window.addEventListener('keydown', unlockAudio);
  function warningSound() {
    if (!audioPermitted || !audioContext || audioContext.state !== 'running') return;
    try {
      const t = audioContext.currentTime;
      [0, .23].forEach((offset) => {
        const oscillator = audioContext.createOscillator();
        const gain = audioContext.createGain();
        oscillator.type = 'sine'; oscillator.frequency.value = 700;
        oscillator.connect(gain); gain.connect(audioContext.destination);
        gain.gain.setValueAtTime(.0001, t + offset);
        gain.gain.exponentialRampToValueAtTime(.08, t + offset + .012);
        gain.gain.exponentialRampToValueAtTime(.0001, t + offset + .16);
        oscillator.start(t + offset); oscillator.stop(t + offset + .17);
      });
    } catch (_) {}
  }
  const layer = document.createElement('div');
  layer.className = 'bika-live-alert-toasts';
  layer.setAttribute('aria-live', 'polite');
  document.body.appendChild(layer);

  function element(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = String(text);
    return node;
  }
  async function acknowledge(id) {
    const response = await fetch(`/notifications/${encodeURIComponent(id)}/read`, {
      method:'POST', credentials:'same-origin',
      headers:{'X-CSRFToken':csrf,'X-Requested-With':'XMLHttpRequest','Accept':'application/json'}
    });
    if (!response.ok) throw new Error(`Acknowledgement failed (${response.status})`);
    window.dispatchEvent(new Event('bika:notifications-changed'));
    await poll();
  }
  function toast(alert) {
    const box = element('div', 'bika-live-alert-toast');
    box.setAttribute('role','status');
    const accent = element('span', 'bika-live-alert-dot','!');
    const copy = element('div','bika-live-alert-copy');
    copy.append(element('strong','',alert.title), element('p','',alert.message));
    const actions = element('div','bika-live-alert-actions');
    const link = element('a','','View Live Stream');
    link.href = '/live-inspection';
    const ack = element('button','','Mark as Read');
    ack.title = 'Mark this notification as read. Camera connection is not changed.';
    ack.type = 'button';
    ack.addEventListener('click', async () => {
      ack.disabled = true;
      try { await acknowledge(alert.id); box.remove(); }
      catch (err) { ack.disabled = false; ack.textContent = 'Try again'; }
    });
    actions.append(link,ack);
    if (!audioPermitted) {
      const enable = element('button','','Enable warning sound');
      enable.type = 'button';
      enable.addEventListener('click', () => {
        unlockAudio();
        setTimeout(() => { warningSound(); if (audioPermitted) enable.remove(); }, 80);
      });
      actions.append(enable);
    }
    copy.append(actions);
    const close = element('button','bika-live-alert-close','×');
    close.type = 'button'; close.setAttribute('aria-label','Close popup, keep notification');
    close.addEventListener('click',() => box.remove());
    box.append(accent,copy,close); layer.prepend(box);
    while (layer.children.length > 3) layer.lastElementChild?.remove();
    setTimeout(() => box.remove(), 12000);
    warningSound();
  }
  function renderLiveCard(alerts) {
    const card = document.querySelector('.lsi-alerts-card');
    if (!card) return;
    let panel = card.querySelector('[data-bika-persisted-live-alerts]');
    if (!panel) {
      panel = element('div','bika-live-persisted-alerts');
      panel.dataset.bikaPersistedLiveAlerts = '';
      card.appendChild(panel);
    }
    panel.replaceChildren();
    panel.hidden = alerts.length === 0;
    if (!alerts.length) return;
    panel.append(element('strong','',`${alerts.length} unacknowledged camera warning${alerts.length > 1?'s':''}`));
    alerts.slice(0, 3).forEach(alert => {
      const row = element('div','bika-live-persisted-row');
      const detail = element('div');
      detail.append(element('b','',alert.title), element('p','',alert.message));
      const ack = element('button','','Mark as Read');
    ack.title = 'Mark this notification as read. Camera connection is not changed.';
      ack.type = 'button';
      ack.addEventListener('click', async () => {
        ack.disabled = true;
        try { await acknowledge(alert.id); }
        catch (_) { ack.disabled = false; ack.textContent='Try again'; }
      });
      row.append(detail,ack); panel.append(row);
    });
  }
  async function poll() {
    if (busy || document.visibilityState === 'hidden') return;
    busy = true;
    try {
      const response = await fetch(api,{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'X-CSRFToken':csrf,'X-Requested-With':'XMLHttpRequest',Accept:'application/json'}});
      if (!response.ok) return;
      const body = await response.json();
      const alerts = Array.isArray(body.unread_alerts)?body.unread_alerts:[];
      const signature = alerts.map(a=>a.id).join(',');
      if (signature !== lastSignature) {
        lastSignature = signature;
        renderLiveCard(alerts);
        window.dispatchEvent(new Event('bika:notifications-changed'));
      }
      // Old unread alerts stay in the bell; only new alerts get a popup/sound.
      const newcomers = alerts.filter(a => !seen.has(a.id));
      newcomers.forEach(a => { seen.add(a.id); toast(a); });
      if (newcomers.length) saveSeen();
    } catch (err) { console.warn('[BIKA Live Alerts] health poll failed',err); }
    finally { busy = false; }
  }
  poll();
  setInterval(poll, 3500);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
  window.addEventListener('bika:notifications-changed', () => {
    // Allow bell-side 'Mark all as read' to update the Live persisted alerts.
    if (!busy) poll();
  });
})();
