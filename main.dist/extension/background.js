/**
 * Flow Extension — Chrome Extension Background Service Worker
 *
 * Connects to local Python agent via WebSocket (agent runs WS server).
 * Captures bearer token, solves reCAPTCHA, proxies API calls through browser.
 */

const AGENT_WS_URL = 'ws://127.0.0.1:9222';
const AGENT_CALLBACK_URL = 'http://127.0.0.1:8100/api/ext/callback';
const HEARTBEAT_INTERVAL_MS = 15000;
// NOTE: This is a browser-restricted public API key — safe to ship in extension bundles.
const API_KEY = 'AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY';

let ws = null;
let flowKey = null;
let callbackSecret = null;  // Auth secret for HTTP callback, received from server on WS connect
let extensionId = null;
let profileHint = null;
let browserLabel = '';
let accountEmail = '';
let agentConnectionId = '';
let heartbeatTimer = null;
let sessionRescanTimer = null;
let accountEmailFetchedAt = 0;
let state = 'off'; // off | idle | running
let manualDisconnect = false;
let metrics = {
  tokenCapturedAt: null,
  requestCount: 0,   // captcha-consuming requests only (gen image/video/upscale)
  successCount: 0,
  failedCount: 0,
  lastError: null,
};

const EXTENSION_CAPABILITIES = [
  'api_request',
  'trpc_request',
  'solve_captcha',
  'refresh_token',
  'media_urls_refresh',
  'upload_video_start',
  'upload_video_chunk',
  'get_status',
];

// ─── URL → Log Type Classifier ─────────────────────────────

// Visible log types — only these appear in the request log
const _VISIBLE_TYPES = new Set(['GEN_IMG', 'GEN_VID', 'GEN_VID_REF', 'UPSCALE', 'TRACKING', 'URL_REFRESH']);

function _classifyApiUrl(url) {
  if (url.includes('uploadImage'))                     return 'UPLOAD';
  if (url.includes('batchGenerateImages'))              return 'GEN_IMG';
  if (url.includes('UpsampleVideo'))                   return 'UPSCALE';
  if (url.includes('ReferenceImages'))                 return 'GEN_VID_REF';
  if (url.includes('batchAsyncGenerateVideo'))          return 'GEN_VID';
  if (url.includes('batchCheckAsync'))                  return 'POLL';
  if (url.includes('upsampleImage'))                   return 'UPS_IMG';
  if (url.includes('/media/'))                         return 'MEDIA';
  if (url.includes('/credits'))                        return 'CREDITS';
  return 'API';
}

function _safeStringify(value) {
  try {
    return typeof value === 'string' ? value : JSON.stringify(value);
  } catch {
    return String(value || '');
  }
}

function _extractApiErrorMeta(payload) {
  const base = (payload && typeof payload === 'object' && payload.data && typeof payload.data === 'object')
    ? payload.data
    : payload;
  const errorBlock = (base && typeof base === 'object' && base.error && typeof base.error === 'object')
    ? base.error
    : null;
  const source = errorBlock || (base && typeof base === 'object' ? base : null);
  const message = typeof source?.message === 'string'
    ? source.message
    : typeof base === 'string'
      ? base
      : '';
  const details = Array.isArray(source?.details) ? source.details : [];
  const reasons = details
    .map((item) => (item && typeof item.reason === 'string' ? item.reason : ''))
    .filter(Boolean);
  const blob = _safeStringify(payload).slice(0, 2000);
  return { message, reasons, blob };
}

function _classify403(payload, fallbackError = '') {
  const meta = _extractApiErrorMeta(payload);
  const haystack = `${fallbackError} ${meta.message} ${meta.reasons.join(' ')} ${meta.blob}`.toLowerCase();

  if (haystack.includes('captcha') || haystack.includes('recaptcha')) {
    return 'CAPTCHA_403';
  }
  if (
    haystack.includes('public_error_unsafe_generation') ||
    haystack.includes('unsafe') ||
    haystack.includes('safety') ||
    haystack.includes('policy') ||
    haystack.includes('prohibited') ||
    haystack.includes('violates')
  ) {
    return 'POLICY_403';
  }
  if (
    haystack.includes('paygate') ||
    haystack.includes('tier') ||
    haystack.includes('subscription') ||
    haystack.includes('not entitled') ||
    haystack.includes('upgrade')
  ) {
    return 'TIER_403';
  }
  if (
    haystack.includes('invalid authentication credentials') ||
    haystack.includes('request had invalid authentication credentials') ||
    haystack.includes('authorization') ||
    haystack.includes('access token') ||
    haystack.includes('oauth') ||
    haystack.includes('credential') ||
    haystack.includes('unauthenticated') ||
    haystack.includes('login required') ||
    haystack.includes('session expired') ||
    haystack.includes('token expired')
  ) {
    return 'AUTH_403';
  }
  return 'API_403';
}

// ─── Request Log ────────────────────────────────────────────

let requestLog = [];

function addRequestLog(entry) {
  requestLog.unshift(entry);
  if (requestLog.length > 100) requestLog.pop();
  broadcastRequestLog();
}

function updateRequestLog(id, updates) {
  const entry = requestLog.find((e) => e.id === id);
  if (entry) Object.assign(entry, updates);
  broadcastRequestLog();
}

function broadcastRequestLog() {
  chrome.runtime.sendMessage({ type: 'REQUEST_LOG_UPDATE', log: requestLog }).catch(() => {});
}

function _normalizeLogContextValue(value) {
  return String(value || '').trim();
}

function _normalizeLogContext(msg) {
  const ctx = msg?.params?.logContext && typeof msg.params.logContext === 'object'
    ? msg.params.logContext
    : {};
  return {
    requestId: _normalizeLogContextValue(ctx.requestId),
    sceneId: _normalizeLogContextValue(ctx.sceneId),
    projectId: _normalizeLogContextValue(ctx.projectId),
    videoId: _normalizeLogContextValue(ctx.videoId),
    requestType: _normalizeLogContextValue(ctx.requestType),
    targetAccountEmail: _normalizeLogContextValue(ctx.targetAccountEmail).toLowerCase(),
    connectionId: _normalizeLogContextValue(ctx.connectionId || msg?.connectionId || agentConnectionId),
  };
}

function clearRequestLogEntries(filters = {}) {
  const clearAll = !!filters.clear_all;
  const requestIds = new Set((filters.request_ids || []).map((value) => _normalizeLogContextValue(value)).filter(Boolean));
  const sceneIds = new Set((filters.scene_ids || []).map((value) => _normalizeLogContextValue(value)).filter(Boolean));
  const projectId = _normalizeLogContextValue(filters.project_id);
  const videoId = _normalizeLogContextValue(filters.video_id);
  if (!clearAll && !requestIds.size && !sceneIds.size && !projectId && !videoId) {
    return 0;
  }

  const before = requestLog.length;
  requestLog = requestLog.filter((entry) => {
    if (clearAll) return false;
    const entryRequestId = _normalizeLogContextValue(entry?.requestId);
    const entrySceneId = _normalizeLogContextValue(entry?.sceneId);
    const entryProjectId = _normalizeLogContextValue(entry?.projectId);
    const entryVideoId = _normalizeLogContextValue(entry?.videoId);
    if (entryRequestId && requestIds.has(entryRequestId)) return false;
    if (entrySceneId && sceneIds.has(entrySceneId)) return false;
    if (projectId && entryProjectId && entryProjectId === projectId) return false;
    if (videoId && entryVideoId && entryVideoId === videoId) return false;
    return true;
  });
  const cleared = Math.max(0, before - requestLog.length);
  if (cleared > 0) {
    broadcastRequestLog();
  }
  return cleared;
}

function newUuid() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function detectBrowserLabel() {
  const brands = navigator.userAgentData?.brands || [];
  const brandText = brands.map((entry) => String(entry?.brand || '')).join(' ').toLowerCase();
  const ua = String(navigator.userAgent || '').toLowerCase();
  if (brandText.includes('microsoft edge') || ua.includes('edg/')) return 'Microsoft Edge';
  if (brandText.includes('opera') || ua.includes('opr/')) return 'Opera';
  if (brandText.includes('brave') || ua.includes('brave')) return 'Brave';
  if (brandText.includes('chromium')) return 'Chromium';
  return 'Google Chrome';
}

async function getFlowTabs() {
  return await chrome.tabs.query({
    url: ['https://labs.google/fx/tools/flow*', 'https://labs.google/fx/*/tools/flow*'],
  });
}

async function getReadyFlowTab() {
  const tabs = await getFlowTabs();
  const tab = tabs.find((entry) => typeof entry?.id === 'number') || null;
  return {
    active_tab_ready: !!tab,
    ready_tab_id: tab?.id ?? null,
  };
}

async function refreshAccountEmail(force = false) {
  if (!flowKey) {
    accountEmail = '';
    accountEmailFetchedAt = 0;
    return '';
  }
  const age = Date.now() - (accountEmailFetchedAt || 0);
  if (!force && accountEmail && age < 60000) {
    return accountEmail;
  }
  try {
    const resp = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
      method: 'GET',
      headers: {
        authorization: `Bearer ${flowKey}`,
        accept: 'application/json',
      },
    });
    if (!resp.ok) {
      throw new Error(`USERINFO_${resp.status}`);
    }
    const data = await resp.json();
    accountEmail = String(data?.email || '').trim().toLowerCase();
    accountEmailFetchedAt = Date.now();
    await chrome.storage.local.set({
      accountEmail,
      accountEmailFetchedAt,
    });
    return accountEmail;
  } catch (error) {
    console.warn('[FlowAgent] Failed to refresh account email:', error);
    return accountEmail || '';
  }
}

async function buildSessionSnapshot(forceAccountRefresh = false) {
  if (forceAccountRefresh) {
    await refreshAccountEmail(true);
  } else if (flowKey && !accountEmail) {
    await refreshAccountEmail(false);
  }
  const flowTab = await getReadyFlowTab();
  return {
    extension_id: extensionId,
    account_email: accountEmail || '',
    browser_label: browserLabel,
    profile_hint: profileHint,
    capabilities: EXTENSION_CAPABILITIES,
    flowKeyPresent: !!flowKey,
    active_tab_ready: !!flowTab.active_tab_ready,
    ready_tab_id: flowTab.ready_tab_id,
    extension_version: chrome.runtime.getManifest().version,
    tokenAge: flowKey && metrics.tokenCapturedAt ? Date.now() - metrics.tokenCapturedAt : null,
    ready: !!flowTab.active_tab_ready,
  };
}

async function sendSessionSnapshot(type = 'session_heartbeat', options = {}) {
  if (ws?.readyState !== WebSocket.OPEN) return;
  const snapshot = await buildSessionSnapshot(!!options.forceAccountRefresh);
  ws.send(JSON.stringify({
    type,
    connectionId: agentConnectionId || undefined,
    ...snapshot,
  }));
}

function isFlowTabUrl(url) {
  const value = String(url || '').toLowerCase();
  return value.includes('https://labs.google/fx/tools/flow') || value.includes('/tools/flow');
}

function scheduleSessionRescan(reason = '') {
  if (sessionRescanTimer) {
    clearTimeout(sessionRescanTimer);
  }
  sessionRescanTimer = setTimeout(async () => {
    sessionRescanTimer = null;
    connectToAgent();
    try {
      await sendSessionSnapshot('session_heartbeat', { forceAccountRefresh: false });
    } catch {}
    try {
      const flowTab = await getReadyFlowTab();
      if (flowTab.active_tab_ready) {
        await captureTokenFromFlowTab();
      }
    } catch (error) {
      console.warn('[FlowAgent] Session rescan failed:', reason, error);
    }
  }, 250);
}

function startHeartbeat() {
  stopHeartbeat();
  heartbeatTimer = setInterval(() => {
    void sendSessionSnapshot('session_heartbeat');
  }, HEARTBEAT_INTERVAL_MS);
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

async function notifyAgentFlowKeyCaptured() {
  if (ws?.readyState !== WebSocket.OPEN || !flowKey) return;
  await refreshAccountEmail(true).catch(() => {});
  await sendSessionSnapshot('session_heartbeat', { forceAccountRefresh: false });
  ws.send(JSON.stringify({
    type: 'token_captured',
    flowKey,
    connectionId: agentConnectionId || undefined,
    extension_id: extensionId,
    account_email: accountEmail || '',
    browser_label: browserLabel,
    profile_hint: profileHint,
    flowKeyPresent: true,
  }));
}

async function applyCapturedFlowKey(token, source = 'capture') {
  const clean = String(token || '').replace(/^Bearer\s+/i, '').trim();
  if (!/^ya29\./.test(clean)) return false;
  flowKey = clean;
  metrics.tokenCapturedAt = Date.now();
  metrics.lastError = null;
  await chrome.storage.local.set({ flowKey, metrics });
  console.log(`[FlowAgent] Bearer token captured via ${source}`);
  await notifyAgentFlowKeyCaptured();
  broadcastStatus();
  return true;
}

async function waitForFlowKey(timeoutMs = 4000) {
  if (flowKey) return true;
  const started = Date.now();
  while (!flowKey && (Date.now() - started) < timeoutMs) {
    await sleep(250);
  }
  return !!flowKey;
}

async function warmupFlowAuthOnTab(tabId) {
  if (!tabId) return;
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      world: 'MAIN',
      func: async (apiKey) => {
        try {
          await fetch(`https://aisandbox-pa.googleapis.com/v1/credits?key=${apiKey}`, {
            method: 'GET',
            credentials: 'include',
            headers: { accept: 'application/json' },
          });
        } catch {}
      },
      args: [API_KEY],
    });
  } catch (e) {
    console.warn('[FlowAgent] Flow auth warmup failed:', e);
  }
}

// ─── Startup ────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(init);
chrome.runtime.onStartup.addListener(init);
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'reconnect') connectToAgent();
  if (alarm.name === 'keepAlive') keepAlive();
  if (alarm.name === 'token-refresh') {
    await captureTokenFromFlowTab();
  }
  if (alarm.name === 'session-sync') {
    await sendSessionSnapshot('session_heartbeat');
  }
});

async function init() {
  const data = await chrome.storage.local.get([
    'flowKey',
    'metrics',
    'callbackSecret',
    'extensionId',
    'profileHint',
    'accountEmail',
    'accountEmailFetchedAt',
  ]);
  if (data.flowKey) flowKey = data.flowKey;
  if (data.metrics) Object.assign(metrics, data.metrics);
  if (data.callbackSecret) callbackSecret = data.callbackSecret;
  extensionId = String(data.extensionId || newUuid());
  profileHint = String(data.profileHint || extensionId.slice(0, 8));
  browserLabel = detectBrowserLabel();
  accountEmail = String(data.accountEmail || '').trim().toLowerCase();
  accountEmailFetchedAt = Number(data.accountEmailFetchedAt || 0) || 0;
  await chrome.storage.local.set({ extensionId, profileHint });
  connectToAgent();
  scheduleSessionRescan('init');
  chrome.alarms.create('keepAlive', { periodInMinutes: 0.4 });
  chrome.alarms.create('session-sync', { periodInMinutes: 0.25 });
}

// ─── Token Capture ──────────────────────────────────────────

chrome.webRequest.onBeforeSendHeaders.addListener(
  (details) => {
    if (!details?.requestHeaders?.length) return;
    const authHeader = details.requestHeaders.find(
      (h) => h.name?.toLowerCase() === 'authorization',
    );
    const value = authHeader?.value || '';
    if (!value.startsWith('Bearer ya29.')) return;

    const token = value.replace(/^Bearer\s+/i, '').trim();
    if (!token) return;

    void applyCapturedFlowKey(token, 'webRequest');
  },
  { urls: ['https://aisandbox-pa.googleapis.com/*', 'https://labs.google/*'] },
  ['requestHeaders', 'extraHeaders'],
);

let _openingFlowTab = false;

async function captureTokenFromFlowTab() {
  const tabs = await chrome.tabs.query({
    url: ['https://labs.google/fx/tools/flow*', 'https://labs.google/fx/*/tools/flow*'],
  });
  if (!tabs.length) {
    if (_openingFlowTab) {
      console.log('[FlowAgent] Flow tab already opening, skipping');
      return;
    }
    _openingFlowTab = true;
    try {
      console.log('[FlowAgent] No Flow tab found — opening one in background');
      await chrome.tabs.create({ url: 'https://labs.google/fx/tools/flow', active: false });
      await sleep(3000);
      const retryTabs = await chrome.tabs.query({
        url: ['https://labs.google/fx/tools/flow*', 'https://labs.google/fx/*/tools/flow*'],
      });
      if (!retryTabs.length) {
        console.log('[FlowAgent] Flow tab not ready yet after open');
        return;
      }
      await chrome.scripting.executeScript({
        target: { tabId: retryTabs[0].id },
        files: ['content.js'],
      });
      await warmupFlowAuthOnTab(retryTabs[0].id);
      await waitForFlowKey(4000);
      console.log('[FlowAgent] Token refresh triggered on newly opened Flow tab');
    } catch (e) {
      console.error('[FlowAgent] Token refresh failed after opening tab:', e);
    } finally {
      _openingFlowTab = false;
    }
    return;
  }
  try {
    await chrome.scripting.executeScript({
      target: { tabId: tabs[0].id },
      files: ['content.js'],
    });
    await warmupFlowAuthOnTab(tabs[0].id);
    await waitForFlowKey(4000);
    console.log('[FlowAgent] Token refresh triggered on Flow tab');
  } catch (e) {
    console.error('[FlowAgent] Token refresh failed:', e);
  }
}

// ─── WebSocket to Agent ─────────────────────────────────────

function connectToAgent() {
  if (manualDisconnect) return;
  if (ws?.readyState === WebSocket.CONNECTING) return;
  if (ws?.readyState === WebSocket.OPEN) return;

  try {
    ws = new WebSocket(AGENT_WS_URL);
  } catch (e) {
    console.error('[FlowAgent] WS connect error:', e);
    scheduleReconnect();
    return;
  }

  ws.onopen = () => {
    console.log('[FlowAgent] Connected to agent');
    chrome.alarms.clear('reconnect');
    setState('idle');
    startHeartbeat();

    // Token refresh alarm — 45 min gives buffer before ~60 min expiry
    chrome.alarms.create('token-refresh', { periodInMinutes: 45 });

    // Send current state + resend token if we have one
    void sendSessionSnapshot('extension_ready', { forceAccountRefresh: true });
    if (flowKey) {
      void notifyAgentFlowKeyCaptured();
    } else {
      void captureTokenFromFlowTab();
    }
  };

  ws.onmessage = async ({ data }) => {
    try {
      const msg = JSON.parse(data);

      if (msg.method === 'api_request') {
        await handleApiRequest(msg);
      } else if (msg.method === 'trpc_request') {
        await handleTrpcRequest(msg);
      } else if (msg.method === 'solve_captcha') {
        await handleSolveCaptcha(msg);
      } else if (msg.method === 'refresh_token') {
        await handleRefreshToken(msg);
      } else if (msg.method === 'upload_video_start') {
        await handleUploadVideoStart(msg);
      } else if (msg.method === 'upload_video_chunk') {
        await handleUploadVideoChunk(msg);
      } else if (msg.method === 'clear_request_log') {
        await handleClearRequestLog(msg);
      } else if (msg.method === 'get_status') {
        const snapshot = await buildSessionSnapshot(false);
        sendToAgent({
          id: msg.id,
          result: {
            state,
            manualDisconnect,
            ...snapshot,
            metrics,
          },
        });
      } else if (msg.type === 'callback_secret') {
        callbackSecret = msg.secret;
        agentConnectionId = String(msg.connectionId || '').trim();
        chrome.storage.local.set({ callbackSecret: msg.secret });
        console.log('[FlowAgent] Received callback secret');
        void sendSessionSnapshot('session_heartbeat');
      } else if (msg.type === 'pong') {
        // keepalive response
      }
    } catch (e) {
      console.error('[FlowAgent] Message error:', e);
    }
  };

  ws.onclose = () => {
    setState('off');
    stopHeartbeat();
    chrome.alarms.clear('token-refresh');
    agentConnectionId = '';
    if (!manualDisconnect) scheduleReconnect();
  };

  ws.onerror = (e) => {
    console.error('[FlowAgent] WS error:', e);
    metrics.lastError = 'WS_ERROR';
    chrome.storage.local.set({ metrics });
  };
}

function scheduleReconnect() {
  chrome.alarms.create('reconnect', { delayInMinutes: 0.083 }); // ~5s
}

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  const tabUrl = String(changeInfo?.url || tab?.url || '');
  if (!isFlowTabUrl(tabUrl)) return;
  if (changeInfo?.url || changeInfo?.status === 'complete') {
    scheduleSessionRescan('tabs.onUpdated');
  }
});

chrome.tabs.onActivated.addListener(() => {
  scheduleSessionRescan('tabs.onActivated');
});

chrome.tabs.onRemoved.addListener(() => {
  scheduleSessionRescan('tabs.onRemoved');
});

function keepAlive() {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'ping', connectionId: agentConnectionId || undefined }));
  } else {
    connectToAgent();
  }
}

function sendToAgent(msg) {
  const payload = {
    ...(msg || {}),
    connectionId: msg?.connectionId || agentConnectionId || undefined,
  };
  // API responses (with msg.id) go via HTTP — immune to WS disconnect
  if (payload.id) {
    const headers = { 'Content-Type': 'application/json' };
    if (callbackSecret) headers['X-Callback-Secret'] = callbackSecret;
    if (agentConnectionId) headers['X-Connection-Id'] = agentConnectionId;
    fetch(AGENT_CALLBACK_URL, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    }).catch(() => {
      // HTTP failed — fallback to WS
      if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(payload));
    });
    return;
  }
  // Non-response messages (ping, status) or no secret yet — use WS
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(payload));
  }
}

// ─── reCAPTCHA Solving ──────────────────────────────────────

async function requestCaptchaFromTab(tabId, requestId, pageAction) {
  try {
    return await chrome.tabs.sendMessage(tabId, {
      type: 'GET_CAPTCHA',
      requestId,
      pageAction,
    });
  } catch (error) {
    const msg = error?.message || '';
    const shouldInject =
      msg.includes('Receiving end does not exist') ||
      msg.includes('Could not establish connection');
    if (!shouldInject) throw error;

    // Inject content script and retry
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ['content.js'],
    });
    await sleep(200);
    return await chrome.tabs.sendMessage(tabId, {
      type: 'GET_CAPTCHA',
      requestId,
      pageAction,
    });
  }
}

async function solveCaptcha(requestId, captchaAction) {
  const tabs = await chrome.tabs.query({
    url: ['https://labs.google/fx/tools/flow*', 'https://labs.google/fx/*/tools/flow*'],
  });

  if (!tabs.length) {
    // Auto-open Flow tab and wait briefly before returning error
    try {
      await chrome.tabs.create({ url: 'https://labs.google/fx/tools/flow', active: false });
      await sleep(3000);
      // Retry tab query after opening
      const retryTabs = await chrome.tabs.query({
        url: ['https://labs.google/fx/tools/flow*', 'https://labs.google/fx/*/tools/flow*'],
      });
      if (!retryTabs.length) return { error: 'NO_FLOW_TAB' };
      const resp = await Promise.race([
        requestCaptchaFromTab(retryTabs[0].id, requestId, captchaAction),
        new Promise((_, rej) => setTimeout(() => rej(new Error('CAPTCHA_TIMEOUT')), 30000)),
      ]);
      return resp;
    } catch (e) {
      return { error: e.message || 'NO_FLOW_TAB' };
    }
  }

  try {
    const resp = await Promise.race([
      requestCaptchaFromTab(tabs[0].id, requestId, captchaAction),
      new Promise((_, rej) => setTimeout(() => rej(new Error('CAPTCHA_TIMEOUT')), 30000)),
    ]);
    return resp;
  } catch (e) {
    return { error: e.message };
  }
}

async function handleSolveCaptcha(msg) {
  const { id, params } = msg;
  const result = await solveCaptcha(id, params?.captchaAction || 'VIDEO_GENERATION');

  // Standalone captcha solve counts as captcha-consuming
  metrics.requestCount++;
  if (result?.token) {
    metrics.successCount++;
  } else {
    metrics.failedCount++;
    metrics.lastError = result?.error || 'NO_TOKEN';
  }
  chrome.storage.local.set({ metrics });

  sendToAgent({ id, result });
}

async function handleRefreshToken(msg) {
  const { id } = msg;
  try {
    await captureTokenFromFlowTab();
    const hasKey = await waitForFlowKey(8000);
    await refreshAccountEmail(false);
    sendToAgent({
      id,
      result: {
        ok: hasKey,
        flowKeyPresent: !!flowKey,
        account_email: accountEmail || '',
        tokenAge: metrics.tokenCapturedAt ? Date.now() - metrics.tokenCapturedAt : null,
      },
    });
  } catch (error) {
    sendToAgent({ id, error: error?.message || 'TOKEN_REFRESH_FAILED' });
  }
}

async function handleClearRequestLog(msg) {
  const { id, params } = msg;
  try {
    const cleared = clearRequestLogEntries(params || {});
    sendToAgent({ id, result: { ok: true, cleared } });
  } catch (error) {
    sendToAgent({ id, error: error?.message || 'REQUEST_LOG_CLEAR_FAILED' });
  }
}

function decodeBase64ChunkToBytes(chunkBase64) {
  const binary = atob(String(chunkBase64 || ''));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

async function parseUploadResponse(resp) {
  const text = await resp.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { text };
  }
}

async function handleUploadVideoStart(msg) {
  const { id, params } = msg;
  const {
    url,
    projectId,
    fileName,
    mimeType = 'video/mp4',
    contentLength = 0,
  } = params || {};

  if (!url || !String(url).startsWith('https://labs.google/fx/api/upload-video?action=start')) {
    sendToAgent({ id, error: 'INVALID_UPLOAD_START_URL' });
    return;
  }

  setState('running');
  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: {
        'x-upload-content-length': String(contentLength || 0),
        'x-upload-content-type': String(mimeType || 'video/mp4'),
        'x-upload-file-name': String(fileName || 'video.mp4'),
        'x-upload-project-id': String(projectId || ''),
      },
      credentials: 'include',
    });
    const data = await parseUploadResponse(resp);
    sendToAgent({ id, status: resp.status, data });
  } catch (error) {
    sendToAgent({ id, status: 500, error: error?.message || 'UPLOAD_VIDEO_START_FAILED' });
  } finally {
    setState('idle');
  }
}

async function handleUploadVideoChunk(msg) {
  const { id, params } = msg;
  const {
    url,
    projectId,
    fileName,
    sessionUrl,
    offset = 0,
    chunkBase64,
    finalize = false,
  } = params || {};

  if (!url || !String(url).startsWith('https://labs.google/fx/api/upload-video?action=upload')) {
    sendToAgent({ id, error: 'INVALID_UPLOAD_CHUNK_URL' });
    return;
  }
  if (!sessionUrl) {
    sendToAgent({ id, error: 'MISSING_UPLOAD_SESSION_URL' });
    return;
  }

  setState('running');
  try {
    const bodyBytes = decodeBase64ChunkToBytes(chunkBase64 || '');
    const resp = await fetch(url, {
      method: 'PUT',
      headers: {
        'content-type': 'application/octet-stream',
        'x-upload-command': finalize ? 'upload, finalize' : 'upload',
        'x-upload-file-name': String(fileName || 'video.mp4'),
        'x-upload-offset': String(offset || 0),
        'x-upload-project-id': String(projectId || ''),
        'x-upload-session-url': String(sessionUrl || ''),
      },
      credentials: 'include',
      body: bodyBytes,
    });
    const data = await parseUploadResponse(resp);
    sendToAgent({ id, status: resp.status, data });
  } catch (error) {
    sendToAgent({ id, status: 500, error: error?.message || 'UPLOAD_VIDEO_CHUNK_FAILED' });
  } finally {
    setState('idle');
  }
}

// ─── API Request Proxy ──────────────────────────────────────

async function handleTrpcRequest(msg) {
  const { id, params } = msg;
  const { url, method = 'POST', headers = {}, body } = params;

  if (!url || !url.startsWith('https://labs.google/')) {
    sendToAgent({ id, error: 'INVALID_TRPC_URL' });
    return;
  }

  setState('running');
  // TRPC calls don't consume captcha — don't count in metrics

  const logId = id;
  const logType = url.includes('createProject') ? 'CREATE_PROJECT' : 'TRPC';
  // TRPC calls are silent — don't show in request log

  const fetchHeaders = { 'Content-Type': 'application/json', ...headers };
  if (flowKey) {
    fetchHeaders['authorization'] = `Bearer ${flowKey}`;
  }

  try {
    const resp = await fetch(url, {
      method,
      headers: fetchHeaders,
      body: body ? JSON.stringify(body) : undefined,
      credentials: 'include',
    });
    const data = await resp.json();
    chrome.storage.local.set({ metrics });
    updateRequestLog(logId, { status: 'success' });
    sendToAgent({ id, status: resp.status, data });
  } catch (e) {
    console.error('[FlowAgent] tRPC request failed:', e);
    chrome.storage.local.set({ metrics });
    updateRequestLog(logId, { status: 'failed', error: e.message || 'TRPC_FETCH_FAILED' });
    sendToAgent({ id, error: e.message || 'TRPC_FETCH_FAILED' });
  } finally {
    setState('idle');
  }
}

async function handleApiRequest(msg) {
  const { id, params } = msg;
  const { url, method, headers, body, captchaAction } = params;
  const logContext = _normalizeLogContext(msg);

  if (!url) {
    sendToAgent({ id, error: 'MISSING_URL' });
    return;
  }

  if (!url.startsWith('https://aisandbox-pa.googleapis.com/')) {
    sendToAgent({ id, error: 'INVALID_URL' });
    return;
  }

  setState('running');
  const hasCaptcha = !!captchaAction;
  if (hasCaptcha) metrics.requestCount++;

  const logId = id;
  const logType = _classifyApiUrl(url);
  if (_VISIBLE_TYPES.has(logType)) {
    const payloadSummary = body ? JSON.stringify(body).slice(0, 200) : null;
    addRequestLog({
      id: logId,
      type: logType,
      time: new Date().toISOString(),
      status: 'processing',
      error: null,
      outputUrl: null,
      url,
      payloadSummary,
      requestId: logContext.requestId,
      sceneId: logContext.sceneId,
      projectId: logContext.projectId,
      videoId: logContext.videoId,
      requestType: logContext.requestType,
      targetAccountEmail: logContext.targetAccountEmail,
      connectionId: logContext.connectionId,
    });
  }

  try {
    // Step 1: Solve captcha if needed
    let captchaToken = null;
    if (captchaAction) {
      const captchaResult = await solveCaptcha(id, captchaAction);
      captchaToken = captchaResult?.token || null;
      if (!captchaToken) {
        // Cannot proceed without captcha — API will 403
        const err = captchaResult?.error || 'CAPTCHA_FAILED';
        console.error(`[FlowAgent] Captcha failed for ${captchaAction}: ${err}`);
        sendToAgent({ id, status: 403, error: `CAPTCHA_FAILED: ${err}`, errorCategory: 'CAPTCHA_403' });
        if (hasCaptcha) { metrics.failedCount++; metrics.lastError = 'CAPTCHA_403'; }
        chrome.storage.local.set({ metrics });
        updateRequestLog(logId, { status: 'failed', error: 'CAPTCHA_403', responseSummary: `CAPTCHA_FAILED: ${err}` });
        setState('idle');
        return;
      }
    }

    // Step 2: Inject captcha token into body
    let finalBody = body;
    if (captchaToken && finalBody) {
      finalBody = JSON.parse(JSON.stringify(finalBody)); // deep clone
      if (finalBody.clientContext?.recaptchaContext) {
        finalBody.clientContext.recaptchaContext.token = captchaToken;
      }
      if (finalBody.requests && Array.isArray(finalBody.requests)) {
        for (const req of finalBody.requests) {
          if (req.clientContext?.recaptchaContext) {
            req.clientContext.recaptchaContext.token = captchaToken;
          }
        }
      }
    }

    // Step 3: Use flowKey for auth
    if (!flowKey) {
      await captureTokenFromFlowTab();
      await waitForFlowKey(4000);
    }
    const activeFlowKey = flowKey;
    if (!activeFlowKey) {
      sendToAgent({ id, status: 503, error: 'NO_FLOW_KEY' });
      if (hasCaptcha) { metrics.failedCount++; metrics.lastError = 'NO_FLOW_KEY'; }
      chrome.storage.local.set({ metrics });
      updateRequestLog(logId, { status: 'failed', error: 'NO_FLOW_KEY' });
      setState('idle');
      return;
    }

    const fetchHeaders = { ...(headers || {}) };
    fetchHeaders['authorization'] = `Bearer ${activeFlowKey}`;

    const shouldRetryInPage = _VISIBLE_TYPES.has(logType) && ['GEN_VID', 'GEN_VID_REF', 'UPSCALE'].includes(logType);
    let response;
    let responseText = '';
    let responseData;
    let usedPageFallback = false;

    try {
      response = await fetch(url, {
        method: method || 'POST',
        headers: fetchHeaders,
        credentials: 'include',
        body: method === 'GET' ? undefined : JSON.stringify(finalBody),
      });
      responseText = await response.text();
      try {
        responseData = JSON.parse(responseText);
      } catch {
        responseData = responseText;
      }

      if (shouldRetryInPage && response.status >= 500) {
        const pageResult = await fetchInFlowPage(url, method || 'POST', fetchHeaders, finalBody);
        if (pageResult?.ok) {
          usedPageFallback = true;
          response = { status: pageResult.status, ok: pageResult.status >= 200 && pageResult.status < 300 };
          responseText = pageResult.text || '';
          try {
            responseData = JSON.parse(responseText);
          } catch {
            responseData = responseText;
          }
        }
      }
    } catch (fetchErr) {
      if (!shouldRetryInPage) throw fetchErr;
      const pageResult = await fetchInFlowPage(url, method || 'POST', fetchHeaders, finalBody);
      if (!pageResult?.ok) {
        throw new Error(pageResult?.error || fetchErr?.message || 'API_REQUEST_FAILED');
      }
      usedPageFallback = true;
      response = { status: pageResult.status, ok: pageResult.status >= 200 && pageResult.status < 300 };
      responseText = pageResult.text || '';
      try {
        responseData = JSON.parse(responseText);
      } catch {
        responseData = responseText;
      }
    }

    let errorCategory = null;
    if (response.status === 403) {
      errorCategory = _classify403(responseData);
      if (errorCategory === 'AUTH_403') {
        captureTokenFromFlowTab().catch((refreshErr) => {
          console.warn('[FlowAgent] Token refresh trigger failed after AUTH_403:', refreshErr);
        });
      }
    }

    sendToAgent({
      id,
      status: response.status,
      data: responseData,
      errorCategory,
    });

    const responseSummary = responseText ? responseText.slice(0, 300) : null;
    if (response.ok) {
      if (hasCaptcha) { metrics.successCount++; metrics.lastError = null; }
      updateRequestLog(logId, {
        status: 'success',
        httpStatus: response.status,
        responseSummary,
        transport: usedPageFallback ? 'page' : 'background',
      });
    } else {
      const errorLabel = errorCategory || `API_${response.status}`;
      if (hasCaptcha) { metrics.failedCount++; metrics.lastError = errorLabel; }
      updateRequestLog(logId, {
        status: 'failed',
        error: errorLabel,
        httpStatus: response.status,
        responseSummary,
        transport: usedPageFallback ? 'page' : 'background',
      });
    }
  } catch (e) {
    sendToAgent({
      id,
      status: 500,
      error: e.message || 'API_REQUEST_FAILED',
    });
    if (hasCaptcha) { metrics.failedCount++; metrics.lastError = e.message; }
    updateRequestLog(logId, { status: 'failed', error: e.message || 'API_REQUEST_FAILED' });
  }

  chrome.storage.local.set({ metrics });
  setState('idle');
}

function filterPageFetchHeaders(headers) {
  const allowed = new Set([
    'accept',
    'accept-language',
    'authorization',
    'content-type',
    'priority',
    'x-browser-channel',
    'x-browser-copyright',
    'x-browser-validation',
    'x-browser-year',
    'x-client-data',
  ]);
  const filtered = {};
  for (const [key, value] of Object.entries(headers || {})) {
    const lower = String(key || '').toLowerCase();
    if (allowed.has(lower)) filtered[lower] = value;
  }
  return filtered;
}

async function getOrCreateFlowTabId() {
  let tabs = await chrome.tabs.query({
    url: ['https://labs.google/fx/tools/flow*', 'https://labs.google/fx/*/tools/flow*'],
  });
  if (!tabs.length) {
    const tab = await chrome.tabs.create({ url: 'https://labs.google/fx/tools/flow', active: false });
    await sleep(5000);
    tabs = await chrome.tabs.query({
      url: ['https://labs.google/fx/tools/flow*', 'https://labs.google/fx/*/tools/flow*'],
    });
    if (!tabs.length && tab?.id) return tab.id;
  }
  return tabs[0]?.id || null;
}

async function fetchInFlowPage(url, method, headers, body, timeoutMs = 60000) {
  const tabId = await getOrCreateFlowTabId();
  if (!tabId) return { ok: false, error: 'NO_FLOW_TAB' };

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    world: 'MAIN',
    func: async (requestUrl, requestMethod, requestHeaders, requestBody, requestTimeoutMs) => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort('FETCH_TIMEOUT'), requestTimeoutMs);
      try {
        const response = await fetch(requestUrl, {
          method: requestMethod,
          headers: requestHeaders,
          credentials: 'include',
          body: requestMethod === 'GET' ? undefined : JSON.stringify(requestBody),
          signal: controller.signal,
        });
        const text = await response.text();
        return {
          ok: true,
          status: response.status,
          text,
        };
      } catch (error) {
        return {
          ok: false,
          error: error?.message || String(error),
        };
      } finally {
        clearTimeout(timer);
      }
    },
    args: [url, method, filterPageFetchHeaders(headers), body, timeoutMs],
  });

  return results?.[0]?.result || { ok: false, error: 'PAGE_FETCH_NO_RESULT' };
}

// ─── State & Popup ──────────────────────────────────────────

function setState(newState) {
  state = newState;
  const badges = { idle: '●', running: '▶', off: '○' };
  const colors = { idle: '#22c55e', running: '#f59e0b', off: '#6b7280' };
  chrome.action.setBadgeText({ text: badges[state] || '' });
  chrome.action.setBadgeBackgroundColor({ color: colors[state] || '#000' });
  broadcastStatus();
}

function broadcastStatus() {
  chrome.runtime.sendMessage({ type: 'STATUS_PUSH' }).catch(() => {});
}

chrome.runtime.onMessage.addListener((msg, _, reply) => {
  if (msg.type === 'STATUS') {
    buildSessionSnapshot(false).then((snapshot) => {
      reply({
        connected: ws?.readyState === WebSocket.OPEN,
        agentConnected: ws?.readyState === WebSocket.OPEN,
        manualDisconnect,
        metrics: {
          requestCount: metrics.requestCount,
          successCount: metrics.successCount,
          failedCount: metrics.failedCount,
          lastError: metrics.lastError,
        },
        state,
        agentConnectionId,
        ...snapshot,
      });
    }).catch((error) => {
      reply({
        connected: ws?.readyState === WebSocket.OPEN,
        agentConnected: ws?.readyState === WebSocket.OPEN,
        flowKeyPresent: !!flowKey,
        manualDisconnect,
        tokenAge: metrics.tokenCapturedAt ? Date.now() - metrics.tokenCapturedAt : null,
        metrics: {
          requestCount: metrics.requestCount,
          successCount: metrics.successCount,
          failedCount: metrics.failedCount,
          lastError: metrics.lastError,
        },
        state,
        agentConnectionId,
        extension_id: extensionId,
        account_email: accountEmail || '',
        browser_label: browserLabel,
        profile_hint: profileHint,
        error: error?.message || 'STATUS_BUILD_FAILED',
      });
    });
    return true;
  }

  if (msg.type === 'DISCONNECT') {
    manualDisconnect = true;
    if (ws) ws.close();
    reply({ ok: true });
    return true;
  }

  if (msg.type === 'RECONNECT') {
    manualDisconnect = false;
    connectToAgent();
    reply({ ok: true });
    return true;
  }

  if (msg.type === 'REQUEST_LOG') {
    reply({ log: requestLog });
    return true;
  }

  if (msg.type === 'OPEN_FLOW_TAB') {
    chrome.tabs.query({
      url: ['https://labs.google/fx/tools/flow*', 'https://labs.google/fx/*/tools/flow*'],
    }).then((tabs) => {
      if (tabs.length) {
        chrome.tabs.update(tabs[0].id, { active: true });
        reply({ ok: true, tabId: tabs[0].id });
      } else {
        chrome.tabs.create({ url: 'https://labs.google/fx/tools/flow' })
          .then((tab) => reply({ ok: true, tabId: tab.id }))
          .catch((e) => reply({ error: e.message }));
      }
    }).catch((e) => reply({ error: e.message }));
    return true;
  }

  if (msg.type === 'REFRESH_TOKEN') {
    captureTokenFromFlowTab()
      .then(() => waitForFlowKey(8000))
      .then((ok) => reply({ ok, flowKeyPresent: !!flowKey }))
      .catch((e) => reply({ error: e.message }));
    return true;
  }

  if (msg.type === 'TEST_CAPTCHA') {
    solveCaptcha(`test-${Date.now()}`, msg.pageAction || 'IMAGE_GENERATION')
      .then((r) => reply(r))
      .catch((e) => reply({ error: e.message }));
    return true;
  }

  if (msg.type === 'TRPC_MEDIA_URLS') {
    handleTrpcMediaUrls(msg.trpcUrl, msg.body);
    reply({ ok: true });
    return true;
  }

  if (msg.type === 'FLOW_AUTH_TOKEN_CAPTURED') {
    applyCapturedFlowKey(msg.token, 'page')
      .then(() => reply({ ok: true, flowKeyPresent: !!flowKey }))
      .catch((e) => reply({ error: e?.message || 'FLOW_AUTH_TOKEN_CAPTURE_FAILED' }));
    return true;
  }

  return true;
});

// ─── TRPC Media URL Extractor ──────────────────────────────

function handleTrpcMediaUrls(trpcUrl, bodyText) {
  try {
    // Extract all fresh GCS signed URLs
    const urlRegex = /https:\/\/storage\.googleapis\.com\/ai-sandbox-videofx\/(?:image|video)\/[0-9a-f-]{36}\?[^"'\s]+/g;
    const matches = bodyText.match(urlRegex) || [];
    if (!matches.length) return;

    // Deduplicate and parse
    const urlMap = {};
    for (const rawUrl of matches) {
      // Unescape JSON-escaped URLs
      const url = rawUrl.replace(/\\u0026/g, '&').replace(/\\/g, '');
      const mediaMatch = url.match(/\/(image|video)\/([0-9a-f-]{36})\?/);
      if (mediaMatch) {
        const [, mediaType, mediaId] = mediaMatch;
        // Keep last occurrence (freshest)
        urlMap[mediaId] = { mediaType, url, mediaId };
      }
    }

    const entries = Object.values(urlMap);
    if (!entries.length) return;

    console.log(`[FlowAgent] Captured ${entries.length} fresh media URLs from TRPC`);
    // URL refresh is silent — don't show in request log

    // Forward to agent for DB update
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'media_urls_refresh',
        connectionId: agentConnectionId || undefined,
        urls: entries,
      }));
    }
  } catch (e) {
    console.error('[FlowAgent] Failed to extract TRPC media URLs:', e);
  }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// ─── Human-like Telemetry ──────────────────────────────────
// Periodically send tracking events to Google's analytics endpoints
// to mimic normal browser behavior.

const _UA = navigator.userAgent;
let _telemetrySessionId = `;${Date.now()}`;

function _rand(min, max) { return Math.floor(Math.random() * (max - min + 1)) + min; }

function _buildBatchLogPayload() {
  const events = [];
  const types = ['FLOW_IMAGE_LATENCY', 'FLOW_VIDEO_LATENCY'];
  const count = _rand(1, 3);
  for (let i = 0; i < count; i++) {
    events.push({
      event: types[_rand(0, types.length - 1)],
      eventProperties: [
        { key: 'CURRENT_TIME_MS', doubleValue: Date.now() },
        { key: 'DURATION_MS', doubleValue: _rand(150, 800) },
        { key: 'USER_AGENT', stringValue: _UA },
        { key: 'IS_DESKTOP', booleanValue: true },
      ],
      eventMetadata: { sessionId: _telemetrySessionId },
      eventTime: new Date().toISOString(),
    });
  }
  return { appEvents: events };
}

function _buildFrontendEventsPayload() {
  const eventTypes = [
    'FLOW_IMAGE_LATENCY', 'FLOW_VIDEO_LATENCY', 'GRID_SCROLL_DEPTH',
    'FLOW_PROJECT_OPEN', 'FLOW_SCENE_VIEW',
  ];
  const count = _rand(1, 4);
  const events = [];
  for (let i = 0; i < count; i++) {
    const et = eventTypes[_rand(0, eventTypes.length - 1)];
    const params = {
      USER_AGENT: { '@type': 'type.googleapis.com/google.protobuf.StringValue', value: _UA },
      IS_DESKTOP: { '@type': 'type.googleapis.com/google.protobuf.StringValue', value: 'true' },
    };
    if (et.includes('LATENCY')) {
      params.CURRENT_TIME_MS = { '@type': 'type.googleapis.com/google.protobuf.StringValue', value: String(Date.now()) };
      params.DURATION_MS = { '@type': 'type.googleapis.com/google.protobuf.StringValue', value: String(_rand(100, 600)) };
    }
    if (et === 'GRID_SCROLL_DEPTH') {
      params.MEDIA_GENERATION_PAYGATE_TIER = { '@type': 'type.googleapis.com/google.protobuf.StringValue', value: 'PAYGATE_TIER_TWO' };
    }
    events.push({
      eventType: et,
      metadata: {
        sessionId: _telemetrySessionId,
        createTime: new Date().toISOString(),
        additionalParams: params,
      },
    });
  }
  return { events };
}

async function sendTelemetry() {
  if (!flowKey || state === 'off') return;

  const headers = {
    'Content-Type': 'text/plain;charset=UTF-8',
    'authorization': `Bearer ${flowKey}`,
  };

  // Telemetry is silent — don't show in request log
  try {
    if (Math.random() < 0.5) {
      await fetch(`https://aisandbox-pa.googleapis.com/v1:batchLog`, {
        method: 'POST', headers, credentials: 'include',
        body: JSON.stringify(_buildBatchLogPayload()),
      });
    } else {
      await fetch(`https://aisandbox-pa.googleapis.com/v1/flow:batchLogFrontendEvents`, {
        method: 'POST', headers, credentials: 'include',
        body: JSON.stringify(_buildFrontendEventsPayload()),
      });
    }
  } catch {}
}

// Send telemetry at random intervals (45-120s) to look organic
function scheduleTelemetry() {
  const delay = _rand(45, 120) * 1000;
  setTimeout(async () => {
    await sendTelemetry();
    scheduleTelemetry(); // reschedule with new random interval
  }, delay);
}

// Refresh session ID every ~30min like a real user
setInterval(() => { _telemetrySessionId = `;${Date.now()}`; }, _rand(25, 35) * 60 * 1000);

scheduleTelemetry();

console.log('[FlowAgent] Extension loaded');
