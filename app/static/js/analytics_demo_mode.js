/* BIKA: isolated, read-only demonstration data for the Data Analytics page.
   Synthetic values are generated from consistent per-run product classifications.
   Nothing is written to the server, Reports, or any production database. */
(() => {
  'use strict';
  const root = document.querySelector('[data-analytics-page]');
  if (!root) return;
  const STORAGE_KEY = 'bika.analytics.demo_mode.v1';
  const FIRST_KEY = 'bika.analytics.demo_first_load.v1';
  const demoOn = sessionStorage.getItem(STORAGE_KEY) === 'true';
  const officialFetch = window.fetch.bind(window);
  const pad = n => String(n).padStart(2,'0');
  const dateISO = d => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
  const shiftNames = ['Morning Shift', 'Afternoon Shift', 'Night Shift'];
  const shiftBases = [0.930, 0.878, 0.828]; // Morning > afternoon > night, but real aggregated counts determine each result.
  const classes = [
    ['too_dark', 'Too Dark', '#cf9458'],
    ['too_short', 'Too Short', '#8b77b2'],
    ['fractured', 'Fractured', '#c55e64'],
    ['bent_snack', 'Bent Snack', '#6686a2']
  ];
  const int = v => Math.round(v);
  const pct = (a,b) => b ? Math.round(a/b*1000)/10 : null;
  const clamp = (v,a,b) => Math.max(a, Math.min(b,v));
  const dayOffset = (date, n) => new Date(date.getFullYear(),date.getMonth(),date.getDate()+n);
  const ymd = value => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value||''))) return null;
    const p = String(value).split('-').map(Number);
    const result = new Date(p[0],p[1]-1,p[2]);
    return dateISO(result) === value ? result : null;
  };
  const fixed = (day, shift, run) => ((day * 191 + shift*61 + run*31 + 173) % 101) / 101;
  const withC = (counts, good, bad, d,s,r) => {
    const noise = fixed(d,s,r);
    const weight = [0.39+0.05*noise,0.27-0.025*noise,0.16+0.02*(1-noise),0.18-0.025*noise];
    const c = [Math.floor(bad*weight[0]),Math.floor(bad*weight[1]),Math.floor(bad*weight[2])];
    c.push(bad-c.reduce((a,b)=>a+b,0));
    for (let k=0;k<4;k++) counts[classes[k][0]]=(counts[classes[k][0]]||0)+c[k];
    return {normal:good, defect:bad, judged:good+bad, counts:Object.fromEntries(classes.map((item,i)=>[item[0],c[i]]))};
  };
  const emptyAgg = () => ({normal:0,defect:0,judged:0,inspections:0,classes:Object.fromEntries(classes.map(v=>[v[0],0]))});
  const add = (a,b) => {
    a.normal+=b.normal; a.defect+=b.defect; a.judged+=b.judged; a.inspections+=b.inspections||0;
    for(const key of Object.keys(a.classes)) a.classes[key]+=b.counts?.[key] ?? b.classes?.[key] ?? 0;
  };
  const cleanClass = a => Object.fromEntries(classes.map(c=>[c[0], a.classes[c[0]]]));
  const today = new Date(); today.setHours(0,0,0,0);
  const lastDate = dateISO(today);
  // A deterministic 75-day synthetic production history. Each entry is a run,
  // with a mode, shift, class counts, and a coherent pass/fail result.
  const runs = [];
  for (let daysAgo=74; daysAgo>=0; daysAgo--) {
    const current=dayOffset(today,-daysAgo);
    const key=dateISO(current), index=74-daysAgo;
    const weekend=current.getDay()===0||current.getDay()===6;
    // Every run belongs to one reproducible scenario (all based on daysAgo).
    // Phases: start-up calibration -> stable production -> afternoon lamp
    // drift -> maintenance recovery -> recent lighting incident -> recovery.
    // A single incident affects ALL shifts on the same days, with exposure
    // strongest on the night shift. This makes the daily line and 3x7 heatmap
    // tell the same physical story, never independently hand-picked rates.
    const startUp = daysAgo>=57 ? -0.030 : 0;
    const tunedLine = daysAgo>=34 && daysAgo<57 ? 0.026 : 0;
    const afternoonLampIssue = daysAgo>=25 && daysAgo<=31 ? 0.105 : 0;
    const recentLightingIssue = daysAgo>=5 && daysAgo<=8 ? 0.148 : 0;
    const recentRecovery = daysAgo<=4 ? (-0.060+(4-daysAgo)*0.025) : 0;
    const longTerm = index*0.00017;
    const weekdayEffect = current.getDay()===1 ? -0.012 : current.getDay()===3 ? 0.011 : current.getDay()===6 ? -0.017 : 0;
    const seasonal = 0.023*Math.sin(index*0.37 + 0.8) + 0.012*Math.cos(index*0.17 + 0.3);
    for(let s=0;s<3;s++) {
      const nRuns=weekend?2:3;
      for(let j=0;j<nRuns;j++) {
        const mode=['image','video','live'][(s+j+index)%3];
        const countBase=mode==='image'?62:mode==='video'?163:118;
        const total=int(countBase*(weekend?.74:1)*(0.91+0.18*fixed(index,s,j)));
        // Run-level production variation; more defects for the affected shifts.
        const affected = recentLightingIssue*(s===2?1.14:s===1?1.02:0.87)
          + afternoonLampIssue*(s===1?1.25:s===2?0.75:0.50);
        const shiftVariation=0.022*Math.sin(index*0.67+s*1.93)
          + 0.012*(fixed(index,s,j)-0.5);
        const rate=clamp(shiftBases[s]+weekdayEffect+seasonal+longTerm+
          startUp+tunedLine+recentRecovery-affected+shiftVariation,0.49,0.970);
        const good=int(total*rate), bad=total-good;
        const counts={}; const values=withC(counts,good,bad,index,s,j);
        runs.push({id:`DEMO-${key}-${s+1}-${j+1}`,date:key,shift:s,mode,good,bad,total,classes:counts,passing:good/total>=0.80, ...values});
      }
    }
  }
  const byRuns = arr => {
    const out=emptyAgg(); let passed=0;
    arr.forEach(r=>{add(out,{normal:r.normal,defect:r.defect,judged:r.judged,inspections:1,counts:r.classes}); if (r.normal/r.judged>=0.80) passed++;});
    out.passed=passed; return out;
  };
  const dailySeries = (arr, allMean) => {
    const byDay=new Map();
    arr.forEach(run => {
      if(!byDay.has(run.date)) byDay.set(run.date,emptyAgg());
      add(byDay.get(run.date),{normal:run.normal,defect:run.defect,judged:run.judged,inspections:1,counts:run.classes});
    });
    return [...byDay].sort(([a],[b])=>a.localeCompare(b)).map(([date,d])=>{
      const p=d.judged ? d.normal/d.judged : 0;
      const sigma=d.judged?3*Math.sqrt(allMean*(1-allMean)/d.judged):0;
      return {date,normal:d.normal,defect:d.defect,judged:d.judged,inspections:d.inspections,
        yield_rate:pct(d.normal,d.judged),defect_rate:pct(d.defect,d.judged),
        lcl:d.judged?pct(clamp(allMean-sigma,0,1)*100,100):null,
        ucl:d.judged?pct(clamp(allMean+sigma,0,1)*100,100):null};
    });
  };
  const roll = rows => {
    rows.forEach((r,i)=> {const w=rows.slice(Math.max(0,i-6),i+1);r.rolling_yield=pct(w.reduce((s,a)=>s+a.normal,0),w.reduce((s,a)=>s+a.judged,0));});return rows;
  };
  const getRange = url => {
    const u=new URL(url,location.href), query=u.searchParams;
    const key=query.get('range')||'30d';
    let lo=null,hi=null,label='All time';
    if(key==='custom') {lo=ymd(query.get('from'));hi=ymd(query.get('to'));label=lo&&hi?`${dateISO(lo)} – ${dateISO(hi)}`:'Custom range';}
    else if(key==='7d'||key==='30d'||key==='90d') {
      const days=key==='7d'?7:key==='30d'?30:90;
      lo=dayOffset(today,-(days-1));hi=today;label=`Last ${days} days`;
    } else if(key==='today') {lo=today;hi=today;label='Today';}
    return {key,lo,hi,label};
  };
  function makeResponse(url) {
    const filter=getRange(url);
    const left=filter.lo?dateISO(filter.lo):null,right=filter.hi?dateISO(filter.hi):null;
    const selected=runs.filter(r=>(!left||r.date>=left)&&(!right||r.date<=right));
    const total=byRuns(selected);
    const official=byRuns(selected.filter(r=>r.mode==='image'));
    const pbar=official.judged?official.normal/official.judged:0;
    const combined=roll(dailySeries(selected, total.judged?total.normal/total.judged:0));
    const officialTrend=roll(dailySeries(selected.filter(r=>r.mode==='image'),pbar));
    // Week is anchored at period end; never treat a missing shift-day as 0%.
    const heatEnd=filter.hi||today;
    const dates=Array.from({length:7},(_,i)=>dateISO(dayOffset(heatEnd,-6+i)));
    const heatRows=shiftNames.map((name,s)=> {
      const cellList=dates.map(date=> {
        const part=byRuns(selected.filter(r=>r.shift===s&&r.date===date));
        return {date,good_rate:pct(part.normal,part.judged),normal:part.normal,judged:part.judged,inspections:part.inspections};
      });
      const local=byRuns(selected.filter(r=>r.shift===s));
      return {name, good_rate:pct(local.normal,local.judged),inspections:local.inspections,judged:local.judged,cells:cellList};
    });
    const classRows=classes.map(c=>({key:c[0],name:c[1],color:c[2],count:total.classes[c[0]],percent:pct(total.classes[c[0]],total.defect)}));
    const a=official.normal+1,b=official.defect+1,mean=a/(a+b),sig=Math.sqrt(a*b/((a+b)**2*(a+b+1)));
    const posterior=official.judged?{mean:+(mean*100).toFixed(2),lower:+(clamp(mean-1.96*sig,0,1)*100).toFixed(2),upper:+(clamp(mean+1.96*sig,0,1)*100).toFixed(2),prior:'Beta(1, 1)',method:'Normal approximation to Beta posterior (95%)'}:null;
    const last=combined.length?combined[combined.length-1].defect_rate:10;
    const forecastAvailable=combined.length>=14;
    const forecast=forecastAvailable?{
      available:true,method:'Demo-only moving-average projection',
      qualification:'Synthetic illustration only; not a validated production forecast.',
      points:Array.from({length:7},(_,i)=>({date:dateISO(dayOffset(heatEnd,i+1)),predicted:+clamp(last-0.20*(i+1)+0.5*Math.sin(i),0,100).toFixed(1),lower:+clamp(last-2.8-0.22*i,0,100).toFixed(1),upper:+clamp(last+2.8+0.12*i,0,100).toFixed(1)}))
    }:{available:false,reason:'Demo forecasting needs at least 14 observed dates in the selected range.',required:{days:14,observations:300,span_days:20},progress:{days:combined.length,observations:total.judged,span_days:combined.length?combined.length-1:0}};
    const candidateDays=[...new Set(selected.filter(r=>r.mode==='image').map(r=>r.date))].slice(-6).reverse();
    const candidates=candidateDays.slice(0,Math.min(4,candidateDays.length)).map((d,i)=>({batch_id:`DEMO-REVIEW-${i+1}`,file_name:`demo_snack_sample_${i+1}.jpg`,date:d,source_type:'image',model_version:'DEMO v4',judged:22+i*5,reasons:[['Low classification confidence','Mask edge review','Class mismatch','Human verification suggested'][i]],reviewed:i===2?2:0,reviewable:false,preview_url:null}));
    const k={good_rate:pct(total.normal,total.judged),defect_rate:pct(total.defect,total.judged),meeting_standard_rate:pct(total.passed,total.inspections),meeting_standard_count:total.passed,inspections:total.inspections,judged:total.judged,normal:total.normal,defects:total.defect,target_good:85,pass_requirement:80,combined_basis:'estimated_tracks_and_judged',incomplete_live_sessions:0};
    const ok={
      filter:{range:filter.key,label:filter.label,from:left,to:right,time_basis:'Synthetic local demo calendar'},
      kpi:k,official_kpi:{...k,normal:official.normal,defects:official.defect,judged:official.judged,good_rate:pct(official.normal,official.judged)},
      trend:combined,combined_trend:combined,official_trend:officialTrend,provisional_trend:[],trend_truncated:false,
      spc:{pbar:pct(official.normal,official.judged),method:'3σ binomial p-chart; official image-only synthetic subset',has_data:!!official.judged},
      defects:classRows,
      shifts:shiftNames.map((name,s)=>{const z=byRuns(selected.filter(r=>r.shift===s));return {name,good_rate:pct(z.normal,z.judged),normal:z.normal,defect:z.defect,judged:z.judged,inspections:z.inspections};}),
      shift_heatmap:{dates,rows:heatRows,basis:'Synthetic per-run shift records. Morning, afternoon and night have different baselines; a recent shared lighting issue and progressive maintenance recovery explain the largest 7-day changes.'},
      bayesian:posterior,forecast,
      review:{candidates,recent_runs:candidates,total_candidates:candidates.length,status:{pending_runs:candidates.filter(r=>!r.reviewed).length,confirmed_objects:candidates.some(r=>r.reviewed)?1:0,false_positive_objects:0,corrected_objects:candidates.some(r=>r.reviewed)?1:0}},
      combined_note:'Demo only · synthetic Image, Video and Live counts. Never used for official reports.',
      note:'DEMO DATA ONLY · Synthetic example, not actual inspections or production performance.'
    };
    return {ok:true,analytics:ok};
  }

  // Intercept only the analytics GET response, and only on this screen when
  // demo mode is enabled. All other endpoints and methods are untouched.
  function isAnalyticsGet(input,init) {
    const method=String(init?.method||((input&&typeof input==='object')?input.method:'GET')||'GET').toUpperCase();
    if (method!=='GET')return false;
    const req=input instanceof Request?input.url:String(input);
    const target=new URL(root.dataset.dataUrl,location.href);
    const asked=new URL(req,location.href);
    return asked.origin===target.origin&&asked.pathname===target.pathname;
  }
  // Avoid mixing real provisional activity or recent reviews into an all-synthetic
  // preview. This endpoint is also read-only; do not call the real server in demo.
  function isProvisionalGet(input,init) {
    const method=String(init?.method||((input&&typeof input==='object')?input.method:'GET')||'GET').toUpperCase();
    if(method!=='GET')return false;
    const requested=input instanceof Request?input.url:String(input);
    const url=new URL(requested,location.href);
    return url.origin===location.origin && url.pathname==='/analytics/api/provisional';
  }
  window.fetch = function(input,init) {
    if(demoOn && (isAnalyticsGet(input,init) || isProvisionalGet(input,init))) {
      if(init?.signal?.aborted) return Promise.reject(new DOMException('The operation was aborted','AbortError'));
      const u=input instanceof Request?input.url:String(input);
      const payload=isProvisionalGet(input,init)?{ok:true,provisional:{daily:[],recent_runs:[]}}:makeResponse(u);
      return Promise.resolve(new Response(JSON.stringify(payload),{status:200,headers:{'Content-Type':'application/json'}}));
    }
    return officialFetch(input,init);
  };

  // UI: match the top-right Period button, including its own Iconsax 2-tone icon.
  // Keep the control outside the Period dropdown: it must never open the date menu.
  const css=document.createElement('style');
  css.textContent=`
  .analytics-page .bika-demo-toggle{
    display:inline-flex;align-items:center;justify-content:center;gap:8px;
    height:38px;min-height:38px;padding:0 14px;margin:0;border:1px solid transparent;
    border-radius:999px;background:var(--an-card,#fff);color:var(--an-ink,#292929);
    box-shadow:0 6px 22px rgba(20,20,20,.045),0 1px 4px rgba(20,20,20,.025);
    font-family:inherit;font-size:13px;font-weight:500;line-height:1.2;
    white-space:nowrap;cursor:pointer;flex:0 0 auto;
    transition:background .16s ease,color .16s ease,box-shadow .16s ease;
  }
  .analytics-page .bika-demo-toggle:hover{background:var(--an-brand-soft,#fbedf1)}
  .analytics-page .bika-demo-toggle:focus-visible{outline:2px solid var(--an-brand,#79223e);outline-offset:2px}
  .analytics-page .bika-demo-toggle.is-on{background:var(--an-card,#fff);color:var(--an-brand,#79223e);border-color:rgba(123,48,67,.12)}
  .analytics-page .bika-demo-toggle iconsax-icon{display:inline-flex;flex:0 0 auto;color:inherit}
  .analytics-page .bika-demo-toggle-label{font-weight:500;letter-spacing:0}
  .analytics-page .bika-demo-toggle-status{font-size:11px;font-weight:650;letter-spacing:0;color:inherit;opacity:.78}
  /* On desktop the Demo pill is anchored to Period, not to the title row. */
  .analytics-page .analytics-head{position:relative}
  .analytics-page .bika-demo-toggle{z-index:4;width:max-content;max-width:none;overflow:visible}
  .analytics-page .bika-demo-header-actions{gap:10px;min-width:0}
  .bika-demo-disclosure{display:flex;align-items:center;gap:8px;margin:10px 0 14px;
    padding:10px 13px;border:1px solid #d8aebc;border-radius:10px;
    background:#fff4f7;color:#71253e;font-size:12.5px;font-weight:600;line-height:1.4}
  .bika-demo-disclosure[hidden]{display:none!important}
  .bika-demo-heading-badge{font-size:10px;font-weight:700;line-height:1.2;
    font-family:inherit;letter-spacing:.06em;color:#93384f;border:1px solid #e6b4c0;
    border-radius:5px;padding:3px 5px;margin-left:7px}
  html[data-theme="dark"] .analytics-page .bika-demo-toggle{background:var(--an-card);color:var(--an-ink)}
  html[data-theme="dark"] .analytics-page .bika-demo-toggle.is-on{background:var(--an-card);color:var(--an-brand)}
  html[data-theme="dark"] .bika-demo-disclosure{background:#402532;color:#ffdbe5;border-color:#875269}
  @media(max-width:750px){
    .analytics-page .bika-demo-toggle{height:36px;min-height:36px;padding:0 11px;font-size:12px}
    .analytics-page .bika-demo-header-actions{gap:8px}
    .analytics-page .bika-demo-disclosure{font-size:11.5px}
  }
  `;
  document.head.appendChild(css);
  const heading=root.querySelector('.analytics-head');
  const button=document.createElement('button');button.type='button';button.className='bika-demo-toggle'+(demoOn?' is-on':'');
  button.setAttribute('aria-pressed',String(demoOn));
  button.setAttribute('aria-label',`Demo Data ${demoOn?'ON':'OFF'}. Switch between synthetic and saved analytics`);
  button.title=demoOn?'Return to real inspection records':'Preview synthetic analytics without changing saved data';
  button.innerHTML='<iconsax-icon name="chart-square" type="twotone" size="18" color="currentColor" aria-hidden="true"></iconsax-icon><span class="bika-demo-toggle-label">Demo Data</span><span class="bika-demo-toggle-status">'+(demoOn?'ON':'OFF')+'</span>';
  const filterWrap=root.querySelector('[data-range-wrap]');
  const periodParent=filterWrap?.parentElement || null;
  if(periodParent) periodParent.insertBefore(button,filterWrap);
  else if(heading) heading.appendChild(button);
  // v3.3: Period changes length AFTER saved-period restoration and whenever the
  // date dropdown is changed. Observe the actual rendered Period width and text.
  // A one-time right offset is not safe: a longer date range can cover Demo Data.
  const periodText=filterWrap?.querySelector('[data-range-label]');
  const rangeRow=document.createElement('div');
  rangeRow.className='bika-demo-range-row';
  let demoAlignmentQueued=false;
  function alignDemoWithPeriod(){
    if(!heading || !filterWrap || !button.isConnected) return;
    const wrapStyle=window.getComputedStyle(filterWrap);
    if(window.innerWidth < 1100){
      if(periodParent && rangeRow.parentElement === heading){
        if(button.parentElement !== periodParent) periodParent.insertBefore(button, filterWrap);
        if(filterWrap.parentElement !== periodParent) periodParent.appendChild(filterWrap);
        rangeRow.remove();
      } else if (periodParent && button.parentElement !== periodParent) {
        periodParent.insertBefore(button, filterWrap);
      }
      button.style.position='';button.style.top='';button.style.right='';button.style.left='';button.style.marginRight='10px';
      filterWrap.style.position='';filterWrap.style.top='';filterWrap.style.right='';
      rangeRow.style.position='';rangeRow.style.top='';rangeRow.style.right='';rangeRow.style.display='';rangeRow.style.alignItems='';rangeRow.style.gap='';
      return;
    }
    if(rangeRow.parentElement !== heading) heading.appendChild(rangeRow);
    rangeRow.style.position='absolute';
    rangeRow.style.top=wrapStyle.top || '0px';
    rangeRow.style.right=wrapStyle.right || '128px';
    rangeRow.style.display='flex';
    rangeRow.style.alignItems='center';
    rangeRow.style.gap='12px';
    rangeRow.style.zIndex='41';
    if(button.parentElement !== rangeRow) rangeRow.appendChild(button);
    if(filterWrap.parentElement !== rangeRow) rangeRow.appendChild(filterWrap);
    button.style.position='static';button.style.top='';button.style.right='';button.style.left='';button.style.marginRight='0';
    filterWrap.style.position='static';filterWrap.style.top='';filterWrap.style.right='';
  }
  function scheduleDemoAlign(){
    if(demoAlignmentQueued) return;
    demoAlignmentQueued=true;
    requestAnimationFrame(()=>requestAnimationFrame(()=>{
      demoAlignmentQueued=false;
      alignDemoWithPeriod();
    }));
  }
  scheduleDemoAlign();
  window.addEventListener('load',scheduleDemoAlign);
  window.addEventListener('resize',scheduleDemoAlign);
  document.fonts?.ready?.then(scheduleDemoAlign);
  if(typeof ResizeObserver!=='undefined' && filterWrap){
    const sizingObserver=new ResizeObserver(scheduleDemoAlign);
    sizingObserver.observe(filterWrap);
    sizingObserver.observe(button);
  }
  if(typeof MutationObserver!=='undefined' && periodText){
    const textObserver=new MutationObserver(scheduleDemoAlign);
    textObserver.observe(periodText,{childList:true,characterData:true,subtree:true});
  }
  root.querySelectorAll('[data-range-option],[data-apply-day],[data-apply-range]')
    .forEach(control=>control.addEventListener('click',scheduleDemoAlign));
  const note=document.createElement('div');note.className='bika-demo-disclosure';note.hidden=!demoOn;
  note.setAttribute('role','status');note.textContent='DEMO DATA · All charts and numbers on this page are synthetic examples. No records are saved or changed.';
  const status=root.querySelector('[data-status]');if(status)status.insertAdjacentElement('beforebegin',note);
  if(demoOn && status && typeof MutationObserver !== 'undefined') {
    const watcher=new MutationObserver(()=>{
      const was=status.textContent||'';
      const fixed=was.replace(/Updated from saved records/g,'Synthetic demo data · not saved').replace(/Loading real inspection records/g,'Loading synthetic demo data');
      if(fixed!==was)status.textContent=fixed;
    });
    watcher.observe(status,{childList:true,characterData:true,subtree:true});
  }
  if(demoOn){
    const h=root.querySelector('.analytics-page-heading h1');
    if(h){const badge=document.createElement('span');badge.className='bika-demo-heading-badge';badge.textContent='SAMPLE DATA';h.append(badge);}
    const tableHead=root.querySelector('[data-admin-review] .analytics-card-header p');
    if(tableHead) tableHead.textContent='Read-only sample review cases. No demo record can be opened or saved.';
  }
  button.addEventListener('click',()=>{
    const next=!demoOn;
    sessionStorage.setItem(STORAGE_KEY,String(next));
    if(next)sessionStorage.setItem(FIRST_KEY,'1');
    location.reload();
  });
  window.addEventListener('load',()=>{
    if(demoOn&&sessionStorage.getItem(FIRST_KEY)==='1'){
      sessionStorage.removeItem(FIRST_KEY);
      root.querySelector('[data-range-option="30d"]')?.click();
    }
  });
})();
