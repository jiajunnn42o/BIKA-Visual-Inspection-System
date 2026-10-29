/* BIKA Live Stream · sampled AI keyframes with Hikvision RTSP or Camo local camera. */
(() => {
  'use strict';
  const page = document.querySelector('[data-live-stream-page]');
  if (!page) return;

  const get = selector => page.querySelector(selector);
  const statusEl = get('[data-stat-connection]');
  const noteEl = get('[data-stat-connection-note]');
  const fpsEl = get('[data-stat-fps]');
  const onlineDot = get('[data-online-dot]');
  const badge = get('[data-live-badge]');
  const liveTag = get('.lsi-live-tag');
  const liveLabel = get('[data-live-label]');
  const image = get('[data-video-image]');
  const empty = get('[data-video-empty]');
  const emptyTitle = get('[data-placeholder-title]');
  const emptyText = get('[data-placeholder-message]');
  const connection = get('[data-detail-connection]');
  const resolution = get('[data-detail-resolution]');
  const stageRes = get('[data-video-resolution]');
  const stageFPS = get('[data-video-fps]');
  const foot = get('[data-viewer-foot-status]');
  const footDot = get('.lsi-foot-dot');
  const message = get('[data-control-message]');
  const stream = get('[data-camera-stream]');
  const camoSettings = get('[data-camo-settings]');
  const camoIndex = get('[data-camo-index]');
  const sourceHelper = get('[data-camera-source-help]');
  const autoConnectToggle = get('[data-auto-connect]');
  const connectButton = get('[data-connect-button]');
  const disconnectButton = get('[data-disconnect-button]');
  const snapshotButton = get('[data-snapshot-button]');
  const monitorState = get('[data-monitor-state]');
  const trendLatest = get('[data-monitor-fps]');
  const trendSvg = get('[data-fps-chart]');
  const trendPath = get('[data-fps-path]');
  const trendPoint = get('[data-fps-point]');
  const trendEmpty = get('[data-trend-empty]');
  const uptimeText = get('[data-monitor-uptime]');
  const lastFrameText = get('[data-monitor-last-frame]');
  const fpsSamples = [];
  const FPS_WINDOW_MS = 60000;
  let fpsStream = null;
  let lastUptime = null;

  function formatUptime(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) return '—';
    const total = Math.floor(seconds);
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor(total % 3600 / 60);
    const secs = total % 60;
    const two = n => String(n).padStart(2, '0');
    return hours ? `${two(hours)}:${two(minutes)}:${two(secs)}` : `${two(minutes)}:${two(secs)}`;
  }

  // Chart uses only measured camera_fps samples from the protected status API.
  // Missing/offline values are not interpolated or replaced with demo numbers.
  function renderTrend(camera, isOnline) {
    const now = performance.now();
    const fps = Number(camera?.camera_fps);
    const uptime = camera?.stream_uptime_seconds;
    if (!isOnline || fpsStream !== camera.stream ||
        (lastUptime != null && typeof uptime === 'number' && uptime + 1 < lastUptime)) {
      fpsSamples.length = 0;
    }
    fpsStream = isOnline ? camera.stream : null;
    lastUptime = isOnline && typeof uptime === 'number' ? uptime : null;
    if (isOnline && camera.camera_fps != null && Number.isFinite(fps) && fps > 0) {
      fpsSamples.push({t: now, fps});
    }
    while (fpsSamples.length && fpsSamples[0].t < now - FPS_WINDOW_MS) fpsSamples.shift();

    monitorState.textContent = isOnline ? 'Live telemetry' : camera?.state === 'connecting' ? 'Connecting' : 'Waiting for camera';
    monitorState.classList.toggle('is-online', isOnline);
    trendLatest.textContent = fpsSamples.length ? `${fpsSamples[fpsSamples.length - 1].fps.toFixed(1)} FPS` : '—';
    uptimeText.textContent = isOnline ? formatUptime(Number(uptime)) : '—';
    const frameAge = camera?.last_frame_seconds_ago;
    lastFrameText.textContent = isOnline && frameAge != null && Number.isFinite(Number(frameAge))
      ? `${Math.max(0, Number(frameAge)).toFixed(1)} s ago` : '—';

    const samples = fpsSamples;
    const hasSamples = samples.length > 0;
    trendEmpty.hidden = hasSamples;
    if (!hasSamples) {
      trendPath.setAttribute('d', '');
      trendPoint.hidden = true;
      trendSvg.setAttribute('aria-label', 'Waiting for measured FPS samples');
      return;
    }
    const values = samples.map(s => s.fps);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const bottom = Math.max(0, Math.floor(min - 3));
    const top = Math.max(bottom + 1, Math.ceil(max + 3));
    const x = t => 5 + 310 * Math.max(0, Math.min(1, (t - (now - FPS_WINDOW_MS)) / FPS_WINDOW_MS));
    const y = value => 50 - 42 * (value - bottom) / (top - bottom);
    const points = samples.map(s => [x(s.t), y(s.fps)]);
    trendPath.setAttribute('d', points.map(([px, py], index) => `${index ? 'L' : 'M'}${px.toFixed(1)} ${py.toFixed(1)}`).join(' '));
    const last = points[points.length - 1];
    trendPoint.setAttribute('cx', last[0].toFixed(1));
    trendPoint.setAttribute('cy', last[1].toFixed(1));
    trendPoint.hidden = false;
    trendSvg.setAttribute('aria-label', `Measured camera FPS over the last 60 seconds: ${min.toFixed(1)} to ${max.toFixed(1)} FPS`);
  }

  const authorizedControl = page.dataset.canControlCamera === 'true';
  const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
  let busy = false;
  let currentState = null;
  let currentStream = null;
  let lastCameraStatus = null;

  // Latest-only HTTP JPEG preview. Fetches are strictly serialized, and each
  // response replaces the older image; no accumulating MJPEG decoder backlog.
  // This improves browser-side freshness, not upstream RTSP/camera latency.
  const previewAge = get('[data-preview-age]');
  const previewURL = page.dataset.latestFrameUrl;
  let previewEpoch = 0;
  let previewTimer = null;
  let previewRequest = null;
  let previewImageURL = null;
  let previewSequence = null;
  let previewRunning = false;
  // Target approximately 10 preview requests per second. The existing fetch loop
  // awaits the full response and JPEG decode before scheduling another request:
  // at most one request is active, so slower networks never create a frame queue.
  // Camera FPS and AI inference FPS remain independent of this display target.
  const PREVIEW_INTERVAL_MS = 100;

  function stopLatestPreview() {
    previewEpoch += 1;
    previewRunning = false;
    if (previewTimer !== null) clearTimeout(previewTimer);
    previewTimer = null;
    if (previewRequest) previewRequest.abort();
    previewRequest = null;
    previewSequence = null;
    if (previewImageURL) URL.revokeObjectURL(previewImageURL);
    previewImageURL = null;
    image.removeAttribute('src');
    if (previewAge) previewAge.textContent = '—';
  }

  async function updateLatestPreview(epoch) {
    if (epoch !== previewEpoch || !previewRunning) return;
    const start = performance.now();
    if (document.hidden) {
      previewTimer = setTimeout(() => updateLatestPreview(epoch), 650);
      return;
    }
    const request = new AbortController();
    previewRequest = request;
    const timeout = setTimeout(() => request.abort(), 4000);
    try {
      const suffix = previewSequence == null ? '' : '?seq=' + encodeURIComponent(previewSequence);
      const response = await fetch(previewURL + suffix, {
        credentials: 'same-origin', cache: 'no-store', signal: request.signal,
      });
      if (response.status === 204) {
        // No newer frame. Retain the image but update the server-side age.
        const ageHeader = response.headers.get('X-BIKA-Server-Frame-Age-Ms');
        if (previewAge && ageHeader != null && Number.isFinite(Number(ageHeader))) {
          previewAge.textContent = Math.max(0, Math.round(Number(ageHeader))) + ' ms';
        }
      } else if (response.ok) {
        const nextSequence = response.headers.get('X-BIKA-Frame-Sequence');
        const ageHeader = response.headers.get('X-BIKA-Server-Frame-Age-Ms');
        const blob = await response.blob();
        if (epoch !== previewEpoch || !previewRunning) return;
        const freshURL = URL.createObjectURL(blob);
        try {
          const decoded = new Image();
          decoded.src = freshURL;
          await decoded.decode();
          if (epoch !== previewEpoch || !previewRunning) {
            URL.revokeObjectURL(freshURL);
            return;
          }
          const prior = previewImageURL;
          image.src = freshURL;
          previewImageURL = freshURL;
          if (prior) URL.revokeObjectURL(prior);
          previewSequence = nextSequence || previewSequence;
          if (previewAge && ageHeader != null) {
            const age = Number(ageHeader) + (performance.now() - start);
            previewAge.textContent = Number.isFinite(age) ? Math.max(0, Math.round(age)) + ' ms' : '—';
          }
        } catch (_) {
          URL.revokeObjectURL(freshURL);
        }
      } else if (response.status === 409) {
        // Camera not yet online; the regular status poll controls the UI.
      } else {
        throw new Error('HTTP ' + response.status);
      }
    } catch (error) {
      // Abort on disconnect/pagehide is expected. A transient network failure
      // should not interrupt the camera worker or restart the AI model.
      if (epoch === previewEpoch && !request.signal.aborted && lastCameraStatus?.state === 'online') {
        if (previewAge) previewAge.textContent = 'Updating…';
      }
    } finally {
      clearTimeout(timeout);
      if (previewRequest === request) previewRequest = null;
      if (epoch === previewEpoch && previewRunning) {
        const elapsed = performance.now() - start;
        previewTimer = setTimeout(() => updateLatestPreview(epoch),
          document.hidden ? 650 : Math.max(60, PREVIEW_INTERVAL_MS - elapsed));
      }
    }
  }

  function startLatestPreview() {
    if (previewRunning) return;
    if (!previewURL) return;
    previewRunning = true;
    const epoch = ++previewEpoch;
    updateLatestPreview(epoch);
  }

  const SOURCE_KEY = 'bika_live_preferred_source_v1';
  const AUTO_KEY = 'bika_live_auto_connect_v1';
  const CAMO_INDEX_KEY = 'bika_live_camo_index_v1';
  // Browser preferences only; credentials stay on the server.
  function readPreference(key) {
    try { return window.localStorage.getItem(key); } catch (_) { return null; }
  }
  function savePreference(key, value) {
    try { window.localStorage.setItem(key, value); } catch (_) { /* Storage disabled: current page still works. */ }
  }
  const preferredSource = readPreference(SOURCE_KEY);
  stream.value = ['main', 'sub', 'camo'].includes(preferredSource) ? preferredSource : 'main';
  const preferredIndex = readPreference(CAMO_INDEX_KEY);
  if (camoIndex && [...camoIndex.options].some(o => o.value === preferredIndex)) camoIndex.value = preferredIndex;
  if (autoConnectToggle) autoConnectToggle.checked = readPreference(AUTO_KEY) === 'true';
  function isCamoSelected() { return stream.value === 'camo'; }
  function selectedStream() { return isCamoSelected() ? 'camo:' + (camoIndex?.value || '0') : stream.value; }
  function syncCameraSourceUI() {
    const camo = isCamoSelected();
    if (camoSettings) camoSettings.hidden = !camo;
    if (sourceHelper) sourceHelper.textContent = camo
      ? 'Uses Camo Studio virtual webcam on this computer. No RTSP or Hikvision credentials required.'
      : 'Hikvision IP and credentials are read securely from server-side .env.';
    const subtitle = get('[data-source-subtitle]');
    if (subtitle && lastCameraStatus?.state !== 'online') subtitle.textContent = camo
      ? 'iPhone Camera via Camo Studio · USB / Wi-Fi' : 'Hikvision DS-2CD1123G0E-I(L)';
    if (autoConnectToggle) {
      autoConnectToggle.disabled = !authorizedControl || camo;
      if (camo) autoConnectToggle.checked = false;
    }
  }
  syncCameraSourceUI();

  function setMessage(text, isError = false) {
    message.textContent = text;
    message.classList.toggle('is-error', isError);
  }

  page.dataset.liveJsReady = 'true';
  setMessage('Checking camera status…');

  function render(camera) {
    if (!camera) return;
    lastCameraStatus = camera;
    const state = camera.state || 'disconnected';
    const online = state === 'online';
    const connecting = state === 'connecting';
    const error = state === 'error';
    renderTrend(camera, online);
    statusEl.textContent = ({online: 'Online', connecting: 'Connecting', error: 'Connection Error'})[state] || 'Disconnected';
    noteEl.textContent = online ? (camera.source_type === 'local_webcam' ? 'Local webcam feed received' : 'Live RTSP stream received') : connecting ? 'Connecting to selected camera' : error ? 'Check camera source' : 'Camera not connected';
    fpsEl.textContent = camera.camera_fps == null ? '—' : Number(camera.camera_fps).toFixed(1);
    badge.textContent = online ? 'Online' : connecting ? 'Connecting' : error ? 'Error' : 'Offline';
    badge.classList.toggle('is-online', online);
    badge.classList.toggle('is-connecting', connecting);
    badge.classList.toggle('is-error', error);
    onlineDot.classList.toggle('is-online', online);
    liveTag.classList.toggle('is-online', online);
    footDot.classList.toggle('is-online', online);
    liveLabel.textContent = online ? 'LIVE' : connecting ? 'CONNECTING' : error ? 'CONNECTION ERROR' : 'NOT CONNECTED';
    connection.textContent = online ? 'Connected' : connecting ? 'Connecting' : error ? 'Error' : 'Offline';
    resolution.textContent = camera.resolution || '—';
    stageRes.textContent = 'Resolution ' + (camera.resolution || '—');
    stageFPS.textContent = 'FPS ' + (camera.camera_fps == null ? '—' : Number(camera.camera_fps).toFixed(1));
    foot.textContent = online ? 'Camera feed streaming' : connecting ? 'Waiting for first frame' : error ? 'Connection failed' : 'Waiting for camera connection';
    // Current server source is authoritative while online or connecting.
    if (online || connecting) {
      if (camera.source_type === 'local_webcam' || camera.stream?.startsWith('camo:')) {
        stream.value = 'camo';
        const index = String(camera.device_index ?? String(camera.stream).split(':')[1]);
        if (camoIndex && [...camoIndex.options].some(o => o.value === index)) camoIndex.value = index;
      } else if (camera.stream === 'main' || camera.stream === 'sub') stream.value = camera.stream;
    }
    syncCameraSourceUI();
    const camo = (online || connecting) ? camera.source_type === 'local_webcam' : isCamoSelected();
    get('[data-feed-source-label]').textContent = camo ? 'iPhone / Camo' : 'Hikvision';
    get('[data-feed-stream-label]').textContent = camo ? 'Device ' + (online || connecting ? (camera.device_index ?? camoIndex?.value) : camoIndex?.value) :
      ((online || connecting ? camera.stream : stream.value) === 'main' ? 'Main Stream' : 'Sub Stream');
    const infoSource = get('[data-detail-source]');
    if (infoSource) infoSource.textContent = camo ? 'Local Webcam · Camo' : 'RTSP · Hikvision';
    const transport = get('[data-stream-transport]');
    if (transport) transport.textContent = camo ? 'Local camera → latest-frame preview' : 'RTSP → latest-frame preview';
    const subtitle = get('[data-source-subtitle]');
    if (subtitle) subtitle.textContent = camo ? 'iPhone Camera via Camo Studio · USB / Wi-Fi' : 'Hikvision DS-2CD1123G0E-I(L)';
    if (!busy) {
      connectButton.disabled = !authorizedControl || online || connecting;
      disconnectButton.disabled = !authorizedControl || !(online || connecting || error);
      snapshotButton.disabled = !authorizedControl || !camera.snapshot_ready;
    }
    stream.disabled = !authorizedControl || online || connecting;
    if (camoIndex) camoIndex.disabled = !authorizedControl || online || connecting;

    if (online) {
      empty.hidden = true;
      image.hidden = false;
      if (currentStream !== camera.stream) {
        stopLatestPreview();
        currentStream = camera.stream;
      }
      startLatestPreview();
    } else {
      stopLatestPreview();
      image.hidden = true;
      currentStream = null;
      empty.hidden = false;
      emptyTitle.textContent = connecting ? 'Connecting to camera…' : error ? 'Camera connection failed' : 'Camera not connected';
      emptyText.textContent = connecting
        ? 'Waiting for the camera to return its first frame. This can take a few seconds.'
        : error ? (camera.message || 'Check the IP, RTSP settings and network connection.')
        : isCamoSelected() ? 'Open Camo Studio and connect your iPhone, then choose the correct Device Index.'
        : camera.configured ? 'Choose a stream, then click Connect Camera.'
          : 'Set HIKVISION_CAMERA_HOST, USER and PASSWORD in your local .env before connecting.';
    }
    if (currentState !== state) {
      if (error) setMessage(camera.message || 'Camera connection failed.', true);
      else if (online) setMessage('Camera connected. Start Detection when ready. Raw preview stays online during AI inference.');
      else if (connecting) setMessage('Connecting to selected camera…');
      else if (!camera.configured && !isCamoSelected()) setMessage('Hikvision camera is not configured. Update the local .env, or choose iPhone Camera (Camo).', true);
      else setMessage('Camera ready to connect.');
    }
    currentState = state;
  }

  // Phase 2: the raw RTSP preview stays independent of the single 09b worker.
  // AI view is a LAST-ANALYSED KEYFRAME, not masks tracked onto new camera frames.
  const aiImage = get('[data-ai-image]');
  const aiToggle = get('[data-ai-toggle]');
  const aiToggleLabel = get('[data-ai-toggle-label]');
  const aiViewToggle = get('[data-ai-view-toggle]');
  const aiViewState = get('[data-ai-view-state]');
  let aiState = null;
  let aiViewPreference = 'raw'; // Keep the true camera preview as the default; sampled AI images can be seconds old.
  let aiFeedStarted = false;
  let lastEventsSignature = '';
  const aiField = selector => get(selector);

  function paintView() {
    const cameraOnline = lastCameraStatus?.state === 'online';
    const ready = cameraOnline && !!aiState?.active && !!aiState?.overlay_ready;
    const showAI = ready && aiViewPreference === 'ai';
    image.hidden = !cameraOnline || showAI;
    aiImage.hidden = !showAI;
    aiViewToggle.disabled = !ready;
    aiViewToggle.textContent = showAI ? 'Show raw feed' : 'View AI keyframe';
    aiViewState.textContent = showAI ? 'Sampled keyframe · not live' : aiState?.active ? 'Raw camera · AI running' : 'Raw camera';
    // Never label a frozen, previously analysed frame as a live camera image.
    if (cameraOnline) {
      liveLabel.textContent = showAI ? 'AI KEYFRAME · NOT LIVE' : 'LIVE';
    }
    liveTag.classList.toggle('is-ai-frame', showAI);
    if (ready && !aiFeedStarted) {
      aiImage.src = page.dataset.aiFeedUrl + '?t=' + Date.now();
      aiFeedStarted = true;
    }
    if (!ready && aiFeedStarted) {
      aiImage.removeAttribute('src');
      aiFeedStarted = false;
    }
  }
  aiViewToggle?.addEventListener('click', () => {
    aiViewPreference = aiViewPreference === 'ai' ? 'raw' : 'ai';
    paintView();
  });
  aiImage?.addEventListener('error', () => { aiFeedStarted = false; });

  function renderEvents(events) {
    const tbody = aiField('[data-ai-events-body]');
    const signature = JSON.stringify((events || []).map(e => e.id));
    if (signature === lastEventsSignature) return;
    lastEventsSignature = signature;
    tbody.replaceChildren();
    if (!events?.length) {
      const row = tbody.insertRow();
      const cell = row.insertCell();
      cell.colSpan = 5;
      cell.className = 'lsi-no-events';
      cell.textContent = 'No sampled defect candidates yet.';
      return;
    }
    for (const ev of events) {
      const row = tbody.insertRow();
      const timeCell = row.insertCell();
      timeCell.textContent = ev.time || '—';
      const previewCell = row.insertCell();
      const previewUrl = page.dataset.aiEventUrlBase + ev.id + '/image';
      const thumb = document.createElement('img');
      thumb.className = 'lsi-event-thumb';
      thumb.loading = 'lazy';
      thumb.alt = 'Sampled defect preview';
      thumb.src = previewUrl;
      previewCell.append(thumb);
      row.insertCell().textContent = ev.label || 'Defect';
      const conf = Number(ev.confidence);
      row.insertCell().textContent = ev.confidence == null || !Number.isFinite(conf) ? '—' : (conf * 100).toFixed(1) + '%';
      const action = row.insertCell();
      const link = document.createElement('a');
      link.href = previewUrl;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = 'View';
      link.className = 'lsi-event-link';
      action.append(link);
    }
  }

  function renderAI(ai, camera) {
    aiState = ai || {state: 'stopped'};
    const active = !!aiState.active;
    const online = camera?.state === 'online';
    aiToggle.disabled = !authorizedControl || busy || (!online && !active);
    aiToggleLabel.textContent = active ? 'Stop Detection' : aiState.state === 'error' ? 'Restart Detection' : 'Start Detection';
    aiToggle.title = active ? 'Stop the AI sampler; keep the camera online' : 'Start sampled 09b inference on live keyframes';
    aiToggle.classList.toggle('is-active', active);
    aiField('[data-ai-state]').textContent = aiState.state === 'error' ? 'Error' :
      active ? (aiState.stage || 'Running') : 'Stopped';
    aiField('[data-detail-ai]').textContent = active ? 'Running · sampled keyframes' : 'Stopped';
    aiField('[data-ai-fps]').textContent = aiState.ai_fps == null ? '—' : `${Number(aiState.ai_fps).toFixed(2)} FPS`;
    aiField('[data-ai-inference]').textContent = aiState.inference_seconds == null ? '—' : `${Number(aiState.inference_seconds).toFixed(2)} s`;
    let age = '—';
    if (aiState.last_sample_at) {
      const diff = (Date.now() - Date.parse(aiState.last_sample_at)) / 1000;
      if (Number.isFinite(diff)) age = `${Math.max(0, Math.round(diff))} s ago`;
    }
    aiField('[data-ai-keyframe-age]').textContent = age;
    aiField('[data-stat-samples]').textContent = aiState.sample_count ? String(aiState.sample_count) : '—';
    aiField('[data-stat-reject]').textContent = aiState.sampled_reject_rate == null ? '—' : `${Number(aiState.sampled_reject_rate).toFixed(1)}%`;
    aiField('[data-ai-events-badge]').textContent = active ? 'Collecting keyframes' : aiState.event_total ? 'Last session' : 'Not collecting';
    const events = aiState.events || [];
    renderEvents(events);
    aiField('[data-ai-alert-badge]').textContent = !active ? 'Waiting' : events.length ? `${events.length} candidates` : 'Monitoring';
    aiField('[data-ai-alert-text]').textContent = aiState.state === 'error' ? (aiState.message || 'AI error') :
      !active ? 'Start AI to monitor sampled defects.' : events.length ?
      `${events.length} possible defect events in this session. Manual verification required.` :
      'No sampled defect candidates yet. AI is analysing available keyframes.';
    aiField('[data-ai-distribution-badge]').textContent = events.length ? 'Sampled events' : 'No data';
    const categories = new Map();
    for (const ev of events) categories.set(ev.label, (categories.get(ev.label) || 0) + 1);
    aiField('[data-ai-ring-total]').textContent = events.length ? String(events.length) : '—';
    aiField('[data-ai-distribution-text]').textContent = categories.size ?
      [...categories.entries()].map(([label, count]) => `${label}: ${count}`).join(' · ') + '. Sampled candidates; not unique products.' :
      'Waiting for sampled defect events; not unique products.';
    paintView();
    if (aiState.state === 'error' && aiState.message) setMessage(aiState.message, true);
  }

  aiToggle?.addEventListener('click', async () => {
    if (!authorizedControl || busy) return;
    const url = aiState?.active ? page.dataset.aiStopUrl : page.dataset.aiStartUrl;
    if (!url) return;
    await action(url);
  });

  async function checkStatus() {
    try {
      const response = await fetch(page.dataset.statusUrl, {credentials:'same-origin', cache:'no-store', headers: {'Accept':'application/json'}});
      if (!response.ok) throw new Error('Camera status HTTP ' + response.status + '. Check Flask login/session.');
      const data = await response.json();
      render(data.camera);
      renderAI(data.ai, data.camera);
      return data.camera;
    } catch (err) {
      setMessage('Camera status request failed: ' + (err.message || 'Check Flask / browser Console.'), true);
      return null;
    }
  }

  async function action(url, payload = {}) {
    if (busy) return;
    busy = true;
    connectButton.disabled = true;
    disconnectButton.disabled = true;
    try {
      const response = await fetch(url, {
        method:'POST', credentials:'same-origin',
        headers: {'Content-Type':'application/json', 'Accept':'application/json', 'X-CSRFToken':csrf},
        body: JSON.stringify(payload)
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        throw new Error(data.message || (response.status === 403 ? 'Admin permission or CSRF authorization required.' : 'Camera request failed.'));
      }
      if (data.message) setMessage(data.message);
      render(data.camera);
      return data.camera;
    } catch (err) {
      setMessage(err.message || 'Unexpected network error.', true);
    } finally {
      busy = false;
      await checkStatus();
    }
  }

// Hardware CUDA availability is distinct from active, sampled AI inference.
const cudaState = get('[data-live-cuda]');
async function checkCudaSupport() {
  if (!page.dataset.deviceStatusUrl || !cudaState) return;
  try {
    const response = await fetch(page.dataset.deviceStatusUrl, {
      credentials: 'same-origin', cache: 'no-store',
      headers: {'Accept': 'application/json'},
    });
    if (!response.ok) throw new Error('Device status unavailable');
    const data = await response.json();
    cudaState.textContent = data.models?.cuda_available == null ? 'Unknown' : (data.models.cuda_available ? 'Available' : 'Unavailable');
    cudaState.title = data.models?.cuda_name || 'CUDA availability does not mean live AI is running.';
  } catch (_) {
    cudaState.textContent = 'Unavailable';
  }
}
checkCudaSupport();
const cudaRefreshInterval = setInterval(checkCudaSupport, 6000);
window.addEventListener('pagehide', () => clearInterval(cudaRefreshInterval), {once:true});

  // Auto-connect never starts AI: operator must click Start Detection.
  function canAutoConnect(camera) {
    return authorizedControl && !busy && autoConnectToggle?.checked &&
      stream.value !== 'camo' && camera?.configured && camera.state === 'disconnected';
  }

  stream?.addEventListener('change', () => {
    savePreference(SOURCE_KEY, stream.value);
    syncCameraSourceUI();
    if (lastCameraStatus && lastCameraStatus.state === 'disconnected') {
      render(lastCameraStatus);
      setMessage(isCamoSelected() ? 'Open Camo Studio, choose the correct local device, then Connect Camera.' : 'Select Hikvision stream and Connect Camera.');
    }
  });
  camoIndex?.addEventListener('change', () => {
    savePreference(CAMO_INDEX_KEY, camoIndex.value);
    if (lastCameraStatus && lastCameraStatus.state === 'disconnected') render(lastCameraStatus);
  });

  autoConnectToggle?.addEventListener('change', () => {
    savePreference(AUTO_KEY, autoConnectToggle.checked ? 'true' : 'false');
    // Enabling the switch can connect now; disabling it does NOT interrupt an active stream.
    if (canAutoConnect(lastCameraStatus)) action(page.dataset.connectUrl, {stream: selectedStream()});
  });

  connectButton?.addEventListener('click', () => action(page.dataset.connectUrl, {stream:selectedStream()}));
  disconnectButton?.addEventListener('click', () => action(page.dataset.disconnectUrl));
  snapshotButton?.addEventListener('click', () => {
    // Browser download; server's protected endpoint verifies role again.
    window.location.assign(page.dataset.snapshotUrl);
  });
  image?.addEventListener('error', () => {
    if (currentState === 'online') setMessage('Unable to decode the latest camera frame. Check the camera codec and network.', true);
  });
  (async () => {
    const camera = await checkStatus();
    if (canAutoConnect(camera)) {
      await action(page.dataset.connectUrl, {stream: selectedStream()});
    }
  })();
  const interval = setInterval(checkStatus, 1600);
  window.addEventListener('pagehide', () => { clearInterval(interval); stopLatestPreview(); }, {once:true});
})();
