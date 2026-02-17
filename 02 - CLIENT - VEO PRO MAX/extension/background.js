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

let wsReconnectDelay = RECONNECT_INTERVAL; // starts at 3s, grows with backoff

function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  try {
    ws = new WebSocket(WEBSOCKET_URL);

    ws.onopen = () => {
      wsConnected = true;
      wsReconnectDelay = RECONNECT_INTERVAL; // reset backoff on success
      console.log('[VEO Bridge] ✅ WebSocket connected to App');

      // Register all known tabs + immediately push cached data
      for (const [tabId, state] of Object.entries(tabState)) {
        if (state.email) {
          wsSend({
            action: 'register',
            email: state.email,
            tabId: parseInt(tabId),
          });

          // Push cached headers immediately (don't wait for next webRequest)
          if (Object.keys(state.headers).length > 0) {
            wsSend({
              action: 'headers_update',
              email: state.email,
              headers: state.headers,
              accessToken: state.accessToken,
            });
            console.log(`[VEO Bridge] 📤 Pushed cached headers for ${state.email}`);
          }

          // Extract fresh access token from page
          extractAndPushToken(parseInt(tabId), state.email);
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
      // Use debug instead of log — app not running is normal
      console.debug(`[VEO Bridge] WebSocket closed, reconnecting in ${wsReconnectDelay / 1000}s...`);
      setTimeout(connectWebSocket, wsReconnectDelay);
      // Exponential backoff: 3s → 6s → 12s → 24s → max 30s
      wsReconnectDelay = Math.min(wsReconnectDelay * 2, 30000);
    };

    ws.onerror = () => {
      // Suppress error — onclose will handle reconnect
      // Connection refused is expected when app isn't running
      console.debug('[VEO Bridge] WebSocket connection refused (app not running?)');
    };
  } catch (e) {
    console.debug('[VEO Bridge] WebSocket connection failed:', e.message);
    setTimeout(connectWebSocket, wsReconnectDelay);
    wsReconnectDelay = Math.min(wsReconnectDelay * 2, 30000);
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
        // Execute directly in page's MAIN world via chrome.scripting API
        // This bypasses CSP (no eval) and isolated world (direct grecaptcha access)
        const results = await chrome.scripting.executeScript({
          target: { tabId },
          world: 'MAIN',
          func: (siteKey) => {
            // This runs in the page's main JS context — full access to grecaptcha
            if (typeof grecaptcha === 'undefined' ||
              typeof grecaptcha.enterprise === 'undefined' ||
              typeof grecaptcha.enterprise.execute !== 'function') {
              return { token: null, error: 'reCAPTCHA Enterprise not available on page' };
            }

            // Extract site key from page if not provided
            if (!siteKey) {
              for (const s of document.querySelectorAll('script[src*="recaptcha"]')) {
                const m = s.src.match(/render=([^&]+)/);
                if (m && m[1] !== 'explicit') { siteKey = m[1]; break; }
              }
            }
            if (!siteKey && typeof ___grecaptcha_cfg !== 'undefined' && ___grecaptcha_cfg.clients) {
              for (const id in ___grecaptcha_cfg.clients) {
                const client = ___grecaptcha_cfg.clients[id];
                for (const key in client) {
                  const obj = client[key];
                  if (obj && typeof obj === 'object') {
                    for (const k2 in obj) {
                      const v = obj[k2];
                      if (v && typeof v === 'object' && v.sitekey) { siteKey = v.sitekey; break; }
                    }
                  }
                  if (siteKey) break;
                }
                if (siteKey) break;
              }
            }

            if (!siteKey) {
              return { token: null, error: 'Could not extract reCAPTCHA site key' };
            }

            // Return a promise — chrome.scripting handles async results
            return grecaptcha.enterprise.execute(siteKey, { action: 'VIDEO_GENERATION' })
              .then(token => {
                if (token && token.length > 500) {
                  return { token };
                }
                return { token: null, error: `Token too short (${token ? token.length : 0} chars)` };
              })
              .catch(err => ({ token: null, error: err.message }));
          },
          args: [msg.siteKey || null],
        });

        const result = results?.[0]?.result;
        wsSend({
          action: 'recaptcha_token',
          requestId: msg.requestId,
          email: msg.email,
          token: result?.token || null,
          error: result?.error || null,
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

    case 'refresh_headers': {
      // App requests fresh headers → reload VEO tabs to trigger API requests
      console.log('[VEO Bridge] App requested header refresh');
      const refreshed = await reloadVeoTabs(msg.email);
      wsSend({
        action: 'headers_refreshed',
        requestId: msg.requestId || null,
        email: msg.email || null,
        tabsReloaded: refreshed,
      });
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
    if (!tabState[details.tabId]) return; // Only capture from registered VEO tabs

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

    // Nothing useful captured
    if (Object.keys(headers).length === 0 && !authHeader) return;

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
  },
  {
    urls: [
      '*://*.googleapis.com/*',   // Google APIs
      '*://*.aisandbox.com/*',    // AI Sandbox
      '*://labs.google/*',         // VEO website
    ],
  },
  ['requestHeaders', 'extraHeaders']
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

// Clean up on tab close + auto-reopen VEO tab
chrome.tabs.onRemoved.addListener((tabId) => {
  if (tabState[tabId]) {
    const email = tabState[tabId].email;
    const wasVeoTab = !!email; // VEO tabs have email registered
    delete tabState[tabId];
    if (email) {
      wsSend({ action: 'tab_closed', email, tabId });
    }
    // Auto-reopen VEO tab if it was closed
    if (wasVeoTab) {
      console.log(`[VEO Bridge] VEO tab ${tabId} closed — reopening in 2s...`);
      setTimeout(() => ensureVeoTab(), 2000);
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


// ── Extract and Push Token Helper ──────────────────────────────────────

async function extractAndPushToken(tabId, email) {
  try {
    const response = await chrome.tabs.sendMessage(tabId, {
      action: 'get_access_token',
    });
    if (response?.token) {
      wsSend({
        action: 'access_token',
        requestId: null,  // unsolicited push (not a response to a request)
        email: email,
        token: response.token,
        tokenEmail: response.email || null,
      });
      console.log(`[VEO Bridge] 🔑 Pushed access token for ${email}`);
    }
  } catch (e) {
    console.debug(`[VEO Bridge] Token extract failed for tab ${tabId}: ${e.message}`);
  }
}


// ── Keepalive & Periodic Refresh ───────────────────────────────────────

const KEEPALIVE_ALARM = 'ws-keepalive';
const HEADER_REFRESH_ALARM = 'header-refresh';

// Chrome suspends service workers after ~30s of inactivity.
chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: 0.5 });
// Refresh headers every 5 minutes by reloading VEO tabs
chrome.alarms.create(HEADER_REFRESH_ALARM, { periodInMinutes: 5 });

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === KEEPALIVE_ALARM) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      wsSend({ action: 'ping' });
    } else {
      connectWebSocket();
    }
  }

  if (alarm.name === HEADER_REFRESH_ALARM) {
    console.log('[VEO Bridge] ⏰ Periodic header refresh');
    reloadVeoTabs();
  }
});


// ── Reload VEO Tabs (shared by periodic + on-demand) ──────────────────

async function reloadVeoTabs(email = null) {
  try {
    const tabs = await chrome.tabs.query({ url: '*://labs.google/*' });
    let reloaded = 0;

    for (const tab of tabs) {
      // If email specified, only reload tabs matching that email
      if (email) {
        const state = tabState[tab.id];
        if (state && state.email !== email) continue;
      }

      try {
        await chrome.tabs.reload(tab.id, { bypassCache: false });
        reloaded++;
        console.log(`[VEO Bridge] 🔄 Reloaded tab ${tab.id} for header refresh`);
      } catch (e) {
        console.debug(`[VEO Bridge] Could not reload tab ${tab.id}: ${e.message}`);
      }
    }

    console.log(`[VEO Bridge] Reloaded ${reloaded}/${tabs.length} VEO tab(s)`);
    return reloaded;
  } catch (e) {
    console.error('[VEO Bridge] Failed to reload VEO tabs:', e);
    return 0;
  }
}


// ── Auto-detect existing VEO tabs ──────────────────────────────────────

async function injectExistingTabs() {
  try {
    const tabs = await chrome.tabs.query({ url: '*://labs.google/*' });
    console.log(`[VEO Bridge] Found ${tabs.length} existing VEO tab(s)`);

    for (const tab of tabs) {
      try {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ['content.js'],
        });
        console.log(`[VEO Bridge] Injected content.js into tab ${tab.id}: ${tab.url}`);

        // Pin VEO tabs that aren't already pinned
        if (!tab.pinned) {
          chrome.tabs.update(tab.id, { pinned: true });
          console.log(`[VEO Bridge] 📌 Pinned VEO tab ${tab.id}`);
        }

        // Reload tab to trigger fresh API requests → headers get captured
        setTimeout(() => {
          chrome.tabs.reload(tab.id, { bypassCache: false });
          console.log(`[VEO Bridge] Reloaded tab ${tab.id} for header capture`);
        }, 1000); // Wait 1s for content.js to register email first

      } catch (e) {
        // Tab may not be accessible (e.g. chrome:// pages, about:blank)
        console.debug(`[VEO Bridge] Could not inject into tab ${tab.id}: ${e.message}`);
      }
    }
  } catch (e) {
    console.error('[VEO Bridge] Failed to query tabs:', e);
  }
}


// ── Ensure VEO Tab (auto-open + pin) ───────────────────────────────────

const VEO_URL = 'https://labs.google/fx/tools/flow';
let _ensureVeoTabRunning = false; // debounce guard

async function ensureVeoTab() {
  if (_ensureVeoTabRunning) return;
  _ensureVeoTabRunning = true;

  try {
    // Check if any VEO tab already exists
    const existing = await chrome.tabs.query({ url: '*://labs.google/*' });
    if (existing.length > 0) {
      // Pin any unpinned VEO tabs
      for (const tab of existing) {
        if (!tab.pinned) {
          chrome.tabs.update(tab.id, { pinned: true });
          console.log(`[VEO Bridge] 📌 Pinned existing VEO tab ${tab.id}`);
        }
      }
      return;
    }

    // No VEO tab found — create one, pinned and inactive (background)
    console.log('[VEO Bridge] 🆕 No VEO tab found, opening one...');
    const tab = await chrome.tabs.create({
      url: VEO_URL,
      active: false, // don't steal focus from current tab
      pinned: true,
    });
    console.log(`[VEO Bridge] 📌 Created pinned VEO tab ${tab.id}`);

    // Inject content.js after page loads
    setTimeout(async () => {
      try {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ['content.js'],
        });
      } catch (e) {
        console.debug(`[VEO Bridge] Content inject after create: ${e.message}`);
      }
    }, 5000); // Wait for page to finish loading

  } catch (e) {
    console.error('[VEO Bridge] ensureVeoTab failed:', e);
  } finally {
    _ensureVeoTabRunning = false;
  }
}


// ── Lifecycle ───────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  console.log('[VEO Bridge] Extension installed/updated');
  chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: 0.5 });
  connectWebSocket();
  // Inject into already-open VEO tabs, then ensure one exists
  injectExistingTabs().then(() => ensureVeoTab());
});

// ── Startup ─────────────────────────────────────────────────────────────

connectWebSocket();
// Also inject on service worker startup (not just install)
injectExistingTabs().then(() => ensureVeoTab());
console.log('[VEO Bridge] Background service worker started');