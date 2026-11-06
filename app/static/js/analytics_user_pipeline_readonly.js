/* BIKA_USER_PIPELINE_READONLY_V2
   Read-only client. Does not infer 'no anomalies' from role-filtered responses.
   Requires a backend-supplied analytics.pipeline_log =
     {available:true, rows:[{batch_id,date,source_type,judged,reasons}], total:N}.
   No review form, mask URLs, or mutation endpoints are used.
*/
(() => {
  'use strict';
  const root=document.querySelector('[data-analytics-page]');
  if (!root || root.dataset.canReview === 'true') return;
  const tbody=root.querySelector('[data-user-pipeline-table]');
  const state=root.querySelector('[data-user-pipeline-state]');
  const count=root.querySelector('[data-user-pipeline-count]');
  const brief=root.querySelector('[data-user-pipeline-brief]');
  if (!tbody || !state || !brief) return;
  const escapeHtml=v=>String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=n=>new Intl.NumberFormat('en-US').format(Math.max(0,Number(n)||0));
  const note=(message,kind='info')=>{
    state.textContent=message;state.dataset.state=kind;
    brief.textContent=message;
  };
  const dateLocal=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const urlForRange=()=>{
    const range=root.querySelector('[data-range]')?.value || 'all';
    const params=new URLSearchParams({range:range==='today'?'custom':range});
    if(range==='today') {const today=dateLocal(new Date());params.set('from',today);params.set('to',today);}
    if(range==='custom') {
      const a=root.querySelector('[data-date-from]')?.value,b=root.querySelector('[data-date-to]')?.value;
      if(!a||!b||a>b)return null;
      params.set('from',a);params.set('to',b);
    }
    return `${root.dataset.dataUrl}?${params}`;
  };
  let controller=null, pending=0, lastKey='';
  async function refresh(){
    const url=urlForRange(); if(!url)return;
    if(controller)controller.abort();
    controller=new AbortController();
    note('Checking shared pipeline log access…');
    try {
      const response=await fetch(url,{credentials:'same-origin',signal:controller.signal});
      if(!response.ok) throw new Error('Analytics data could not be loaded.');
      const payload=await response.json();
      const log=payload?.analytics?.pipeline_log;
      // Critical: review.candidates returned to Admin is not an authorized User endpoint.
      // An absent log is an access gap, not proof of zero anomalies.
      if(!log || log.available !== true || !Array.isArray(log.rows)) {
        tbody.innerHTML='<tr><td colspan="5" class="analytics-table-empty">Shared pipeline log access is not enabled by the server yet.</td></tr>';
        if(count)count.textContent='—';
        note('Read-only pipeline data is not yet available for User accounts. The server API needs to enable it.','unavailable');
        return;
      }
      const rows=log.rows.slice(0,80);
      const total=Number.isFinite(Number(log.total))?Number(log.total):rows.length;
      if(count) count.textContent=fmt(total);
      if(!rows.length){
        tbody.innerHTML='<tr><td colspan="5" class="analytics-table-empty">No pipeline anomalies found in this selected period.</td></tr>';
        note('No flagged pipeline runs in this period.','empty');
        return;
      }
      tbody.innerHTML=rows.map(r=>{
        const reasons=Array.isArray(r.reasons)?r.reasons.map(String):r.reason?[String(r.reason)]:[];
        return `<tr><td><strong>${escapeHtml(r.batch_id||'—')}</strong></td><td>${escapeHtml(r.date||'—')}</td><td>${escapeHtml(r.source_type||'Image')}</td><td>${fmt(r.judged)}</td><td>${escapeHtml(reasons.join('; ')||'Flagged for review')}</td></tr>`;
      }).join('');
      note(`${fmt(total)} flagged pipeline run${total===1?'':'s'} in the selected period. Read-only for User accounts.`,'ready');
    }catch(error){
      if(error.name==='AbortError')return;
      tbody.innerHTML='<tr><td colspan="5" class="analytics-table-empty">The pipeline log could not be loaded.</td></tr>';
      note('Unable to check the pipeline log. Try refreshing the page.','error');
    }
  }
  const schedule=()=>{
    clearTimeout(pending);
    pending=setTimeout(()=>{
      const key=[root.querySelector('[data-range]')?.value,root.querySelector('[data-date-from]')?.value,root.querySelector('[data-date-to]')?.value,root.querySelector('[data-range-label]')?.textContent].join('|');
      if(lastKey!==key){lastKey=key;refresh();}
    },220);
  };
  const label=root.querySelector('[data-range-label]');
  if(label) new MutationObserver(schedule).observe(label,{childList:true,subtree:true,characterData:true});
  root.querySelectorAll('[data-range-option],[data-apply-day],[data-apply-range]').forEach(el=>el.addEventListener('click',()=>setTimeout(schedule,100)));
  schedule();
})();
