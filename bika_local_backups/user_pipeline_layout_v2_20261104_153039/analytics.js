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
  let selectedQueue = 'recent';
  let reviewSourceImage = null; // Loaded source image shared by full-frame overlay and crops.
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
      // BIKA-TREND-REVIEW-MASK-V1: Separate, clearly-labelled provisional data.
      try {
        const url = `/analytics/api/provisional?${params.toString()}`;
        const extraResponse = await fetch(url, {credentials:'same-origin', signal:controller.signal});
        if (extraResponse.ok) {
          const extraPayload = await extraResponse.json();
          const extra = extraPayload?.provisional || {};
          data.provisional_trend = Array.isArray(extra.daily) ? extra.daily : [];
          if (admin && data.review && Array.isArray(extra.recent_runs)) {
            data.review.recent_runs = [...extra.recent_runs, ...(data.review.recent_runs||[])]
              .sort((a,b)=>String(b.date).localeCompare(String(a.date))).slice(0,80);
          }
        }
      } catch (extraError) {
        if (extraError.name === 'AbortError') throw extraError;
        data.provisional_trend = [];
      }
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
    const live = data.live || {};
    const liveRuns = Math.max(0, Number(live.sessions) || 0);
    const liveObservations = Math.max(0, Number(live.defect_observations) || 0);
    const totalRuns = Number(k.inspections || 0);
    const map = {
      '[data-kpi-good]':pct(k.good_rate), '[data-kpi-defect]':pct(k.defect_rate),
      '[data-kpi-standard]':pct(k.meeting_standard_rate),
      '[data-kpi-good-foot]':`Target ${pct(k.target_good)}`,
      '[data-kpi-defect-foot]':`${fmt(k.defects)} defects (est.)`,
      '[data-kpi-standard-foot]':`${fmt(k.meeting_standard_count)} / ${fmt(Math.max(0, Number(k.inspections || 0) - Number(k.incomplete_live_sessions || 0)))} runs · Target ${pct(k.pass_requirement)}`,
      '[data-stat-runs]':fmt(totalRuns), '[data-stat-judged]':fmt(k.judged),
      '[data-stat-normal]':fmt(k.normal), '[data-stat-defective]':fmt(k.defects),
      '[data-footer-note]':data.note,
    };
    Object.entries(map).forEach(([selector, value]) => { const el = one(selector); if (el) el.textContent = value; });
    const clsLine = one('[data-unified-live-class-line]');
    if (clsLine) {
      clsLine.hidden = Boolean(data.kpi?.combined_basis) || !liveObservations;
      if (!clsLine.hidden) {
        const cls = live.classes || {};
        const parts = ['Fractured','Too Dark','Too Short','Bent Snack']
          .filter(name => Number(cls[name]) > 0)
          .map(name => `${name}: ${fmt(cls[name])}`);
        clsLine.textContent = `Live observations (provisional): ${parts.join(' · ')}`;
      }
    }
    renderTrend();
    const info = one('[data-unified-live-trend-note]');
    if (info) {
      info.hidden = Boolean(data.kpi?.combined_basis) || (!liveRuns && !live.unavailable);
      if (!info.hidden) {
        const dates=(live.daily || []).slice(-7).map(item =>
          `<span>${esc(item.date)} · ${fmt(item.sessions)} session${Number(item.sessions)===1?'':'s'}</span>`).join('');
        info.innerHTML = live.unavailable ? 'Live history is temporarily unavailable.' :
          `<strong>Live activity included:</strong> ${fmt(liveRuns)} session${liveRuns===1?'':'s'} · ${fmt(liveObservations)} provisional defect observations · ${fmt(live.ai_frames || 0)} AI frames · ${Number(live.duration_seconds || 0).toFixed(1)} s runtime`+
          `<div class="analytics-unified-live-daily">${dates}</div><span class="analytics-unified-live-foot">Daily quality rates and SPC above still use judged Image/Video records only.</span>`;
      }
    }
    renderShifts();
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
    const coreRows = chartMode === 'spc' ? (data.official_trend || []) : (data.combined_trend || []);
    const provisionalRows = []; // Sources are already summed in combined_trend.
    const byDay = new Map(coreRows.map(r=>[r.date,r]));
    provisionalRows.forEach(p=>{
      if(!byDay.has(p.date)) byDay.set(p.date, {date:p.date, judged:0, normal:0, defect:0,
        yield_rate:null, defect_rate:null, rolling_yield:null, lcl:null, ucl:null});
    });
    const rows = [...byDay.values()].sort((a,b)=>String(a.date).localeCompare(String(b.date))).slice(-90);
    const provisionalByDate = new Map(provisionalRows.map(p=>[p.date,p]));
    if (!rows.some(r => num(r.judged)>0 || num(provisionalByDate.get(r.date)?.video_runs)>0 || num(provisionalByDate.get(r.date)?.live_runs)>0)) {
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
    if (chartMode !== 'spc') mode.desc = `${mode.name} (%) · Total Image + Video + Live · Target`;
    const outputLabel = chartMode === 'spc' ? 'Judged Output' : 'Combined Tracked Output';
    one('[data-trend-guide]').textContent=mode.desc;
    one('[data-trend-caption]').textContent = chartMode === 'spc' ? `${data.spc.method}. Official judged inspections only.` : `Daily total: Image + Video + complete Live counts. Estimates are provisional; SPC uses judged data.`;
    // Two genuine y-axes: rates on the left, daily judged observations on the right.
    // The horizontal dashed line is a TARGET; it is never mislabelled as an LCL.
    // v3.2: SVG coordinates follow the chart holder width AND height.
    // Recompute geometry instead of stretching a fixed 760x395 SVG.
    const w=Math.max(340,Math.min(1600,Math.round(holder.clientWidth||760))),
          h=Math.max(310,Math.min(900,Math.round(holder.clientHeight||395))),
          l=52,r=58,t=32,b=36;
    const iw=w-l-r,ih=h-t-b;
    const X=i=>l+iw*(i+.5)/rows.length;
    // Focus the percent axis on observed values; output volume has its own axis.
    // Include p-chart bounds for SPC; retain a truthful labelled axis.
    const rateValues=rows.flatMap(row=>[row[mode.field],mode.rolling?row[mode.rolling]:null,
      chartMode==='spc'?row.lcl:null,chartMode==='spc'?row.ucl:null]);
    if(mode.target!==null)rateValues.push(mode.target);
    const observed=rateValues.filter(v=>v!==null&&v!==undefined&&Number.isFinite(Number(v))).map(Number);
    const minRate=observed.length?Math.min(...observed):0;
    const maxRate=observed.length?Math.max(...observed):100;
    let axisLow=Math.max(0,Math.floor((minRate-5)/10)*10);
    let axisHigh=Math.min(100,Math.ceil((maxRate+5)/10)*10);
    if(axisHigh-axisLow<30){
      const missing=30-(axisHigh-axisLow);
      axisLow=Math.max(0,axisLow-Math.ceil(missing/20)*10);
      axisHigh=Math.min(100,Math.max(axisLow+30,axisHigh));
    }
    if(axisHigh<=axisLow){axisLow=0;axisHigh=100;}
    const Y=v=>t+ih*(1-(cap(num(v),axisLow,axisHigh)-axisLow)/(axisHigh-axisLow));
    const maximum=Math.max(1,...rows.map(row=>num(row.judged)));
    const nice = Math.pow(10,Math.floor(Math.log10(maximum)));
    const scale=Math.ceil(maximum/nice)*nice;
    const outputY=v=>t+ih*(1-num(v)/scale);
    let contents='';
    for(let tick=0;tick<=5;tick++) {
      const v=axisLow+(axisHigh-axisLow)*tick/5,y=Y(v);
      contents+=`<line class="gridline" x1="${l}" y1="${y}" x2="${w-r}" y2="${y}"/>`;
      contents+=`<text class="axis-label" x="${l-9}" y="${y+3}" text-anchor="end">${v}%</text>`;
    }
    for(let tick=0;tick<=4;tick++) {
      const count=Math.round(scale*tick/4);
      contents+=`<text class="axis-label" x="${w-r+9}" y="${t+ih*(1-tick/4)+3}" text-anchor="start">${fmt(count)}</text>`;
    }
    contents+=`<text class="chart-title-axis" x="${l}" y="13">${esc(mode.name)} (%)</text>`;
    contents+=`<text class="chart-title-axis" x="${w-r}" y="13" text-anchor="end">${esc(outputLabel)}</text>`;
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
    // Visual overlays only; never feed provisional counts into SPC calculations.
    for (const source of ['video','live']) {
      const color=source==='video'?'#cb9250':'#8b6dc6';
      const vals=rows.map(r=>{
        const p=provisionalByDate.get(r.date);
        return p ? p[`${source}_${chartMode==='defect'?'defect_rate':'good_rate'}`] : null;
      });
      contents+=svgLine(vals,X,Y,`series-${source}-provisional`,true);
      rows.forEach((r,i)=>{
        const p=provisionalByDate.get(r.date);
        if(!p || !num(p[`${source}_runs`]))return;
        const rate=vals[i];
        const yy=rate===null||rate===undefined ? t+ih-5 : Y(rate);
        contents+=`<circle data-provisional-index="${i}" data-provisional-source="${source}" cx="${X(i)}" cy="${yy}" r="5" fill="${color}" stroke="white" stroke-width="1.5" tabindex="0" role="button" aria-label="${esc(source)} provisional ${esc(r.date)}"/>`;
      });
    }
    rows.forEach((point,i)=>{
      if(primary[i]===null||primary[i]===undefined)return;
      contents+=`<circle data-point="${i}" class="series-dots ${primaryClass}" cx="${X(i)}" cy="${Y(primary[i])}" r="3.6" tabindex="0" role="button" aria-label="${esc(point.date)} ${esc(mode.name)} ${esc(pct(primary[i]))}"/>`;
    });
    const labelInterval=Math.max(1,Math.ceil(rows.length/7));
    rows.forEach((point,i)=>{
      if(i%labelInterval===0||i===rows.length-1)contents+=`<text class="axis-label" x="${X(i)}" y="${h-14}" text-anchor="middle">${esc(dateLabel(point.date))}</text>`;
    });
    holder.innerHTML=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(mode.name)} with daily judged output volume">${contents}</svg><div class="analytics-chart-tooltip" data-chart-tooltip hidden></div>`;
    const legends=[[mode.name,chartMode==='defect'?'#c86168':'#7b3043'],[outputLabel,'#bfcbd8']];
    if(mode.rolling)legends.push(['7-day rolling','#529f84']);
    if(mode.target!==null)legends.push([`Target ${pct(mode.target)}`,'#c78c95']);
    if(chartMode==='spc')legends.push(['UCL / LCL','#ba9c5b']);
    if(rows.some(r=>num(provisionalByDate.get(r.date)?.video_runs)))legends.push(['Video · Provisional','#cb9250']);
    if(rows.some(r=>num(provisionalByDate.get(r.date)?.live_runs)))legends.push(['Live · Provisional','#8b6dc6']);
    one('[data-chart-legend]').innerHTML=legends.map(([label,color])=>`<span><b style="background:${color}"></b>${esc(label)}</span>`).join('');
    holder.onmouseover=showPoint;
    holder.onfocusin=showPoint;
    holder.onmouseout=e=>{if(e.target?.hasAttribute?.('data-point'))one('[data-chart-tooltip]',holder)?.setAttribute('hidden','');};
    function showPoint(event){
      const provisional=event.target.closest?.('[data-provisional-index]');
      if(provisional){
        const idx=Number(provisional.dataset.provisionalIndex), source=provisional.dataset.provisionalSource;
        const r=rows[idx],p=provisionalByDate.get(r.date),rate=p?.[`${source}_${chartMode==='defect'?'defect_rate':'good_rate'}`];
        const label=source==='video'?'Video':'Live';
        const tip=one('[data-chart-tooltip]',holder);
        tip.innerHTML=`<strong>${esc(r.date)} · ${label}</strong><br>${esc(mode.name)}: <strong>${rate===null||rate===undefined?'Not recorded':pct(rate)}</strong><br>${fmt(p?.[`${source}_runs`])} session(s) · ${fmt(p?.[`${source}_total`])} estimated tracks<br><em>Provisional · excluded from official SPC</em>`;
        tip.removeAttribute('hidden');return;
      }
      const point=event.target.closest?.('[data-point]');if(!point)return;
      const r=rows[Number(point.dataset.point)];if(!r)return;
      const tip=one('[data-chart-tooltip]',holder);
      tip.innerHTML=`<strong>${esc(r.date)}</strong><br>${esc(mode.name)}: <strong>${esc(pct(r[mode.field]))}</strong><br>${esc(outputLabel)}: ${fmt(r.judged)} · Defects: ${fmt(r.defect)}${chartMode==='spc'?`<br>3σ limits: ${pct(r.lcl)} – ${pct(r.ucl)}`:''}`;
      tip.removeAttribute('hidden');
    }
  }

  // ResizeObserver only redraws the visualization; never refetch or mutate data.
  let qualityPlotWidth=0,qualityPlotHeight=0;
  if(typeof ResizeObserver!=='undefined'){
    const plot=one('[data-quality-chart]');
    if(plot){
      const ro=new ResizeObserver(entries=>{
        const bounds=entries[0]?.contentRect;
        const width=Math.round(bounds?.width||0),height=Math.round(bounds?.height||0);
        if(!data||width<1||height<1)return;
        if(Math.abs(width-qualityPlotWidth)<5&&Math.abs(height-qualityPlotHeight)<5)return;
        qualityPlotWidth=width;qualityPlotHeight=height;
        renderTrend();
      });
      ro.observe(plot);
    }
  }

  function renderShifts() {
    const place=one('[data-shift-chart]');
    const heat=data.shift_heatmap;
    if (!heat || !Array.isArray(heat.dates) || !Array.isArray(heat.rows)) {
      place.innerHTML=empty('Shift history unavailable','Please refresh to load the latest shift analysis.');
      return;
    }
    const dates=heat.dates;
    const names=dates.map(iso => {
      const day=new Date(`${iso}T12:00:00`);
      return {weekday:day.toLocaleDateString('en-US',{weekday:'short'}),date:day.toLocaleDateString('en-US',{month:'numeric',day:'numeric'})};
    });
    const header=`<div class="analytics-heatmap-heading"><span>Recent 7 calendar days</span><span>Good Snack Rate</span></div>`;
    const weekdays=`<div class="analytics-heatmap-header"><span class="analytics-heatmap-corner">Shift</span>${names.map(d=>`<span class="analytics-heatmap-date"><b>${esc(d.weekday)}</b><small>${esc(d.date)}</small></span>`).join('')}</div>`;
    const threshold=num(data.kpi.target_good || 85);
    let available=0;
    const rows=heat.rows.map(row => {
      const title=esc(row.name);
      const cells=(row.cells||[]).map(c=>{
        const has=c.good_rate!==null && c.good_rate!==undefined && num(c.judged)>0;
        if(has)available++;
        const rate=has?num(c.good_rate):null;
        const level=!has?'no-data':rate>=threshold?'on-target':rate>=threshold-15?'near-target':'below-target';
        const label=has?`${row.name}, ${c.date}: ${pct(c.good_rate)} Good Snack Rate from ${fmt(c.judged)} judged objects in ${fmt(c.inspections)} runs`:`${row.name}, ${c.date}: No judged observations`;
        return `<button type="button" class="analytics-heatmap-cell analytics-heatmap-${level}" data-heatmap-cell data-detail="${esc(label)}" title="${esc(label)}" aria-label="${esc(label)}">${has?`${Math.round(rate)}%`: '–'}</button>`;
      }).join('');
      return `<div class="analytics-heatmap-data-row" role="row"><span class="analytics-heatmap-shift" title="${title}">${title}</span>${cells}</div>`;
    }).join('');
    const content=heat.rows.length?rows:`<div class="analytics-heatmap-no-shift">No saved inspections in this period. The heatmap will update when inspection results are saved.</div>`;
    const key=`<div class="analytics-heatmap-legend" aria-label="Heatmap legend"><span><i class="analytics-heatmap-key analytics-heatmap-on-target"></i>Meets target</span><span><i class="analytics-heatmap-key analytics-heatmap-near-target"></i>Near target</span><span><i class="analytics-heatmap-key analytics-heatmap-below-target"></i>Below target</span><span><i class="analytics-heatmap-key analytics-heatmap-no-data"></i>No data</span></div>`;
    const foot=available?`Based on ${fmt(available)} shift-day ${available===1?'sample':'samples'} · Hover or tap a cell for counts`:'No judged observations in the displayed week';
    place.innerHTML=`${header}<div class="analytics-heatmap-grid" role="group" aria-label="Good Snack Rate heatmap by inspector shift and date">${weekdays}${content}</div><div class="analytics-heatmap-selected" data-heatmap-selected hidden></div>${key}<p class="analytics-heatmap-foot">${foot}</p>`;
    place.onclick = (event) => {
      const cell=event.target.closest('[data-heatmap-cell]');
      if (!cell) return;
      all('[data-heatmap-cell]',place).forEach(item=>item.classList.toggle('is-selected',item===cell));
      const selected=one('[data-heatmap-selected]',place);
      selected.textContent=cell.dataset.detail || '';
      selected.hidden=false;
    };
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
    const holder=one('[data-defects]');
    // BIKA-UNIFIED-VIEWS-V1: aggregate defect *observations* only.
    // NEVER alter Good Snack Rate / SPC denominators with provisional Live IDs.
    const liveCounts = data.kpi?.combined_basis ? {} : ((data.live || {}).classes || {});
    const classes=(data.defects || []).map(row => ({...row,
      count: Number(row.count || 0) + Number(liveCounts[row.name] || 0)}));
    const total=classes.reduce((s,r)=>s+num(r.count),0);
    if(total===0) {holder.innerHTML=empty('No defect-class counts available','Defect class distribution appears when stored inspection metadata includes class counts.');return;}
    let cursor=0;
    const stops=[];
    classes.forEach(row=> {const percent=num(row.count)/total*100;if(percent>0){stops.push(`${row.color} ${cursor.toFixed(3)}% ${(cursor+percent).toFixed(3)}%`);cursor+=percent;}});
    holder.innerHTML=`<div class="analytics-donut-row"><div class="analytics-donut" style="background:conic-gradient(${stops.join(',')})"><div class="analytics-donut-center"><strong>${fmt(total)}</strong><small>Defects</small></div></div><div class="analytics-donut-desc">Detected defects<br>across saved inspection runs.</div></div>${classes.map(row=>`<div class="analytics-defect-row"><span class="analytics-defect-color" style="background:${row.color}"></span><span>${esc(row.name)}</span><strong>${fmt(row.count)}</strong><small>${(num(row.count)*100/total).toFixed(1)}%</small></div>`).join('')}`;
    if (Number(data.live?.defect_observations || 0) > 0) {
      holder.innerHTML += `<p class="analytics-unified-live-foot">Includes ${fmt(data.live.defect_observations)} provisional Live Track ID observations; these are not verified unique products.</p>`;
    }
  }

  function renderBayesian() {
    const holder=one('[data-bayesian]'); const b=data.bayesian;
    if (!b) {holder.innerHTML=empty('Awaiting observations','The Beta–Binomial estimate becomes available after judged snack observations are saved.');return;}
    const low=cap(num(b.lower),0,100),high=cap(num(b.upper),0,100),mid=cap(num(b.mean),0,100);
    holder.innerHTML=`<div class="analytics-bayes-metric"><small>Posterior mean · Good Snack Rate</small><strong>${pct(mid)}</strong></div><div class="analytics-bayes-body"><div class="analytics-bayes-track"><div class="analytics-bayes-range" style="left:${low}%;width:${high-low}%"></div><div class="analytics-bayes-pin" style="left:${mid}%"></div></div><div class="analytics-bayes-scale"><span>0%</span><strong>Approx. 95% credible interval: ${pct(low)} – ${pct(high)}</strong><span>100%</span></div><p class="analytics-bayes-explain">${esc(b.prior)} prior updated with ${fmt((data.official_kpi || data.kpi).normal)} normal and ${fmt((data.official_kpi || data.kpi).defects)} defective observations. ${esc(b.method)}. This is uncertainty estimation, not future prediction.</p></div>`;
  }

  function renderReviewQueue() {
    const review=data.review || {candidates:[],recent_runs:[],total_candidates:0};
    const count=one('[data-review-count]'); if(count) count.textContent=fmt(review.total_candidates);
    const stats=review.status||{};
    const statusValues={'[data-review-pending]':stats.pending_runs,'[data-review-confirmed]':stats.confirmed_objects,'[data-review-false]':stats.false_positive_objects,'[data-review-corrected]':stats.corrected_objects};
    Object.entries(statusValues).forEach(([selector,value])=>{const el=one(selector);if(el)el.textContent=value===undefined?'—':fmt(value);});
    const query=(one('[data-review-search]')?.value||'').trim().toLowerCase();
    const mode=one('[data-review-mode]')?.value||'recent';
    selectedQueue=mode;
    reviewList=(mode==='recent'?review.recent_runs:review.candidates)||[];
    const rows=reviewList.filter(row=>!query||`${row.batch_id} ${row.file_name} ${row.reasons.join(' ')}`.toLowerCase().includes(query));
    const tbody=one('[data-review-table]');
    if(!rows.length) {
      tbody.innerHTML=`<tr><td colspan="5" class="analytics-table-empty">${query?'No runs match your search.':mode==='flagged'?'No pipeline anomalies found in this period. Select All inspection runs for normal and provisional activity.':'No saved Image / Video / Live runs in this period.'}</td></tr>`;
    } else {
      tbody.innerHTML=rows.map(row=>{
        const reasons=Array.isArray(row.reasons)?row.reasons:[];
        const reason=reasons.length?reasons[0]:'Routine review';
        const more=reasons.length>1?`<span class="analytics-reason-more">+${fmt(reasons.length-1)} more</span>`:'';
        const reviewed=Math.max(0,num(row.reviewed));
        const reviewState=reviewed>0?'has-reviewed':'pending';
        const reviewLabel=reviewed>0?`${fmt(reviewed)} reviewed`:'Pending review';
        const queueTag=mode==='flagged'?'Review required':row.source_type==='video'?'Video · Provisional':row.source_type==='live'?'Live · Provisional':'Saved image';
        const queueClass=mode==='flagged'?'needs-review':'routine';
        return `<tr>
          <td>
            <div class="analytics-review-source">
              ${row.preview_url?`<img src="${esc(row.preview_url)}" class="analytics-review-thumb" alt="Saved inspection thumbnail" loading="lazy">`:'<span class="analytics-review-thumbnail-empty"><iconsax-icon name="gallery" type="twotone" size="20" color="currentColor"></iconsax-icon></span>'}
              <div class="analytics-review-source-info">
                <div class="analytics-review-primary" title="${esc(row.batch_id)}">${esc(row.batch_id)}</div>
                <div class="analytics-review-secondary" title="${esc(row.file_name)}">${esc(row.file_name)}</div>
                <div class="analytics-review-secondary analytics-review-date"><iconsax-icon name="calendar" type="twotone" size="12" color="currentColor"></iconsax-icon>${esc(row.date)}</div>
              </div>
            </div>
          </td>
          <td class="analytics-review-quantity"><span class="analytics-review-number">${fmt(row.judged)}</span><small>observations</small></td>
          <td>
            <div class="analytics-reason-stack">
              <span class="analytics-reason-tag ${queueClass}"><span class="analytics-reason-dot" aria-hidden="true"></span>${queueTag}</span>
              <span class="analytics-reason-detail" title="${esc(reasons.join('; '))}">${esc(reason)}</span>${more}
            </div>
          </td>
          <td>
            <span class="analytics-review-status-pill ${reviewState}"><span class="analytics-review-status-dot" aria-hidden="true"></span>${reviewLabel}</span>
          </td>
          <td class="analytics-review-action-cell">
            <button type="button" class="analytics-view-button" data-open-review="${esc(row.batch_id)}" aria-label="Review masks for ${esc(row.batch_id)}" title="Review masks" ${row.reviewable?'':'disabled'}>
              <iconsax-icon name="eye" type="twotone" size="20" color="currentColor" aria-hidden="true"></iconsax-icon>
            </button>
          </td>
        </tr>`;
      }).join('');
    }
    const total=one('[data-review-pagination]');if(total)total.textContent=`${fmt(rows.length)} shown${review.total_candidates>40 && mode==='flagged'?' · latest 40 flagged runs':''}`;
  }

  // Keep the native select as the stored value for the existing review API.
  // The visual menu lives outside the scrolling modal so options cannot be clipped.
  const decisionSelect=document.querySelector('[data-decision]');
  const decisionButton=document.querySelector('[data-decision-trigger]');
  const decisionMenu=document.querySelector('[data-decision-menu]');
  const decisionOptions=decisionMenu?Array.from(decisionMenu.querySelectorAll('[data-decision-option]')):[];
  // BIKA-REVIEW-CORRECT-CLASS-V1_1: use existing native review decision and save API.
  const correctField = document.querySelector('[data-correct-class-field]');
  const correctSelect = document.querySelector('[data-correct-class]');
  function normalizeReviewClass(value) {
    return String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
  }
  function syncCorrectClassField(){
    if(!correctField || !correctSelect || !decisionSelect) return;
    const needed = decisionSelect.value === 'incorrect_class';
    correctField.hidden = !needed;
    correctSelect.disabled = !needed;
    correctSelect.required = needed;
    if (!needed) correctSelect.value = '';
  }
  decisionSelect?.addEventListener('change', syncCorrectClassField);

  function syncDecisionPicker(){
    if(!decisionSelect||!decisionButton)return;
    const option=decisionSelect.selectedOptions[0];
    const label=decisionButton.querySelector('[data-decision-selected]');
    if(label)label.textContent=option?.textContent||'Choose a review decision';
    decisionOptions.forEach(el=>el.setAttribute('aria-selected',String(el.dataset.decisionOption===decisionSelect.value)));
  }
  function closeDecisionPicker(focus=false){
    if(!decisionMenu||!decisionButton)return;
    decisionMenu.hidden=true;
    decisionButton.setAttribute('aria-expanded','false');
    if(focus)decisionButton.focus();
  }
  function positionDecisionPicker(){
    if(!decisionMenu||!decisionButton||decisionMenu.hidden)return;
    const rect=decisionButton.getBoundingClientRect(),margin=10;
    const h=decisionMenu.offsetHeight||184;
    const below=window.innerHeight-rect.bottom-margin;
    const above=rect.top-margin;
    const top=below>=h+8||below>=above?rect.bottom+7:rect.top-h-7;
    const width=Math.max(200,rect.width);
    decisionMenu.style.width=`${Math.min(width,window.innerWidth-2*margin)}px`;
    decisionMenu.style.left=`${Math.max(margin,Math.min(rect.left,window.innerWidth-width-margin))}px`;
    decisionMenu.style.top=`${Math.max(margin,Math.min(top,window.innerHeight-h-margin))}px`;
  }
  function openDecisionPicker(){
    if(!decisionMenu||!decisionButton||!decisionSelect)return;
    syncDecisionPicker();decisionMenu.hidden=false;
    decisionButton.setAttribute('aria-expanded','true');
    positionDecisionPicker();
    (decisionOptions.find(el=>el.dataset.decisionOption===decisionSelect.value)||decisionOptions[0])?.focus();
  }
  if(decisionButton){
    decisionButton.addEventListener('click',()=>decisionMenu.hidden?openDecisionPicker():closeDecisionPicker());
    decisionButton.addEventListener('keydown',e=>{
      if(['ArrowDown','ArrowUp','Enter',' '].includes(e.key)){e.preventDefault();openDecisionPicker();}
    });
    decisionOptions.forEach((opt,index)=>{
      opt.addEventListener('click',()=>{
        decisionSelect.value=opt.dataset.decisionOption;
        decisionSelect.dispatchEvent(new Event('change',{bubbles:true}));
        syncDecisionPicker();closeDecisionPicker(true);
      });
      opt.addEventListener('keydown',e=>{
        if(e.key==='Escape'){e.preventDefault();closeDecisionPicker(true);}
        if(e.key==='ArrowDown'||e.key==='ArrowUp'){
          e.preventDefault();decisionOptions[(index+(e.key==='ArrowDown'?1:-1)+decisionOptions.length)%decisionOptions.length].focus();
        }
        if(e.key==='Home'){e.preventDefault();decisionOptions[0].focus();}
        if(e.key==='End'){e.preventDefault();decisionOptions[decisionOptions.length-1].focus();}
      });
    });
    document.addEventListener('pointerdown',e=>{
      if(decisionMenu.hidden||decisionMenu.contains(e.target)||decisionButton.contains(e.target))return;
      closeDecisionPicker();
    });
    document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!decisionMenu.hidden){e.stopPropagation();closeDecisionPicker(true);}},true);
    window.addEventListener('resize',()=>{if(!decisionMenu.hidden)positionDecisionPicker();});
    // Modal column scrolling requires menu to track the trigger position.
    document.querySelector('.analytics-mask-side')?.addEventListener('scroll',()=>{if(!decisionMenu.hidden)positionDecisionPicker();},{passive:true});
  }

  // Generate both previews from the same saved source image + polygon points.
  // No new API, image uploads, or changes to original prediction records.
  function renderSelectedCrop(){
    const modal=document.querySelector('[data-mask-modal]');
    const panel=modal?.querySelector('[data-crop-panel]');
    if(!panel)return;
    if(!selectedObject||!reviewRecord||!reviewSourceImage?.naturalWidth){panel.hidden=true;return;}
    const orig=panel.querySelector('[data-crop-original]');
    const masked=panel.querySelector('[data-crop-masked]');
    if(!orig||!masked)return;
    const img=reviewSourceImage;
    const metaW=num(reviewRecord.image.width)||img.naturalWidth;
    const metaH=num(reviewRecord.image.height)||img.naturalHeight;
    const polys=(selectedObject.polygons||[]).filter(p=>Array.isArray(p)&&p.length>=3).slice(0,40);
    let pointCount=0;
    let x1=Infinity,y1=Infinity,x2=-Infinity,y2=-Infinity;
    for(const poly of polys){
      for(const p of poly.slice(0,4000)){
        if(!Array.isArray(p)||p.length<2)continue;
        const x=Number(p[0]),y=Number(p[1]);
        if(!Number.isFinite(x)||!Number.isFinite(y))continue;
        pointCount++;
        x1=Math.min(x1,x);y1=Math.min(y1,y);x2=Math.max(x2,x);y2=Math.max(y2,y);
      }
    }
    if(!pointCount){
      const b=selectedObject.bbox||{};
      x1=num(b.x1??b.xmin??b.left??b[0]);y1=num(b.y1??b.ymin??b.top??b[1]);
      x2=num(b.x2??b.xmax??b.right??b[2]);y2=num(b.y2??b.ymax??b.bottom??b[3]);
      if((!x2||!y2)&&b.width&&b.height){x2=x1+num(b.width);y2=y1+num(b.height);}
    }
    if(!Number.isFinite(x1+y1+x2+y2)||x2<=x1||y2<=y1){panel.hidden=true;return;}
    // Keep some surrounding context so the object does not touch crop borders.
    const pad=Math.max(9,Math.min(65,Math.max(x2-x1,y2-y1)*.19));
    x1=cap(x1-pad,0,metaW);x2=cap(x2+pad,0,metaW);
    y1=cap(y1-pad,0,metaH);y2=cap(y2+pad,0,metaH);
    const scaleX=img.naturalWidth/metaW,scaleY=img.naturalHeight/metaH;
    const sx=x1*scaleX,sy=y1*scaleY,sw=(x2-x1)*scaleX,sh=(y2-y1)*scaleY;
    if(sw<=0||sh<=0){panel.hidden=true;return;}
    const ratio=Math.min(1,520/sw,220/sh), cw=Math.max(1,Math.round(sw*ratio)),ch=Math.max(1,Math.round(sh*ratio));
    for(const canvas of [orig,masked]){
      canvas.width=cw;canvas.height=ch;
      const ctx=canvas.getContext('2d');if(!ctx)continue;
      ctx.clearRect(0,0,cw,ch);
      ctx.drawImage(img,sx,sy,sw,sh,0,0,cw,ch);
    }
    const ctx=masked.getContext('2d');
    if(ctx&&pointCount){
      const colour=/^#[0-9a-f]{6}$/i.test(selectedObject.colour)?selectedObject.colour:'#741f2e';
      const toX=x=>(x-x1)/(x2-x1)*cw;
      const toY=y=>(y-y1)/(y2-y1)*ch;
      polys.forEach(poly=>{
        const valid=poly.slice(0,4000).filter(pt=>Array.isArray(pt)&&pt.length>=2&&Number.isFinite(Number(pt[0]))&&Number.isFinite(Number(pt[1])));
        if(valid.length<3)return;
        ctx.beginPath();
        valid.forEach((pt,i)=>{const x=toX(Number(pt[0])),y=toY(Number(pt[1]));if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);});
        ctx.closePath();
        ctx.fillStyle=colour;ctx.globalAlpha=.30;ctx.fill();ctx.globalAlpha=1;
        ctx.lineWidth=Math.max(1.5,Math.min(3.2,cw/145));
        ctx.strokeStyle='#ffffff';ctx.stroke();
      });
    }
    panel.querySelector('[data-crop-object-id]').textContent=selectedObject.object_id;
    panel.querySelector('[data-crop-note]').textContent=pointCount
      ?'Original and masked views of the selected saved object.'
      :'No saved polygon for this object; displaying the bounding-box crop.';
    panel.hidden=false;
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
    selectedObject=null;reviewRecord=null;reviewSourceImage=null;
    const cropPanel=one('[data-crop-panel]',modal); if(cropPanel)cropPanel.hidden=true;
    closeDecisionPicker();
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
        reviewSourceImage=img;
        if(selectedObject) renderSelectedCrop();
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
    if(correctSelect) correctSelect.value=old?.corrected_class||'';
    syncDecisionPicker();
    syncCorrectClassField();
    renderSelectedCrop();
    one('[data-review-note]',modal).value=old?.note||'';
    one('[data-save-review]',modal).disabled=false;
    const message=one('[data-save-message]',modal); message.textContent='';message.classList.remove('is-error');
  }

  async function saveReview() {
    if(!reviewRecord||!selectedObject)return;
    const modal=document.querySelector('[data-mask-modal]');
    const button=one('[data-save-review]',modal),message=one('[data-save-message]',modal);
    const token=document.querySelector('meta[name="csrf-token"]')?.content||'';
    const decision=one('[data-decision]',modal).value;
    const correctedClass = decision==='incorrect_class' ? (correctSelect?.value || '') : null;
    if(decision==='incorrect_class'){
      if(!correctedClass){
        message.classList.add('is-error');message.textContent='Please select the correct class.';
        correctSelect?.focus();return;
      }
      if(normalizeReviewClass(selectedObject.class_name)===correctedClass){
        message.classList.add('is-error');message.textContent='Choose a different class from the AI prediction.';
        correctSelect?.focus();return;
      }
    }
    button.disabled=true;message.classList.remove('is-error');message.textContent='Saving human review…';
    try {
      const response=await fetch(`${root.dataset.reviewUrlRoot}${encodeURIComponent(reviewRecord.batch_id)}`,{
        method:'POST',credentials:'same-origin',
        headers:{'Content-Type':'application/json','X-CSRFToken':token},
        body:JSON.stringify({object_id:selectedObject.object_id,decision,corrected_class:correctedClass,note:one('[data-review-note]',modal).value})
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
    closeDecisionPicker();
    modal.setAttribute('hidden','');document.body.style.overflow='';reviewRecord=null;selectedObject=null;reviewSourceImage=null;
  }
  // Dashboard-matched date pill/dropdown. Native select remains as an internal value holder for load().
  const dateButton=one('[data-range-button]');
  const dateMenu=one('[data-range-menu]');
  const rangeSelect=one('[data-range]');
  // BIKA_ANALYTICS_PERIOD_MEMORY_V1: preference belongs to logged-in account,
  // stored on the server, not shared between accounts on the same browser.
  const periodPreferenceUrl = root.dataset.periodPreferenceUrl;
  const allowedPeriodKeys = new Set(['today','7d','30d','90d','all','custom']);
  const isoValid = value => {
    if(typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value))return false;
    const [year,month,day] = value.split('-').map(Number);
    const parsed = new Date(Date.UTC(year,month-1,day));
    return parsed.getUTCFullYear()===year && parsed.getUTCMonth()===month-1 && parsed.getUTCDate()===day;
  };
  function applySavedPeriod(pref){
    if(!pref || !allowedPeriodKeys.has(pref.range))return false;
    if(pref.range==='custom'){
      if(!isoValid(pref.from)||!isoValid(pref.to)||pref.from>pref.to)return false;
      one('[data-date-from]').value=pref.from;
      one('[data-date-to]').value=pref.to;
      if(pref.from===pref.to)singleDayInput.value=pref.from;
      one('[data-range-label]').textContent=periodLabel(pref.from,pref.to);
    }else{
      one('[data-range-label]').textContent=presetPeriodLabel(pref.range);
    }
    rangeSelect.value=pref.range;
    all('[data-range-option]').forEach(item=>item.classList.toggle('is-active',item.dataset.rangeOption===pref.range));
    return true;
  }
  let periodWriteQueue = Promise.resolve();
  function saveSelectedPeriod(){
    if(!periodPreferenceUrl)return;
    const range=rangeSelect.value;
    const payload={range};
    if(range==='custom'){
      payload.from=one('[data-date-from]').value;
      payload.to=one('[data-date-to]').value;
    }
    const token=document.querySelector('meta[name="csrf-token"]')?.content||'';
    // Serialize requests to avoid older user selections overwriting newer ones.
    periodWriteQueue=periodWriteQueue.catch(()=>{}).then(async()=>{
      const response=await fetch(periodPreferenceUrl,{
        method:'POST',credentials:'same-origin',keepalive:true,
        headers:{'Content-Type':'application/json','X-CSRFToken':token},
        body:JSON.stringify(payload)
      });
      if(!response.ok)throw new Error(`Period preference save returned ${response.status}`);
    }).catch(error=>{console.warn('Analytics period preference not saved:',error);});
  }
  async function restorePeriodAndLoad(){
    if(periodPreferenceUrl){
      try{
        const response=await fetch(periodPreferenceUrl, {credentials:'same-origin',cache:'no-store'});
        if(response.ok){
          const payload=await response.json();
          applySavedPeriod(payload.preference);
        } else {
          console.warn('Analytics period preference load returned',response.status);
        }
      }catch(error){console.warn('Analytics period preference unavailable:',error);}
    }
    await load();
  }

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
    closeDate();saveSelectedPeriod();load();
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
    closeDate();saveSelectedPeriod();load();
  });
  one('[data-apply-range]').addEventListener('click',()=>{
    const from=one('[data-date-from]').value,to=one('[data-date-to]').value;
    if(!from||!to||from>to){status('Choose a valid custom date range.',true);return;}
    rangeSelect.value='custom';
    one('[data-range-label]').textContent=periodLabel(from,to);
    if(from===to)singleDayInput.value=from;
    all('[data-range-option]').forEach(item=>item.classList.remove('is-active'));
    closeDate();saveSelectedPeriod();load();
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
    // Accessible custom queue picker. Keep the original <select> as the single
    // source of truth so the existing API filtering and change handler are unchanged.
    const queueWrap=one('[data-review-select]');
    const queueNative=one('[data-review-mode]');
    const queueTrigger=one('[data-review-trigger]');
    const queueMenu=one('[data-review-options]');
    const queueOptions=all('[data-review-option]');
    function syncQueuePicker(){
      const active=queueOptions.find(option=>option.dataset.reviewOption===queueNative.value);
      const label=active?.querySelector('span')?.textContent || 'Flagged runs';
      one('[data-review-selected]').textContent=label;
      queueTrigger.setAttribute('aria-label',`Review queue: ${label}`);
      queueOptions.forEach(option=>option.setAttribute('aria-selected',String(option===active)));
    }
    function closeQueuePicker(restoreFocus=false){
      queueMenu.hidden=true;
      queueTrigger.setAttribute('aria-expanded','false');
      queueWrap.classList.remove('is-open');
      if(restoreFocus)queueTrigger.focus();
    }
    function openQueuePicker(){
      queueMenu.hidden=false;
      queueTrigger.setAttribute('aria-expanded','true');
      queueWrap.classList.add('is-open');
      const active=queueOptions.find(option=>option.dataset.reviewOption===queueNative.value);
      (active||queueOptions[0])?.focus();
    }
    queueTrigger.addEventListener('click',()=>{
      if(queueMenu.hidden)openQueuePicker();else closeQueuePicker();
    });
    queueOptions.forEach(option=>option.addEventListener('click',()=>{
      const next=option.dataset.reviewOption;
      const changed=queueNative.value!==next;
      queueNative.value=next;
      syncQueuePicker();
      closeQueuePicker(true);
      if(changed)queueNative.dispatchEvent(new Event('change',{bubbles:true}));
    }));
    queueWrap.addEventListener('keydown',event=>{
      if(queueMenu.hidden){
        if((event.key==='ArrowDown'||event.key==='ArrowUp')&&document.activeElement===queueTrigger){
          event.preventDefault();openQueuePicker();
        }
        return;
      }
      if(event.key==='Escape'){event.preventDefault();closeQueuePicker(true);return;}
      if(event.key==='Tab'){closeQueuePicker();return;}
      if(event.key==='ArrowDown'||event.key==='ArrowUp'){
        event.preventDefault();
        const index=queueOptions.indexOf(document.activeElement);
        const step=event.key==='ArrowDown'?1:-1;
        queueOptions[(index+step+queueOptions.length)%queueOptions.length].focus();
      }
    });
    document.addEventListener('pointerdown',event=>{
      if(!queueWrap.contains(event.target)&&!queueMenu.hidden)closeQueuePicker();
    });
    queueNative.addEventListener('change',syncQueuePicker);
    syncQueuePicker();
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

  // Data Analytics info tips: one viewport-aligned tooltip for hover, keyboard and touch.
  // A body-level popover avoids clipping in KPI cards / narrow shift panels.
  (() => {
    const infoButtons = all('.analytics-info[data-info-tooltip]');
    if (!infoButtons.length) return;
    const tip = document.createElement('div');
    tip.className = 'analytics-floating-info-tooltip';
    tip.id = 'analytics-metric-description';
    tip.setAttribute('role','tooltip');
    tip.hidden = true;
    // Same compact text-only popover as Dashboard: no extra heading or warning glyph.
    const copy = document.createElement('div');
    copy.className = 'analytics-floating-info-copy';
    tip.append(copy);
    document.body.append(tip);
    let anchor = null;
    let clicked = false;
    const hide = () => {
      tip.hidden = true;
      if (anchor) anchor.removeAttribute('aria-describedby');
      anchor = null; clicked = false;
    };
    const show = button => {
      if (anchor && anchor !== button) hide();
      anchor = button;
      copy.textContent = button.dataset.infoTooltip || '';
      tip.hidden = false;
      button.setAttribute('aria-describedby',tip.id);
      const rect = button.getBoundingClientRect();
      const tw = tip.offsetWidth, th = tip.offsetHeight;
      const left = Math.max(12, Math.min(window.innerWidth - tw - 12, rect.left + rect.width / 2 - tw / 2));
      const above = rect.top >= th + 15;
      const top = above ? rect.top - th - 10 : rect.bottom + 10;
      tip.style.left = Math.round(left) + 'px';
      tip.style.top = Math.round(top) + 'px';
      tip.style.setProperty('--a-tip-arrow-x',Math.max(16,Math.min(tw - 16,rect.left + rect.width / 2 - left)) + 'px');
      tip.dataset.placement = above ? 'above' : 'below';
    };
    infoButtons.forEach(button => {
      button.addEventListener('pointerenter', event => { if (event.pointerType !== 'touch') show(button); });
      button.addEventListener('pointerleave', event => { if (event.pointerType !== 'touch' && !clicked) hide(); });
      button.addEventListener('focus', () => show(button));
      button.addEventListener('blur', () => { if (!clicked) hide(); });
      button.addEventListener('click', event => {
        event.preventDefault();
        if (anchor === button && clicked) hide();
        else { show(button); clicked = true; }
      });
    });
    document.addEventListener('pointerdown', event => {
      if (anchor && !anchor.contains(event.target)) hide();
    });
    document.addEventListener('keydown', event => { if (event.key === 'Escape') hide(); });
    window.addEventListener('scroll',hide,true);
    window.addEventListener('resize',hide);
  })();
  restorePeriodAndLoad();
})();

/* BIKA-UNIFIED-VIEWS-V1 */

/* BIKA-UNIFIED-FIX-V2 */

/* BIKA-TREND-REVIEW-MASK-V1 */

/* BIKA-COMBINED-TOTALS-V1-1 */

/* BIKA-ANALYTICS-KPI-COMPACT-V1 */

// BIKA-REVIEW-CORRECT-CLASS-V1_1
// BIKA_ANALYTICS_DEMO_VISUAL_V3_2_20261103: responsive visuals only; existing SPC aggregation is preserved.
