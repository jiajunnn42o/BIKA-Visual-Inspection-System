/* BIKA_VIDEO_RETENTION_PHASE1_V1 — configuration and tabs only; no deletion */
(() => {
  'use strict';
  const root=document.querySelector('[data-about-system-page]');
  if(!root || !root.querySelector('[data-bika-retention-pane="video"]'))return;
  const tabs=[...root.querySelectorAll('[data-bika-retention-tab]')];
  const panes=[...root.querySelectorAll('[data-bika-retention-pane],[data-bika-retention-status-pane]')];
  const save=root.querySelector('[data-video-save]');
  const status=root.querySelector('[data-video-save-message]');
  const fields={
    full:{select:root.querySelector('[data-video-full-days]'),custom:root.querySelector('[data-video-full-custom]'),wrap:root.querySelector('[data-video-custom="full"]'),max:365},
    anomaly:{select:root.querySelector('[data-video-anomaly-days]'),custom:root.querySelector('[data-video-anomaly-custom]'),wrap:root.querySelector('[data-video-custom="anomaly"]'),max:365},
    limit:{select:root.querySelector('[data-video-limit]'),custom:root.querySelector('[data-video-limit-custom]'),wrap:root.querySelector('[data-video-custom="limit"]'),max:1000},
  };
  function activate(view){
    const selected=view==='video'?'video':'records';
    for(const pane of panes){
      const type=pane.hasAttribute('data-bika-retention-pane')?pane.dataset.bikaRetentionPane:pane.dataset.bikaRetentionStatusPane;
      pane.hidden=type!==selected;
    }
    for(const tab of tabs){const active=tab.dataset.bikaRetentionTab===selected;tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;}
  }
  tabs.forEach(tab=>{
    tab.addEventListener('click',()=>activate(tab.dataset.bikaRetentionTab));
    tab.addEventListener('keydown',event=>{
      if(!['ArrowLeft','ArrowRight'].includes(event.key))return;
      event.preventDefault();
      const other=tab.dataset.bikaRetentionTab==='records'?'video':'records';
      activate(other);
      tab.parentElement?.querySelector(`[data-bika-retention-tab="${other}"]`)?.focus();
    });
  });
  activate('records');
  Object.values(fields).forEach(field=>field.select?.addEventListener('change',()=>{field.wrap.hidden=field.select.value!=='custom';}));
  function getNumber(field,label){
    const raw=field.select.value==='custom'?field.custom?.value:field.select.value;
    if(!/^\d+$/.test(String(raw||'')))throw Error(`${label} must be a whole number.`);
    const result=Number(raw);
    if(!Number.isSafeInteger(result)||result<1||result>field.max)throw Error(`${label} must be between 1 and ${field.max}.`);
    return result;
  }
  function message(text,isError=false){if(status){status.textContent=text;status.dataset.error=String(isError);}}
  save?.addEventListener('click',async()=>{
    if(save.disabled)return;
    let values;
    try{values={full_days:getNumber(fields.full,'Full retention'),anomaly_days:getNumber(fields.anomaly,'Anomaly retention'),storage_limit_gb:getNumber(fields.limit,'Storage limit')};}
    catch(e){message(e.message,true);return;}
    save.disabled=true;
    const label=save.textContent;
    save.textContent='Saving…';message('Saving settings…');
    try{
      const response=await fetch(root.dataset.videoRetentionUrl,{
        method:'POST',credentials:'same-origin',cache:'no-store',
        headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('meta[name="csrf-token"]')?.content||''},
        body:JSON.stringify(values),
      });
      const result=await response.json().catch(()=>({}));
      if(!response.ok||!result.ok)throw Error(result.message||`Unable to save (${response.status}).`);
      const full=root.querySelector('[data-video-status-full]'),anomaly=root.querySelector('[data-video-status-anomaly]'),limit=root.querySelector('[data-video-status-limit]');
      if(full)full.textContent=`${values.full_days} ${values.full_days===1?'day':'days'}`;
      if(anomaly)anomaly.textContent=`${values.anomaly_days} ${values.anomaly_days===1?'day':'days'}`;
      if(limit)limit.textContent=`${values.storage_limit_gb} GB`;
      message(result.message||'Settings saved.');
    }catch(e){message(e.message,true);}
    finally{save.disabled=false;save.textContent=label;}
  });
})();
