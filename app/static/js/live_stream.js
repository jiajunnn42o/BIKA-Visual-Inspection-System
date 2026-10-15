/* BIKA Live Stream Inspection · camera-only Phase 1. No fake AI results. */
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
  const SOURCE_KEY = 'bika_live_preferred_source_v1';
  const AUTO_KEY = 'bika_live_auto_connect_v1';
  // Browser preferences only; credentials stay on the server.
  function readPreference(key) {
    try { return window.localStorage.getItem(key); } catch (_) { return null; }
  }
  function savePreference(key, value) {
    try { window.localStorage.setItem(key, value); } catch (_) { /* Storage disabled: current page still works. */ }
  }
  const preferredSource = readPreference(SOURCE_KEY);
  stream.value = preferredSource === 'sub' ? 'sub' : 'main';
  if (autoConnectToggle) autoConnectToggle.checked = readPreference(AUTO_KEY) === 'true';

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
    noteEl.textContent = online ? 'Live RTSP stream received' : connecting ? 'Attempting RTSP connection' : error ? 'Check camera configuration' : 'Camera not connected';
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
    // While connected the hardware's current stream is authoritative.
    if ((online || connecting) && (camera.stream === 'main' || camera.stream === 'sub')) {
      stream.value = camera.stream;
    }
    const displayedStream = (online || connecting) ? camera.stream : stream.value;
    get('[data-feed-stream-label]').textContent = displayedStream === 'main' ? 'Main Stream' : 'Sub Stream';
    if (!busy) {
      connectButton.disabled = !authorizedControl || online || connecting;
      disconnectButton.disabled = !authorizedControl || !(online || connecting || error);
      snapshotButton.disabled = !authorizedControl || !camera.snapshot_ready;
    }
    stream.disabled = !authorizedControl || online || connecting;

    if (online) {
      empty.hidden = true;
      image.hidden = false;
      if (currentStream !== camera.stream || !image.getAttribute('src')) {
        image.src = page.dataset.videoUrl + '?stream=' + encodeURIComponent(camera.stream);
        currentStream = camera.stream;
      }
    } else {
      image.removeAttribute('src');
      image.hidden = true;
      currentStream = null;
      empty.hidden = false;
      emptyTitle.textContent = connecting ? 'Connecting to camera…' : error ? 'Camera connection failed' : 'Camera not connected';
      emptyText.textContent = connecting
        ? 'Waiting for the camera to return its first frame. This can take a few seconds.'
        : error ? (camera.message || 'Check the IP, RTSP settings and network connection.')
        : camera.configured ? 'Choose a stream, then click Connect Camera.'
          : 'Set HIKVISION_CAMERA_HOST, USER and PASSWORD in your local .env before connecting.';
    }
    if (currentState !== state) {
      if (error) setMessage(camera.message || 'Camera connection failed.', true);
      else if (online) setMessage('Camera connected. You may capture a snapshot; AI inference is not active.');
      else if (connecting) setMessage('Connecting to Hikvision camera…');
      else if (!camera.configured) setMessage('Camera is not configured. Please update the local .env file.', true);
      else setMessage('Camera ready to connect.');
    }
    currentState = state;
  }

  async function checkStatus() {
    try {
      const response = await fetch(page.dataset.statusUrl, {credentials:'same-origin', cache:'no-store', headers: {'Accept':'application/json'}});
      if (!response.ok) throw new Error('Camera status HTTP ' + response.status + '. Check Flask login/session.');
      const data = await response.json();
      render(data.camera);
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

  // Auto-connect only after the first successful status response. Never run AI inference.
  function canAutoConnect(camera) {
    return authorizedControl && !busy && autoConnectToggle?.checked &&
      camera?.configured && camera.state === 'disconnected';
  }

  stream?.addEventListener('change', () => {
    savePreference(SOURCE_KEY, stream.value);
    if (lastCameraStatus && lastCameraStatus.state === 'disconnected') {
      get('[data-feed-stream-label]').textContent = stream.value === 'main' ? 'Main Stream' : 'Sub Stream';
    }
  });

  autoConnectToggle?.addEventListener('change', () => {
    savePreference(AUTO_KEY, autoConnectToggle.checked ? 'true' : 'false');
    // Enabling the switch can connect now; disabling it does NOT interrupt an active stream.
    if (canAutoConnect(lastCameraStatus)) action(page.dataset.connectUrl, {stream: stream.value});
  });

  connectButton?.addEventListener('click', () => action(page.dataset.connectUrl, {stream:stream.value}));
  disconnectButton?.addEventListener('click', () => action(page.dataset.disconnectUrl));
  snapshotButton?.addEventListener('click', () => {
    // Browser download; server's protected endpoint verifies role again.
    window.location.assign(page.dataset.snapshotUrl);
  });
  image?.addEventListener('error', () => {
    if (currentState === 'online') setMessage('Unable to display the MJPEG preview. Check codec and network stability.', true);
  });
  (async () => {
    const camera = await checkStatus();
    if (canAutoConnect(camera)) {
      await action(page.dataset.connectUrl, {stream: stream.value});
    }
  })();
  const interval = setInterval(checkStatus, 1600);
  window.addEventListener('pagehide', () => clearInterval(interval), {once:true});
})();
