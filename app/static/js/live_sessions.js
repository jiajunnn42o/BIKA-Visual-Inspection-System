/* Read-only live session history, separate from judged InspectionBatch metrics. */
document.addEventListener('DOMContentLoaded', () => {
  const section = document.querySelector('[data-bika-live-history]');
  if (!section) return;
  const area = section.querySelector('[data-bika-live-history-list]');
  const url = section.dataset.url;
  const labels = {too_dark:'Too Dark', too_short:'Too Short', fractured:'Fractured', bent_snack:'Bent Snack', normal:'Normal'};
  function node(tag, cls, text) {
    const el=document.createElement(tag);
    if(cls) el.className=cls;
    if(text !== undefined) el.textContent=String(text);
    return el;
  }
  function formatDate(value) {
    if(!value) return 'Unknown date';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
  }
  function formatDuration(seconds) {
    if (!Number.isFinite(Number(seconds))) return '—';
    const n=Math.max(0, Math.round(Number(seconds)));
    return `${Math.floor(n/60)}m ${n%60}s`;
  }
  function render(sessions) {
    area.replaceChildren();
    if (!sessions.length) {
      area.append(node('div','bika-live-history-empty','No saved Live Inspection sessions yet. Start AI detection in Live Stream.'));
      return;
    }
    for(const s of sessions) {
      const row = node('div', 'bika-live-history-row');
      const intro = node('div');
      intro.append(node('div','bika-live-history-when', formatDate(s.started_at)));
      intro.append(node('div','bika-live-history-muted',`${String(s.status || '').replaceAll('_',' ')} · Provisional observations`));
      row.append(intro);
      for(const [val,label] of [[formatDuration(s.duration_seconds),'Duration'],[s.ai_frames ?? 0,'AI frames'],[s.event_count ?? 0,'Defect events']]) {
        const cell=node('div');
        cell.append(node('div','bika-live-history-metric',val));
        cell.append(node('div','bika-live-history-label',label));
        row.append(cell);
      }
      const classes=node('div','bika-live-history-classes');
      const entries=Object.entries(s.class_breakdown || {});
      classes.textContent=entries.length ? entries.map(([key,value])=>`${labels[key]||key}: ${value}`).join('  ·  ') : 'No saved defect events for this session';
      row.append(classes);
      if ((s.event_count || 0) > 0) {
        const details=node('details','bika-live-history-details');
        details.append(node('summary', '', `View saved defect observations (${s.event_count})`));
        const items=node('div','bika-live-history-events');
        for(const event of (s.recent_events || [])) {
          const line=node('div','bika-live-history-event');
          const confidence=Number(event.confidence);
          line.textContent = `${labels[event.label] || event.label || 'Defect'}  ·  ${Number.isFinite(confidence) ? (confidence*100).toFixed(1)+'%' : '—'}  ·  ${formatDate(event.detected_at)}`;
          items.append(line);
        }
        details.append(items);
        row.append(details);
      }
      area.append(row);
    }
  }
  fetch(url,{credentials:'same-origin',cache:'no-store'})
    .then(async r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json();})
    .then(json=>render(Array.isArray(json.sessions)?json.sessions:[]))
    .catch(()=>{area.replaceChildren(node('div','bika-live-history-empty','Could not load Live Session History. Please refresh.'));});
});
