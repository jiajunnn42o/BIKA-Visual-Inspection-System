/* BIKA Live Session Analytics: read-only and isolated from official Quality Trend. */
(() => {
  'use strict';
  const panel = document.querySelector('[data-bika-live-analytics]');
  const page = document.querySelector('[data-analytics-page]');
  if (!panel || !page) return;
  const $ = (selector) => panel.querySelector(selector);
  const fmt = (value) => new Intl.NumberFormat('en-US').format(Number(value) || 0);
  const sec = (value) => {
    const n = Math.max(0, Math.floor(Number(value) || 0));
    return `${Math.floor(n / 3600)}h ${Math.floor(n % 3600 / 60)}m ${n % 60}s`;
  };
  const colours = {'Fractured':'#E6464C', 'Too Dark':'#FF00AA', 'Too Short':'#48A1E2','Bent Snack':'#B85DDE'};
  const order = ['Fractured', 'Too Dark', 'Too Short', 'Bent Snack'];
  const set = (selector, value) => {const el=$(selector); if(el) el.textContent=value;};
  const period = () => {
    const select = page.querySelector('[data-range]');
    const key = select?.value || '30d';
    const params = new URLSearchParams({range:key});
    if(key==='custom') {
      const a = page.querySelector('[data-date-from]')?.value;
      const b = page.querySelector('[data-date-to]')?.value;
      if (!a || !b || a > b) return null;
      params.set('from', a); params.set('to', b);
    }
    return params;
  };
  let fetching = false;
  async function update() {
    if(fetching || document.hidden) return;
    const params = period();
    if(!params) return;
    fetching = true;
    try {
      const response = await fetch(`${panel.dataset.url}?${params}`, {credentials:'same-origin', cache:'no-store'});
      if(!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload=await response.json();
      if(!payload.ok || !payload.live) throw new Error('Invalid data');
      const live=payload.live;
      set('[data-live-sessions]',fmt(live.sessions));
      set('[data-live-observations]',fmt(live.defect_observations));
      set('[data-live-frames]',fmt(live.ai_frames));
      set('[data-live-uptime]',sec(live.duration_seconds));
      const total=Number(live.defect_observations)||0;
      set('[data-live-summary]', total
        ? `${fmt(total)} provisional defect observations · ${live.effective_fps ?? '—'} average effective FPS`
        : live.sessions ? 'No saved defect observations for the selected period.' : 'No saved Live sessions for the selected period.');
      const classes=live.classes || {};
      const breakdown=$('[data-live-classes]');
      if(breakdown) {
        breakdown.replaceChildren();
        for(const label of order) {
          const count=Number(classes[label]||0);
          const item=document.createElement('div'); item.className='bika-live-class';
          const top=document.createElement('div'); top.className='bika-live-class-top';
          const dot=document.createElement('i'); dot.className='bika-live-class-dot'; dot.style.backgroundColor=colours[label];
          const name=document.createElement('span');name.textContent=label;
          const value=document.createElement('strong');value.textContent=`${fmt(count)} · ${total?(100*count/total).toFixed(1):'0.0'}%`;
          top.append(dot,name,value);
          const bar=document.createElement('div');bar.className='bika-live-class-track';
          const fill=document.createElement('div');fill.className='bika-live-class-fill';
          fill.style.width=total ? `${Math.min(100,100*count/total)}%` : '0%';fill.style.backgroundColor=colours[label];
          bar.append(fill); item.append(top,bar);breakdown.append(item);
        }
      }
      const daily=$('[data-live-daily]');
      if(daily){
        daily.replaceChildren();
        const list=Array.isArray(live.daily)?live.daily:[];
        if(!list.length){const node=document.createElement('p');node.className='bika-live-note';node.textContent='No Live session activity in this period.';daily.append(node);}
        else{
          const max=Math.max(1,...list.map(x=>Number(x.sessions)||0));
          for(const x of list){
            const row=document.createElement('div');row.className='bika-live-day';
            const label=document.createElement('span');label.textContent=x.date;
            const track=document.createElement('div');track.className='bika-live-day-track';
            const fill=document.createElement('div');fill.className='bika-live-day-fill';fill.style.width=`${100*Number(x.sessions)/max}%`;track.append(fill);
            const val=document.createElement('strong');val.textContent=fmt(x.sessions);
            row.append(label,track,val); daily.append(row);
          }
        }
      }
    }catch(err){set('[data-live-summary]',`Could not load Live history (${err.message}).`);}
    finally{fetching=false;}
  }
  update();
  // Analytics restores its per-account period asynchronously; watch the period text.
  const select=page.querySelector('[data-range]');
  select?.addEventListener('change',()=>setTimeout(update,20));
  const label=page.querySelector('[data-range-label]');
  if(label) new MutationObserver(()=>setTimeout(update,100)).observe(label,{childList:true,subtree:true,characterData:true});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden) update();});
  const timer=setInterval(update,15000);
  window.addEventListener('pagehide',()=>clearInterval(timer),{once:true});
})();
