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
  const shiftBases = [0.888, 0.849, 0.807];
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
    const dip=(daysAgo>=9 && daysAgo<=15)?0.087:(daysAgo>=33 && daysAgo<=36)?0.04:0;
    const improvement=daysAgo<=8 ? (8-daysAgo)*0.003 : 0;
    for(let s=0;s<3;s++) {
      const nRuns=weekend?2:3;
      for(let j=0;j<nRuns;j++) {
        const mode=['image','video','live'][(s+j+index)%3];
        const countBase=mode==='image'?62:mode==='video'?163:118;
        const total=int(countBase*(weekend?.74:1)*(0.91+0.18*fixed(index,s,j)));
        const rate=clamp(shiftBases[s] - dip + improvement + 0.021*Math.sin(index*0.62+s*1.9+j*0.8),0.57,0.97);
        const good=int(total*rate), bad=total-good;
        const counts={}; const values=withC(counts,good,bad,index,s,j);
        runs.push({id:`DEMO-${key}-${s+1}-${j+1}`,date:key,shift:s,mode,good,bad,total,classes:counts,passing:rate>=0.80, ...values});
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
      shift_heatmap:{dates,rows:heatRows,basis:'Synthetic runs assigned by the simulated morning, afternoon, and night shifts.'},
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
  window.fetch = function(input,init) {
    if (demoOn&&isAnalyticsGet(input,init)) {
      if (init?.signal?.aborted) return Promise.reject(new DOMException('The operation was aborted','AbortError'));
      const u=input instanceof Request?input.url:String(input);
      return Promise.resolve(new Response(JSON.stringify(makeResponse(u)),{status:200,headers:{'Content-Type':'application/json'}}));
    }
    return officialFetch(input,init);
  };

  // UI: prominent, persistent disclosure. Switch changes only this page.
  const css=document.createElement('style');
  css.textContent=`
  .bika-demo-toggle {display:inline-flex;align-items:center;gap:9px;margin-top:8px;padding:8px 13px;border:1px solid #cdb1ba;border-radius:999px;background:#fff;color:#65243a;cursor:pointer;font-size:12px;font-weight:600;line-height:1.2;font-family:inherit;white-space:nowrap;box-shadow:0 2px 7px rgba(85,29,46,.06)}
  .bika-demo-toggle:hover,.bika-demo-toggle:focus-visible {border-color:#9e536a;outline-offset:2px}
  .bika-demo-toggle.is-on{background:#722a43;color:#fff;border-color:#722a43}
  .bika-demo-toggle-dot{width:9px;height:9px;border-radius:100%;background:#b7afb3;flex:none}
  .bika-demo-toggle.is-on .bika-demo-toggle-dot{background:#fff}
  .bika-demo-disclosure {display:flex;align-items:center;gap:8px;margin:10px 0 14px;padding:10px 13px;border:1px solid #d8aebc;border-radius:10px;background:#fff4f7;color:#71253e;font-size:12.5px;font-weight:600;line-height:1.4}
  .bika-demo-disclosure[hidden]{display:none!important}
  .bika-demo-heading-badge{font-size:10px;font-weight:700;line-height:1.2;font-family:inherit;letter-spacing:.06em;color:#93384f;border:1px solid #e6b4c0;border-radius:5px;padding:3px 5px;margin-left:7px}
  .bika-demo-note{color:#92465b;font-size:11px}
  @media (max-width:700px){.bika-demo-toggle{padding:7px 10px;font-size:11px}.bika-demo-disclosure{font-size:11.5px}}
  [data-theme="dark"] .bika-demo-toggle{background:#281c22;color:#efd5dc}
  [data-theme="dark"] .bika-demo-toggle.is-on{background:#873c53;color:#fff}
  [data-theme="dark"] .bika-demo-disclosure{background:#402532;color:#ffdbe5;border-color:#875269}
  `;
  document.head.appendChild(css);
  const heading=root.querySelector('.analytics-head');
  const button=document.createElement('button');button.type='button';button.className='bika-demo-toggle'+(demoOn?' is-on':'');
  button.setAttribute('aria-pressed',String(demoOn));
  button.title=demoOn?'Return to real inspection records':'Preview realistic synthetic analytics without changing saved data';
  button.innerHTML='<span class="bika-demo-toggle-dot" aria-hidden="true"></span><span>'+(demoOn?'Demo Data: ON':'Demo Data: OFF')+'</span>';
  if(heading){
    const title=heading.querySelector('.analytics-page-heading');
    (title||heading).appendChild(button);
  }
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
