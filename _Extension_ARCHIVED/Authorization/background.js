/**
 * VEO Pro Max Bridge — Background Service Worker
 *
 * Responsibilities:
 * 1. Intercept x-browser-* and Authorization headers from real web requests
 * 2. Maintain WebSocket connection to Python app (ws://127.0.0.1:8765)
 * 3. Relay reCAPTCHA token requests from App → content.js → App
 * 4. Auto-push captured headers when they change
 */

// ── State ──────────────────────────────────────────────────────────────
const WEBSOCKET_URL = 'ws://127.0.0.1:8765';
const RECONNECT_INTERVAL = 3000; // 3 seconds

let ws = null;
let wsConnected = false;

// Per-tab state: tabId → {email, headers, accessToken}
const tabState = {};

// Headers we care about (per Protocol Analysis §1.4)
const BROWSER_HEADERS = [
  'x-browser-channel',
  'x-browser-copyright',
  'x-browser-year',
  'x-browser-validation',
  'x-client-data',
];

// Pending reCAPTCHA requests: requestId → {tabId, resolve}
const pendingRecaptcha = {};


// ── WebSocket Connection ───────────────────────────────────────────────

function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  try {
    ws = new WebSocket(WEBSOCKET_URL);

    ws.onopen = () => {
      wsConnected = true;
      console.log('[VEO Bridge] ✅ WebSocket connected to App');

      // Register all known tabs
      for (const [tabId, state] of Object.entries(tabState)) {
        if (state.email) {
          wsSend({
            action: 'register',
            email: state.email,
            tabId: parseInt(tabId),
          });
        }
      }
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleAppMessage(msg);
      } catch (e) {
        console.error('[VEO Bridge] Failed to parse message:', e);
      }
    };

    ws.onclose = () => {
      wsConnected = false;
      ws = null;
      console.log('[VEO Bridge] WebSocket closed, reconnecting in 3s...');
      setTimeout(connectWebSocket, RECONNECT_INTERVAL);
    };

    ws.onerror = (err) => {
      console.error('[VEO Bridge] WebSocket error:', err);
      // onclose will fire after onerror, triggering reconnect
    };
  } catch (e) {
    console.error('[VEO Bridge] WebSocket connection failed:', e);
    setTimeout(connectWebSocket, RECONNECT_INTERVAL);
  }
}

function wsSend(data) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(data));
    return true;
  }
  return false;
}


// ── Handle Messages from App ───────────────────────────────────────────

async function handleAppMessage(msg) {
  console.log('[VEO Bridge] App →', msg.action, msg);

  switch (msg.action) {
    case 'request_recaptcha': {
      // Find tab for this email
      const tabId = findTabForEmail(msg.email);
      if (!tabId) {
        wsSend({
          action: 'recaptcha_token',
          requestId: msg.requestId,
          token: null,
          error: `No tab found for ${msg.email}`,
        });
        return;
      }

      try {
        // Send request to content.js
        const response = await chrome.tabs.sendMessage(tabId, {
          action: 'get_recaptcha',
          siteKey: msg.siteKey || null,
        });

        wsSend({
          action: 'recaptcha_token',
          requestId: msg.requestId,
          email: msg.email,
          token: response?.token || null,
          error: response?.error || null,
        });
      } catch (e) {
        wsSend({
          action: 'recaptcha_token',
          requestId: msg.requestId,
          email: msg.email,
          token: null,
          error: e.message,
        });
      }
      break;
    }

    case 'request_headers': {
      // Return cached headers for email
      const tabId = findTabForEmail(msg.email);
      const state = tabId ? tabState[tabId] : null;

      wsSend({
        action: 'headers',
        email: msg.email,
        headers: state?.headers || {},
        accessToken: state?.accessToken || null,
      });
      break;
    }

    case 'request_access_token': {
      const tabId = findTabForEmail(msg.email);
      if (!tabId) {
        wsSend({
          action: 'access_token',
          requestId: msg.requestId,
          email: msg.email,
          token: null,
          error: `No tab found for ${msg.email}`,
        });
        return;
      }

      try {
        const response = await chrome.tabs.sendMessage(tabId, {
          action: 'get_access_token',
        });

        wsSend({
          action: 'access_token',
          requestId: msg.requestId,
          email: msg.email,
          token: response?.token || null,
          tokenEmail: response?.email || null,
        });
      } catch (e) {
        wsSend({
          action: 'access_token',
          requestId: msg.requestId,
          email: msg.email,
          token: null,
          error: e.message,
        });
      }
      break;
    }

    case 'ping':
      wsSend({ action: 'pong' });
      break;
  }
}


// ── Header Interception ────────────────────────────────────────────────

chrome.webRequest.onBeforeSendHeaders.addListener(
  (details) => {
    if (!details.requestHeaders || details.tabId < 0) return;

    const headers = {};
    let authHeader = null;

    for (const h of details.requestHeaders) {
      const name = h.name.toLowerCase();

      // Capture x-browser-* headers
      if (BROWSER_HEADERS.includes(name)) {
        headers[name] = h.value;
      }

      // Capture Authorization (contains SAPISIDHASH with access info)
      if (name === 'authorization') {
        authHeader = h.value;
      }
    }

    // Update tab state if we got useful headers
    if (Object.keys(headers).length > 0 || authHeader) {
      if (!tabState[details.tabId]) {
        tabState[details.tabId] = { email: null, headers: {}, accessToken: null };
      }

      const state = tabState[details.tabId];

      // Merge headers (don't overwrite with empty)
      Object.assign(state.headers, headers);

      if (authHeader) {
        state.accessToken = authHeader;
      }

      // Auto-push to app if connected and we have an email
      if (state.email && Object.keys(headers).length > 0) {
        wsSend({
          action: 'headers_update',
          email: state.email,
          headers: state.headers,
          accessToken: state.accessToken,
        });
      }
    }
  },
  {
    urls: ['*://*.googleapis.com/*', '*://*.aisandbox.com/*'],
  },
  ['requestHeaders']
);


// ── Tab Email Detection ────────────────────────────────────────────────

// When content.js loads on VEO page, it sends email
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'register_tab' && sender.tab) {
    const tabId = sender.tab.id;
    if (!tabState[tabId]) {
      tabState[tabId] = { email: null, headers: {}, accessToken: null };
    }
    tabState[tabId].email = msg.email;

    console.log(`[VEO Bridge] Tab ${tabId} registered: ${msg.email}`);

    // Notify app
    wsSend({
      action: 'register',
      email: msg.email,
      tabId: tabId,
    });

    sendResponse({ ok: true });
  }

  // Forward popup requests
  if (msg.action === 'getStatus') {
    sendResponse({
      connected: wsConnected,
      tabs: Object.entries(tabState)
        .filter(([_, s]) => s.email)
        .map(([id, s]) => ({ tabId: parseInt(id), email: s.email, headerCount: Object.keys(s.headers).length })),
    });
  }

  return false; // sync response
});

// Clean up on tab close
chrome.tabs.onRemoved.addListener((tabId) => {
  if (tabState[tabId]) {
    const email = tabState[tabId].email;
    delete tabState[tabId];
    if (email) {
      wsSend({ action: 'tab_closed', email, tabId });
    }
  }
});


// ── Helpers ─────────────────────────────────────────────────────────────

function findTabForEmail(email) {
  for (const [tabId, state] of Object.entries(tabState)) {
    if (state.email === email) {
      return parseInt(tabId);
    }
  }
  // Fallback: return any VEO tab
  for (const [tabId, state] of Object.entries(tabState)) {
    if (state.email) {
      return parseInt(tabId);
    }
  }
  return null;
}


// ── Startup ─────────────────────────────────────────────────────────────

connectWebSocket();
console.log('[VEO Bridge] Background service worker started');