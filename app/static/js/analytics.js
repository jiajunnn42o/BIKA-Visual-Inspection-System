/* BIKA Data Analytics – real inspection data, zero external chart dependencies. */
(() => {
  'use strict';
  const root = document.querySelector('[data-analytics-page]');
  if (!root) return;
  const one = (s, parent = root) => parent.querySelector(s);
  const all = (s, parent = root) => Array.from(parent.querySelectorAll(s));
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);
  const pct = (v) => v === null || v === undefined ? '—' : `${num(v).toFixed(1)}%`;
  const fmt = (v) => new Intl.NumberFormat('en-US').format(num(v));
  const cap = (v, min, max) => Math.max(min, Math.min(max, v));
  const dateLabel = (s) => { const x = String(s || '').split('-'); return x.length === 3 ? `${x[1]}/${x[2]}` : String(s || ''); };
  // Use the browser's calendar date (not UTC toISOString(), which can be a day off in MY/SG).
  const localISO = (d) => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const todayISO = () => localISO(new Date());
  const fullDateLabel = (iso) => { const p=String(iso||'').split('-'); return p.length===3?`${p[1]}/${p[2]}/${p[0]}`:String(iso||''); };
  const periodLabel = (a,b=a) => `Period: ${fullDateLabel(a)}${a===b?'':` – ${fullDateLabel(b)}`}`;
  const presetPeriodLabel = (key) => {
    const end=new Date();
    const days=key==='7d'?6:key==='30d'?29:key==='90d'?89:0;
    const start=new Date(end.getFullYear(),end.getMonth(),end.getDate()-days);
    return key==='all'?'Period: All runs to date':periodLabel(localISO(start),localISO(end));
  };
  const empty = (heading, body) => `<div class="analytics-empty"><iconsax-icon name="chart" type="twotone" size="28" color="currentColor"></iconsax-icon><strong>${esc(heading)}</strong><span>${esc(body)}</span></div>`;
  let data = null;
  let chartMode = 'yield';
  let controller = null;
  let reviewRecord = null;
  let selectedObject = null;
  let reviewList = [];
  let selectedQueue = 'flagged';
  const admin = root.dataset.canReview === 'true';

  const status = (message, fail = false) => {
    const el = one('[data-status]'); if (!el) return;
    el.textContent = message; el.classList.toggle('is-error', fail);
  };

  async function load() {
    if (controller) controller.abort();
    controller = new AbortController();
    const sel = one('[data-range]');
    const params = new URLSearchParams({range: sel.value === 'today' ? 'custom' : sel.value});
    if (sel.value === 'today') {
      // Re-evaluate on each refresh so Today follows the local calendar date.
      const day = todayISO();
      params.set('from',day); params.set('to',day);
      one('[data-range-label]').textContent=periodLabel(day);
    }
    if (sel.value === 'custom') {
      const a = one('[data-date-from]').value, b = one('[data-date-to]').value;
      if (!a || !b || a > b) { status('Choose a valid custom date range.', true); return; }
      params.set('from', a); params.set('to', b);
    }
    status('Loading real inspection records…');
    try {
      const response = await fetch(`${root.dataset.dataUrl}?${params.toString()}`, {credentials:'same-origin', signal:controller.signal});
      if (!response.ok) throw new Error(`Server returned ${response.status}`);
      const payload = await response.json();
      if (!payload.ok || !payload.analytics) throw new Error('Invalid analytics response');
      data = payload.analytics;
      renderAll();
      const runs = data.kpi.inspections;
      status(`${data.filter.label} · ${fmt(runs)} inspection ${runs === 1 ? 'run' : 'runs'} · Updated from saved records`);
    } catch(e) {
      if (e.name === 'AbortError') return;
      status(`Could not load analytics: ${e.message}`, true);
    }
  }

  function renderAll() {
    const k = data.kpi;
    const map = {
      '[data-kpi-good]':pct(k.good_rate), '[data-kpi-defect]':pct(k.defect_rate),
      '[data-kpi-standard]':pct(k.meeting_standard_rate),
      '[data-kpi-good-foot]':`Target ${pct(k.target_good)}`,
      '[data-kpi-defect-foot]':`${fmt(k.defects)} defective observations`,
      '[data-kpi-standard-foot]':`${fmt(k.meeting_standard_count)} of ${fmt(k.inspections)} runs · Requirement ${pct(k.pass_requirement)}`,
      '[data-stat-runs]':fmt(k.inspections), '[data-stat-judged]':fmt(k.judged),
      '[data-stat-normal]':fmt(k.normal), '[data-stat-defective]':fmt(k.defects),
      '[data-footer-note]':data.note,
    };
    Object.entries(map).forEach(([selector, value]) => { const el = one(selector); if (el) el.textContent = value; });
    renderTrend(); renderShifts();
    if (admin) renderReviewQueue();
  }

  const svgLine = (vals, X, Y, klass, dashed=false) => {
    let paths=[], curr=[];
    vals.forEach((v, i) => {
      if (v === null || v === undefined || !Number.isFinite(Number(v))) {
        if (curr.length) {paths.push(curr); curr=[];} return;
      }
      curr.push(`${curr.length ? 'L' : 'M'}${X(i).toFixed(2)},${Y(num(v)).toFixed(2)}`);
    });
    if (curr.length) paths.push(curr);
    return paths.map(p => `<path d="${p.join(' ')}" class="${klass}" fill="none" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" ${dashed ? 'stroke-dasharray="6 5"' : ''}/>`).join('');
  };
  const grid = (width, height, left, right, top, bottom, yMax, count, labels) => {
    const innerW = width-left-right, innerH=height-top-bottom;
    const X = (i) => left+(count<2 ? innerW/2 : i*innerW/(count-1));
    const Y = (v) => top+innerH*(1-cap(v,0,yMax)/yMax);
    let pieces=[];
    for(let t=0;t<=5;t++) {
      const val=t*yMax/5;
      pieces.push(`<line class="gridline" x1="${left}" y1="${Y(val)}" x2="${width-right}" y2="${Y(val)}"/>`);
      pieces.push(`<text class="axis-label" x="${left-9}" y="${Y(val)+3}" text-anchor="end">${Math.round(val)}%</text>`);
    }
    const interval = Math.max(1,Math.ceil(count/7));
    for(let i=0;i<count;i++) if(i%interval===0||i===count-1) pieces.push(`<text class="axis-label" x="${X(i)}" y="${height-8}" text-anchor="middle">${esc(dateLabel(labels[i]))}</text>`);
    return { X, Y, markup:pieces.join('') };
  };

  function renderTrend() {
    const holder = one('[data-quality-chart]');
    const rows = data.trend || [];
    if (!rows.some(r => num(r.judged) > 0)) {
      holder.innerHTML = empty('No quality history yet','Run and save an image inspection to populate the trend.');
      one('[data-chart-legend]').innerHTML = '';
      return;
    }
    const modes = {
      yield:{name:'Good Snack Rate',field:'yield_rate',rolling:'rolling_yield',target:num(data.kpi.target_good),desc:'Good Snack Rate (%) · Judged Output · Target'},
      defect:{name:'Defect Rate',field:'defect_rate',rolling:null,target:100-num(data.kpi.target_good),desc:'Defect Rate (%) · Judged Output · Defect Target'},
      spc:{name:'Good Snack Rate (SPC)',field:'yield_rate',rolling:null,target:null,desc:'Good Snack Rate (%) · Judged Output · 3σ Control Limits'},
    };
    const mode = modes[chartMode];
    one('[data-trend-guide]').textContent=mode.desc;
    one('[data-trend-caption]').textContent = `${data.spc.method}. Output bars show judged observations (not unique objects across video frames). ${data.trend_truncated ? 'Latest 90 observed dates shown. ' : ''}No-data dates are not treated as 0% quality.`;
    // Two genuine y-axes: rates on the left, daily judged observations on the right.
    // The horizontal dashed line is a TARGET; it is never mislabelled as an LCL.
    const w=760,h=395,l=49,r=49,t=32,b=36;
    const iw=w-l-r,ih=h-t-b;
    const X=i=>l+iw*(i+.5)/rows.length;
    const Y=v=>t+ih*(1-cap(num(v),0,100)/100);
    const maximum=Math.max(1,...rows.map(row=>num(row.judged)));
    const nice = Math.pow(10,Math.floor(Math.log10(maximum)));
    const scale=Math.ceil(maximum/nice)*nice;
    const outputY=v=>t+ih*(1-num(v)/scale);
    let contents='';
    for(let tick=0;tick<=5;tick++) {
      const v=tick*20,y=Y(v);
      contents+=`<line class="gridline" x1="${l}" y1="${y}" x2="${w-r}" y2="${y}"/>`;
      contents+=`<text class="axis-label" x="${l-9}" y="${y+3}" text-anchor="end">${v}%</text>`;
    }
    for(let tick=0;tick<=4;tick++) {
      const count=Math.round(scale*tick/4);
      contents+=`<text class="axis-label" x="${w-r+9}" y="${t+ih*(1-tick/4)+3}" text-anchor="start">${fmt(count)}</text>`;
    }
    contents+=`<text class="chart-title-axis" x="${l}" y="13">${esc(mode.name)} (%)</text>`;
    contents+=`<text class="chart-title-axis" x="${w-r}" y="13" text-anchor="end">Judged Output</text>`;
    const barWidth=cap(iw/(rows.length*2.1),5,37);
    rows.forEach((point,i)=>{
      const val=num(point.judged);
      if(!val)return;
      const y=outputY(val);
      contents+=`<rect class="analytics-output-bar" x="${(X(i)-barWidth/2).toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${(t+ih-y).toFixed(1)}" rx="3"/>`;
    });
    const primary=rows.map(row=>row[mode.field]);
    const primaryClass=chartMode==='defect'?'series-rose':'series-good';
    if(mode.target!==null){
      contents+=`<line class="series-target" x1="${l}" x2="${w-r}" y1="${Y(mode.target)}" y2="${Y(mode.target)}" stroke-width="1.7" stroke-dasharray="6 5"/>`;
      contents+=`<text class="analytics-target-label" x="${w-r-3}" y="${Math.max(t+12,Y(mode.target)-6)}" text-anchor="end">Target ${pct(mode.target)}</text>`;
    }
    if(chartMode==='spc'){
      contents+=svgLine(rows.map(row=>row.ucl),X,Y,'series-limit',true);
      contents+=svgLine(rows.map(row=>row.lcl),X,Y,'series-limit',true);
    }
    if(mode.rolling) contents+=svgLine(rows.map(row=>row[mode.rolling]),X,Y,'series-green',true);
    contents+=svgLine(primary,X,Y,primaryClass);
    rows.forEach((point,i)=>{
      if(primary[i]===null||primary[i]===undefined)return;
      contents+=`<circle data-point="${i}" class="series-dots ${primaryClass}" cx="${X(i)}" cy="${Y(primary[i])}" r="3.6" tabindex="0" role="button" aria-label="${esc(point.date)} ${esc(mode.name)} ${esc(pct(primary[i]))}"/>`;
    });
    const labelInterval=Math.max(1,Math.ceil(rows.length/7));
    rows.forEach((point,i)=>{
      if(i%labelInterval===0||i===rows.length-1)contents+=`<text class="axis-label" x="${X(i)}" y="${h-14}" text-anchor="middle">${esc(dateLabel(point.date))}</text>`;
    });
    holder.innerHTML=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(mode.name)} with daily judged output volume">${contents}</svg><div class="analytics-chart-tooltip" data-chart-tooltip hidden></div>`;
    const legends=[[mode.name,chartMode==='defect'?'#c86168':'#7b3043'],['Judged Output','#bfcbd8']];
    if(mode.rolling)legends.push(['7-day rolling','#529f84']);
    if(mode.target!==null)legends.push([`Target ${pct(mode.target)}`,'#c78c95']);
    if(chartMode==='spc')legends.push(['UCL / LCL','#ba9c5b']);
    one('[data-chart-legend]').innerHTML=legends.map(([label,color])=>`<span><b style="background:${color}"></b>${esc(label)}</span>`).join('');
    holder.onmouseover=showPoint;
    holder.onfocusin=showPoint;
    holder.onmouseout=e=>{if(e.target?.hasAttribute?.('data-point'))one('[data-chart-tooltip]',holder)?.setAttribute('hidden','');};
    function showPoint(event){
      const point=event.target.closest?.('[data-point]');if(!point)return;
      const r=rows[Number(point.dataset.point)];if(!r)return;
      const tip=one('[data-chart-tooltip]',holder);
      tip.innerHTML=`<strong>${esc(r.date)}</strong><br>${esc(mode.name)}: <strong>${esc(pct(r[mode.field]))}</strong><br>Judged Output: ${fmt(r.judged)} · Defects: ${fmt(r.defect)}${chartMode==='spc'?`<br>3σ limits: ${pct(r.lcl)} – ${pct(r.ucl)}`:''}`;
      tip.removeAttribute('hidden');
    }
  }

  function renderShifts() {
    const place=one('[data-shift-chart]');
    if (!data.shifts.length) { place.innerHTML=empty('No shift information','Link inspection runs to users with a configured Shift to compare performance.');return; }
    place.innerHTML=data.shifts.map(row=>{
      const p=num(row.good_rate);
      return `<div class="analytics-shift-row"><div class="analytics-shift-top"><strong>${esc(row.name)}</strong><span>${pct(row.good_rate)} · ${fmt(row.inspections)} runs</span></div><div class="analytics-progress"><div class="analytics-progress-fill" style="width:${cap(p,0,100)}%"></div></div></div>`;
    }).join('');
  }

  function renderForecast() {
    const f=data.forecast,holder=one('[data-forecast-content]'),state=one('[data-forecast-state]');
    if(!f.available) {
      state.textContent='Insufficient history'; state.classList.remove('is-ready');
      holder.innerHTML=`<div class="analytics-forecast-status"><span class="analytics-forecast-status-icon"><iconsax-icon name="clock" type="twotone" size="24" color="currentColor"></iconsax-icon></span><div><strong>Collecting data for forecasting</strong><p>${esc(f.reason)}</p></div></div><div class="analytics-forecast-progress"><span>Observed days: <strong>${fmt(f.progress.days)} / ${fmt(f.required.days)}</strong></span><span>Judged objects: <strong>${fmt(f.progress.observations)} / ${fmt(f.required.observations)}</strong></span><span>Calendar span: <strong>${fmt(f.progress.span_days)} / ${fmt(f.required.span_days)}</strong></span></div>`;
      return;
    }
    state.textContent='Experimental estimate';state.classList.add('is-ready');
    const recent=data.trend.filter(r=>r.defect_rate!==null).slice(-12);
    const forecast=f.points||[];
    const labels=[...recent.map(r=>r.date),...forecast.map(r=>r.date)];
    const w=700,h=220,l=40,r=10,t=12,b=28;
    const allRates=[...recent.map(v=>num(v.defect_rate)),...forecast.map(v=>num(v.upper))];
    const upperBound= Math.max(10,Math.min(100,Math.ceil((Math.max(...allRates,0)+5)/10)*10));
    const gg=grid(w,h,l,r,t,b,upperBound,labels.length,labels);
    const lastHistoric=recent.length-1;
    const hdata=labels.map((_,i)=>i<recent.length?recent[i].defect_rate:null);
    const future=labels.map((_,i)=>i===lastHistoric?recent[lastHistoric].defect_rate:i>=recent.length?forecast[i-recent.length].predicted:null);
    let polygon='';
    if(forecast.length){
      const upper=forecast.map((p,i)=>`${gg.X(recent.length+i)},${gg.Y(p.upper)}`);
      const lower=forecast.map((p,i)=>`${gg.X(recent.length+i)},${gg.Y(p.lower)}`).reverse();
      if(lastHistoric>=0)polygon=`<polygon points="${gg.X(lastHistoric)},${gg.Y(recent[lastHistoric].defect_rate)} ${upper.join(' ')} ${lower.join(' ')}" fill="#a85b6f" fill-opacity=".14" stroke="none"/>`;
    }
    const transition=lastHistoric>=0?`<line x1="${gg.X(lastHistoric)}" x2="${gg.X(lastHistoric)}" y1="${t}" y2="${h-b}" class="gridline" stroke-dasharray="4 4"/>`:'';
    holder.innerHTML=`<div class="analytics-svg-chart" style="height:210px"><svg viewBox="0 0 ${w} ${h}" aria-label="Historical defect rate and experimental seven-day forecast" role="img">${gg.markup}${polygon}${transition}${svgLine(hdata,gg.X,gg.Y,'series-good')}${svgLine(future,gg.X,gg.Y,'series-rose',true)}</svg></div><div class="analytics-chart-legend"><span><b style="background:#7b3043"></b>Observed</span><span><b style="background:#c86168"></b>Regression forecast</span><span><b style="background:#e1bdc8"></b>Heuristic uncertainty</span></div><p class="analytics-forecast-caption">${esc(f.qualification)}</p>`;
  }

  function renderDefects() {
    const holder=one('[data-defects]');const classes=data.defects||[];
    const total=classes.reduce((s,r)=>s+num(r.count),0);
    if(total===0) {holder.innerHTML=empty('No defect-class counts available','Defect class distribution appears when stored inspection metadata includes class counts.');return;}
    let cursor=0;
    const stops=[];
    classes.forEach(row=> {const percent=num(row.count)/total*100;if(percent>0){stops.push(`${row.color} ${cursor.toFixed(3)}% ${(cursor+percent).toFixed(3)}%`);cursor+=percent;}});
    holder.innerHTML=`<div class="analytics-donut-row"><div class="analytics-donut" style="background:conic-gradient(${stops.join(',')})"><div class="analytics-donut-center"><strong>${fmt(total)}</strong><small>Defects</small></div></div><div class="analytics-donut-desc">Detected defects<br>across saved inspection runs.</div></div>${classes.map(row=>`<div class="analytics-defect-row"><span class="analytics-defect-color" style="background:${row.color}"></span><span>${esc(row.name)}</span><strong>${fmt(row.count)}</strong><small>${(num(row.count)*100/total).toFixed(1)}%</small></div>`).join('')}`;
  }

  function renderBayesian() {
    const holder=one('[data-bayesian]'); const b=data.bayesian;
    if (!b) {holder.innerHTML=empty('Awaiting observations','The Beta–Binomial estimate becomes available after judged snack observations are saved.');return;}
    const low=cap(num(b.lower),0,100),high=cap(num(b.upper),0,100),mid=cap(num(b.mean),0,100);
    holder.innerHTML=`<div class="analytics-bayes-metric"><small>Posterior mean · Good Snack Rate</small><strong>${pct(mid)}</strong></div><div class="analytics-bayes-body"><div class="analytics-bayes-track"><div class="analytics-bayes-range" style="left:${low}%;width:${high-low}%"></div><div class="analytics-bayes-pin" style="left:${mid}%"></div></div><div class="analytics-bayes-scale"><span>0%</span><strong>Approx. 95% credible interval: ${pct(low)} – ${pct(high)}</strong><span>100%</span></div><p class="analytics-bayes-explain">${esc(b.prior)} prior updated with ${fmt(data.kpi.normal)} normal and ${fmt(data.kpi.defects)} defective observations. ${esc(b.method)}. This is uncertainty estimation, not future prediction.</p></div>`;
  }

  function renderReviewQueue() {
    const review=data.review || {candidates:[],recent_runs:[],total_candidates:0};
    const count=one('[data-review-count]'); if(count) count.textContent=fmt(review.total_candidates);
    const stats=review.status||{};
    const statusValues={'[data-review-pending]':stats.pending_runs,'[data-review-confirmed]':stats.confirmed_objects,'[data-review-false]':stats.false_positive_objects,'[data-review-corrected]':stats.corrected_objects};
    Object.entries(statusValues).forEach(([selector,value])=>{const el=one(selector);if(el)el.textContent=value===undefined?'—':fmt(value);});
    const query=(one('[data-review-search]')?.value||'').trim().toLowerCase();
    const mode=one('[data-review-mode]')?.value||'flagged';
    selectedQueue=mode;
    reviewList=(mode==='recent'?review.recent_runs:review.candidates)||[];
    const rows=reviewList.filter(row=>!query||`${row.batch_id} ${row.file_name} ${row.reasons.join(' ')}`.toLowerCase().includes(query));
    const tbody=one('[data-review-table]');
    if(!rows.length) {
      tbody.innerHTML=`<tr><td colspan="5" class="analytics-table-empty">${query?'No runs match your search.':mode==='flagged'?'No flagged inspection runs in this period.':'No stored image inspections available in this period.'}</td></tr>`;
    } else {
      tbody.innerHTML=rows.map(row=>{
        const reason=row.reasons?.length?row.reasons[0]:'Routine review';
        return `<tr><td><div class="analytics-review-source">${row.preview_url?`<img src="${esc(row.preview_url)}" class="analytics-review-thumb" alt="Saved inspection thumbnail" loading="lazy">`:'<span class="analytics-review-thumbnail-empty">—</span>'}<div><div class="analytics-review-primary" title="${esc(row.batch_id)}">${esc(row.batch_id)}</div><div class="analytics-review-secondary" title="${esc(row.file_name)}">${esc(row.file_name)}</div><div class="analytics-review-secondary">${esc(row.date)}</div></div></div></td><td>${fmt(row.judged)}</td><td><span class="analytics-reason" title="${esc(row.reasons.join('; '))}">${esc(reason)}</span></td><td><span class="analytics-review-badge">${fmt(row.reviewed)} reviewed</span></td><td><button type="button" class="analytics-view-button" data-open-review="${esc(row.batch_id)}" ${row.reviewable?'':'disabled title="Saved image results required"'}>Review Masks ↗</button></td></tr>`;
      }).join('');
    }
    const total=one('[data-review-pagination]');if(total)total.textContent=`${fmt(rows.length)} shown${review.total_candidates>40 && mode==='flagged'?' · latest 40 flagged runs':''}`;
  }

  async function openReview(batchId) {
    const modal=document.querySelector('[data-mask-modal]');if(!modal)return;
    modal.removeAttribute('hidden'); document.body.style.overflow='hidden';
    one('[data-modal-title]',modal).textContent=batchId;
    one('[data-modal-subtitle]',modal).textContent='Loading saved image and masks…';
    one('[data-mask-stage]',modal).innerHTML='<div class="analytics-mask-loading">Loading original image…</div>';
    one('[data-object-list]',modal).innerHTML='';
    one('[data-object-detail]',modal).innerHTML='<p>Select a mask to view details.</p>';
    one('[data-save-review]',modal).disabled=true;
    one('[data-save-message]',modal).textContent='';
    selectedObject=null;reviewRecord=null;
    try{
      const response=await fetch(`${root.dataset.reviewUrlRoot}${encodeURIComponent(batchId)}`,{credentials:'same-origin'});
      const payload=await response.json();
      if(!response.ok||!payload.ok)throw new Error(payload.message||`HTTP ${response.status}`);
      reviewRecord=payload.detail;
      one('[data-modal-title]',modal).textContent=reviewRecord.batch_id;
      one('[data-modal-subtitle]',modal).textContent=`${reviewRecord.file_name} · Model ${reviewRecord.model_version}`;
      one('[data-object-count]',modal).textContent=`${reviewRecord.objects.length} objects`;
      const stage=one('[data-mask-stage]',modal);
      stage.innerHTML='<div class="analytics-mask-loading">Preparing image…</div>';
      const img=new Image();img.alt=`Inspection source image for ${batchId}`;
      img.onload=()=>{
        if(!reviewRecord || reviewRecord.batch_id!==batchId)return;
        const w=num(reviewRecord.image.width)||img.naturalWidth,h=num(reviewRecord.image.height)||img.naturalHeight;
        if(!w||!h){stage.textContent='Unable to read source image dimensions.';return;}
        // Inner wrapper gives the image and polygon SVG exactly the same box.
        const wrap=document.createElement('div');wrap.style.cssText='position:relative;display:inline-block;max-width:100%;line-height:0;';
        img.style.cssText='width:auto;height:auto;max-width:100%;max-height:540px;object-fit:contain;display:block;';
        wrap.append(img);
        const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
        svg.setAttribute('class','analytics-mask-svg');svg.setAttribute('viewBox',`0 0 ${w} ${h}`);
        svg.setAttribute('preserveAspectRatio','none');svg.setAttribute('aria-label','Select a mask on the image');
        reviewRecord.objects.forEach((obj,i)=>{
          (obj.polygons||[]).slice(0,40).forEach(poly=>{
            if(!Array.isArray(poly)||poly.length<3)return;
            const pairs=poly.slice(0,4000).filter(p=>Array.isArray(p)&&p.length>=2&&Number.isFinite(Number(p[0]))&&Number.isFinite(Number(p[1]))).map(p=>`${cap(num(p[0]),0,w).toFixed(1)},${cap(num(p[1]),0,h).toFixed(1)}`);
            if(pairs.length<3)return;
            const el=document.createElementNS('http://www.w3.org/2000/svg','polygon');
            el.setAttribute('points',pairs.join(' '));
            el.setAttribute('fill',/^#[0-9a-f]{6}$/i.test(obj.colour)?obj.colour:'#741f2e');
            el.dataset.objectIndex=String(i); el.setAttribute('tabindex','0');
            el.addEventListener('click',()=>selectObject(i));
            el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectObject(i);}});
            const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=`${obj.object_id}: ${obj.class_name}`;el.append(title);
            svg.append(el);
          });
        });
        wrap.append(svg);stage.replaceChildren(wrap);
      };
      img.onerror=()=>{stage.innerHTML='<div class="analytics-mask-loading">The original image could not be loaded.</div>';};
      img.src=reviewRecord.image_url;
      const list=one('[data-object-list]',modal);
      if(!reviewRecord.objects.length){list.innerHTML='<div class="analytics-empty">No saved detection objects.</div>';return;}
      list.innerHTML=reviewRecord.objects.map((obj,i)=>`<button type="button" class="analytics-object-choice" data-object-index="${i}"><span class="analytics-object-dot" style="background:${/^#[0-9a-f]{6}$/i.test(obj.colour)?obj.colour:'#741f2e'}"></span><span><strong>${esc(obj.object_id)} · ${esc(obj.class_name)}</strong><small>${obj.in_safe_zone?'Judged':'Edge / Not judged'} · ${obj.confidence==null?'—':pct(num(obj.confidence)*100)}${reviewRecord.reviews[obj.object_id]?' · Reviewed':''}</small></span></button>`).join('');
      selectObject(0);
    }catch(e){one('[data-mask-stage]',modal).innerHTML=`<div class="analytics-mask-loading">${esc(e.message)}</div>`;one('[data-modal-subtitle]',modal).textContent='Review unavailable';}
  }

  function selectObject(index) {
    if(!reviewRecord)return;
    selectedObject=reviewRecord.objects[index];if(!selectedObject)return;
    const modal=document.querySelector('[data-mask-modal]');
    all('[data-object-index]',modal).forEach(el=>el.classList.toggle('is-selected',Number(el.dataset.objectIndex)===index));
    all('polygon[data-object-index]',modal).forEach(el=>el.classList.toggle('is-selected',Number(el.dataset.objectIndex)===index));
    const old=reviewRecord.reviews[selectedObject.object_id];
    one('[data-object-detail]',modal).innerHTML=`<strong>${esc(selectedObject.object_id)}</strong><br>Prediction: <strong>${esc(selectedObject.class_name)}</strong> · ${esc(selectedObject.decision)}<br>Classification confidence: <strong>${selectedObject.confidence==null?'—':pct(num(selectedObject.confidence)*100)}</strong><br>Detection confidence: <strong>${selectedObject.detection_confidence==null?'—':pct(num(selectedObject.detection_confidence)*100)}</strong><br>Segmentation polygons: ${(selectedObject.polygons||[]).length}${old?`<br>Last review: <strong>${esc(old.decision)}</strong> by ${esc(old.reviewer_name||'Reviewer')}`:''}`;
    one('[data-decision]',modal).value=old?.decision||'correct';
    one('[data-review-note]',modal).value=old?.note||'';
    one('[data-save-review]',modal).disabled=false;
    const message=one('[data-save-message]',modal); message.textContent='';message.classList.remove('is-error');
  }

  async function saveReview() {
    if(!reviewRecord||!selectedObject)return;
    const modal=document.querySelector('[data-mask-modal]');
    const button=one('[data-save-review]',modal),message=one('[data-save-message]',modal);
    const token=document.querySelector('meta[name="csrf-token"]')?.content||'';
    button.disabled=true;message.classList.remove('is-error');message.textContent='Saving human review…';
    try {
      const response=await fetch(`${root.dataset.reviewUrlRoot}${encodeURIComponent(reviewRecord.batch_id)}`,{
        method:'POST',credentials:'same-origin',
        headers:{'Content-Type':'application/json','X-CSRFToken':token},
        body:JSON.stringify({object_id:selectedObject.object_id,decision:one('[data-decision]',modal).value,note:one('[data-review-note]',modal).value})
      });
      const payload=await response.json();
      if(!response.ok||!payload.ok)throw new Error(payload.message||`HTTP ${response.status}`);
      reviewRecord.reviews[selectedObject.object_id]=payload.review;
      message.textContent='Review saved. Original AI prediction remains unchanged.';
      const idx=reviewRecord.objects.findIndex(o=>o.object_id===selectedObject.object_id);selectObject(idx);
      message.textContent='Review saved. Original AI prediction remains unchanged.';
      // Refresh backend-derived review counts without closing the modal.
      await load();
    }catch(e){message.classList.add('is-error');message.textContent=`Unable to save: ${e.message}`;}
    finally{button.disabled=false;}
  }

  function closeModal() {
    const modal=document.querySelector('[data-mask-modal]');if(!modal)return;
    modal.setAttribute('hidden','');document.body.style.overflow='';reviewRecord=null;selectedObject=null;
  }
  // Dashboard-matched date pill/dropdown. Native select remains as an internal value holder for load().
  const dateButton=one('[data-range-button]');
  const dateMenu=one('[data-range-menu]');
  const rangeSelect=one('[data-range]');
  const dateWrap=one('[data-range-wrap]');
  const dateLabels={'today':'Today','7d':'Last 7 days','30d':'Last 30 days','90d':'Last 90 days','all':'All runs to date','custom':'Custom range'};
  // Initialize the selected period before the first API request.
  one('[data-range-label]').textContent = periodLabel(todayISO());
  function closeDate(){dateMenu.hidden=true;dateButton.setAttribute('aria-expanded','false');}
  dateButton.addEventListener('click',()=>{
    const next=dateMenu.hidden;
    dateMenu.hidden=!next;
    dateButton.setAttribute('aria-expanded',String(next));
  });
  all('[data-range-option]').forEach(button=>button.addEventListener('click',()=>{
    rangeSelect.value=button.dataset.rangeOption;
    one('[data-range-label]').textContent=presetPeriodLabel(rangeSelect.value);
    all('[data-range-option]').forEach(item=>item.classList.toggle('is-active',item===button));
    closeDate();load();
  }));
  // Select a single historical day without requiring two custom-range fields.
  const singleDayInput=one('[data-date-single]');
  singleDayInput.value=todayISO();
  one('[data-apply-day]').addEventListener('click',()=>{
    const day=singleDayInput.value;
    if(!day){status('Choose a date.',true);return;}
    one('[data-date-from]').value=day;
    one('[data-date-to]').value=day;
    rangeSelect.value='custom';
    one('[data-range-label]').textContent=periodLabel(day);
    all('[data-range-option]').forEach(item=>item.classList.toggle('is-active',item.dataset.rangeOption==='today'&&day===todayISO()));
    closeDate();load();
  });
  one('[data-apply-range]').addEventListener('click',()=>{
    const from=one('[data-date-from]').value,to=one('[data-date-to]').value;
    if(!from||!to||from>to){status('Choose a valid custom date range.',true);return;}
    rangeSelect.value='custom';
    one('[data-range-label]').textContent=periodLabel(from,to);
    if(from===to)singleDayInput.value=from;
    all('[data-range-option]').forEach(item=>item.classList.remove('is-active'));
    closeDate();load();
  });
  document.addEventListener('click',event=>{if(!dateWrap.contains(event.target))closeDate();});
  document.addEventListener('keydown',event=>{if(event.key==='Escape')closeDate();});
  function alignDateWithDashboardTopbar(){
    if(window.innerWidth<1100){dateWrap.style.top='';dateWrap.style.right='';return;}
    const toggle=document.querySelector('.app-topbar .app-theme-switch');
    const header=one('.analytics-head');
    if(!toggle||!header)return;
    const rect=toggle.getBoundingClientRect(),parent=header.getBoundingClientRect();
    if(!rect.width||!rect.height)return;
    // Match the real theme-toggle vertical centre; 14px is BIKA's topbar control gap.
    dateWrap.style.top=`${Math.round(rect.top+rect.height/2-parent.top-dateButton.offsetHeight/2)}px`;
    dateWrap.style.right=`${Math.round(parent.right-rect.left+14)}px`;
  }
  requestAnimationFrame(alignDateWithDashboardTopbar);
  window.addEventListener('load',alignDateWithDashboardTopbar);
  window.addEventListener('resize',alignDateWithDashboardTopbar);
  document.fonts?.ready?.then(alignDateWithDashboardTopbar);
  all('[data-chart-mode]').forEach(button=>button.addEventListener('click',()=>{
    chartMode=button.dataset.chartMode;
    all('[data-chart-mode]').forEach(el=>{el.classList.toggle('is-active',el===button);el.setAttribute('aria-selected',el===button?'true':'false');});
    if(data)renderTrend();
  }));
  if(admin){
    one('[data-review-search]').addEventListener('input',()=>{if(data)renderReviewQueue();});
    one('[data-review-mode]').addEventListener('change',()=>{if(data)renderReviewQueue();});
    one('[data-review-table]').addEventListener('click',e=>{
      const button=e.target.closest('[data-open-review]');if(button&&!button.disabled)openReview(button.dataset.openReview);
    });
    const modal=document.querySelector('[data-mask-modal]');
    one('[data-modal-close]',modal).addEventListener('click',closeModal);
    modal.addEventListener('click',e=>{if(e.target===modal)closeModal();});
    document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!modal.hidden)closeModal();});
    one('[data-object-list]',modal).addEventListener('click',e=>{
      const button=e.target.closest('[data-object-index]');if(button)selectObject(Number(button.dataset.objectIndex));
    });
    one('[data-save-review]',modal).addEventListener('click',saveReview);
  }
  load();
})();
