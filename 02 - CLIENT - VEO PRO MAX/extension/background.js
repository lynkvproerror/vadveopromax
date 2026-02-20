/**
 * VEO Pro Max Bridge — Background Service Worker
 *
 * Responsibilities:
 * 1. Intercept x-browser-* and Authorization headers from real web requests
 * 2. Maintain WebSocket connection to Python app (ws://127.0.0.1:8765)
 * 3. Relay reCAPTCHA token requests from App → content.js → App
 * 4. Auto-push captured headers when they change
 * 5. Track content.js heartbeats for health monitoring
 * 6. Relay activity simulation commands to content.js
 * 7. Lightweight header refresh without full page reload
 */

// ── State ──────────────────────────────────────────────────────────────
const WEBSOCKET_PORTS = [8765, 8766, 8767]; // Primary + fallback ports
const RECONNECT_INTERVAL = 3000; // 3 seconds

let ws = null;
let wsConnected = false;
let currentPortIndex = 0; // Which port to try next

// Per-tab state: tabId → {email, headers, accessToken, lastHeartbeat, recaptchaReady}
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

// Short token tracking: tabId → consecutive short token count
// When >= 3, auto-reload tab to re-initialize reCAPTCHA widget
const shortTokenCounts = {};
const SHORT_TOKEN_RELOAD_THRESHOLD = 3;

// Content heartbeat tracking
const HEARTBEAT_TIMEOUT = 45000;  // 45s without heartbeat = frozen tab
let _heartbeatCheckTimer = null;


// ── WebSocket Connection ───────────────────────────────────────────────

let wsReconnectDelay = RECONNECT_INTERVAL; // starts at 3s, grows with backoff

function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  const port = WEBSOCKET_PORTS[currentPortIndex];
  const url = `ws://127.0.0.1:${port}`;

  try {
    ws = new WebSocket(url);

    ws.onopen = () => {
      wsConnected = true;
      wsReconnectDelay = RECONNECT_INTERVAL; // reset backoff on success
      console.log(`[VEO Bridge] ✅ WebSocket connected to App on port ${port}`);

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
      // Rotate to next port on disconnect
      currentPortIndex = (currentPortIndex + 1) % WEBSOCKET_PORTS.length;
      const nextPort = WEBSOCKET_PORTS[currentPortIndex];
      console.debug(`[VEO Bridge] WebSocket closed (port ${port}), trying port ${nextPort} in ${wsReconnectDelay / 1000}s...`);
      setTimeout(connectWebSocket, wsReconnectDelay);
      // Exponential backoff: 3s → 6s → 12s → 24s → max 30s
      // Reset backoff when we've cycled through all ports
      if (currentPortIndex === 0) {
        wsReconnectDelay = Math.min(wsReconnectDelay * 2, 30000);
      }
    };

    ws.onerror = () => {
      // Suppress error — onclose will handle reconnect + port rotation
      console.debug(`[VEO Bridge] WebSocket connection refused on port ${port}`);
    };
  } catch (e) {
    console.debug('[VEO Bridge] WebSocket connection failed:', e.message);
    currentPortIndex = (currentPortIndex + 1) % WEBSOCKET_PORTS.length;
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
          func: async (siteKey) => {
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

            // Use async/await for proper Promise resolution by chrome.scripting
            try {
              const token = await grecaptcha.enterprise.execute(siteKey, { action: 'VIDEO_GENERATION' });
              if (token && token.length > 500) {
                return { token, tokenLength: token.length };
              }
              return { token: null, error: `Token too short (${token ? token.length : 0} chars)`, tokenLength: token ? token.length : 0 };
            } catch (err) {
              return { token: null, error: err.message, tokenLength: 0 };
            }
          },
          args: [msg.siteKey || null],
        });

        const result = results?.[0]?.result;

        // Track consecutive short tokens per tab — auto-reload after threshold
        if (result?.error?.includes('too short')) {
          shortTokenCounts[tabId] = (shortTokenCounts[tabId] || 0) + 1;
          console.warn(
            `[VEO Bridge] ⚠️ Short token #${shortTokenCounts[tabId]} for tab ${tabId} ` +
            `(${result.tokenLength || 0} chars)`
          );
          if (shortTokenCounts[tabId] >= SHORT_TOKEN_RELOAD_THRESHOLD) {
            console.warn(
              `[VEO Bridge] 🔄 Auto-reloading tab ${tabId} — ` +
              `${shortTokenCounts[tabId]} consecutive short tokens (reCAPTCHA widget broken)`
            );
            shortTokenCounts[tabId] = 0;
            try {
              await chrome.tabs.reload(tabId, { bypassCache: true });
              // Wait for page to reload and reCAPTCHA to re-initialize
              await new Promise(r => setTimeout(r, 5000));
            } catch (reloadErr) {
              console.debug(`[VEO Bridge] Tab reload failed: ${reloadErr.message}`);
            }
          }
        } else if (result?.token) {
          // Valid token — reset short token counter
          shortTokenCounts[tabId] = 0;
        }

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

    case 'refresh_headers_lightweight': {
      // Lightweight refresh — tell content.js to trigger a fetch (no page reload)
      console.log('[VEO Bridge] App requested lightweight header refresh');
      const tabId = findTabForEmail(msg.email);
      if (tabId) {
        try {
          await chrome.tabs.sendMessage(tabId, { action: 'lightweight_header_refresh' });
          wsSend({
            action: 'headers_refreshed_lightweight',
            requestId: msg.requestId || null,
            email: msg.email || null,
            success: true,
          });
        } catch (e) {
          // Content script not responding — fall back to full reload
          console.log('[VEO Bridge] Lightweight refresh failed, falling back to full reload');
          const refreshed = await reloadVeoTabs(msg.email);
          wsSend({
            action: 'headers_refreshed',
            requestId: msg.requestId || null,
            email: msg.email || null,
            tabsReloaded: refreshed,
          });
        }
      } else {
        wsSend({
          action: 'headers_refreshed_lightweight',
          requestId: msg.requestId || null,
          email: msg.email || null,
          success: false,
          error: 'No tab found',
        });
      }
      break;
    }

    case 'simulate_activity': {
      // App requests activity simulation on a specific tab
      const tabId = findTabForEmail(msg.email);
      if (tabId) {
        try {
          await chrome.tabs.sendMessage(tabId, { action: 'simulate_activity' });
          console.log(`[VEO Bridge] 🖱️ Activity simulated for ${msg.email}`);
          wsSend({
            action: 'activity_simulated',
            requestId: msg.requestId || null,
            email: msg.email,
            success: true,
          });
        } catch (e) {
          wsSend({
            action: 'activity_simulated',
            requestId: msg.requestId || null,
            email: msg.email,
            success: false,
            error: e.message,
          });
        }
      }
      break;
    }

    case 'assign_email': {
      // Server tells us which email this browser belongs to
      // (fallback when content.js email detection fails)
      const email = msg.email;
      if (!email) break;

      console.log(`[VEO Bridge] 📧 Server assigned email: ${email}`);

      // First: check if ANY tab already has this email assigned
      let existingTabId = findTabForEmail(email);
      if (existingTabId) {
        console.log(`[VEO Bridge] Email ${email} already assigned to tab ${existingTabId}`);
        wsSend({ action: 'register', email, tabId: existingTabId });
        break;
      }

      // Second: find any VEO tab (broad match including locale prefixes like /vi/)
      const veoTabs = await chrome.tabs.query({ url: '*://labs.google/*' });
      if (veoTabs.length > 0) {
        // Use first unassigned VEO tab, or first tab if all assigned
        let targetTab = veoTabs.find(t => !tabState[t.id]?.email) || veoTabs[0];
        const tabId = targetTab.id;
        if (!tabState[tabId]) {
          tabState[tabId] = { email: null, headers: {}, accessToken: null, lastHeartbeat: 0, recaptchaReady: false };
        }
        tabState[tabId].email = email;
        console.log(`[VEO Bridge] Assigned email ${email} to existing VEO tab ${tabId} (${targetTab.url})`);
        wsSend({ action: 'register', email, tabId });
      } else {
        // No VEO tab exists at all — create one, pinned and inactive
        console.log(`[VEO Bridge] No VEO tab found, creating one for ${email}...`);
        const newTab = await chrome.tabs.create({
          url: VEO_URL,
          active: false,
          pinned: true,
        });
        tabState[newTab.id] = { email, headers: {}, accessToken: null, lastHeartbeat: 0, recaptchaReady: false };
        console.log(`[VEO Bridge] Created VEO tab ${newTab.id} for ${email}`);
        wsSend({ action: 'register', email, tabId: newTab.id });
        startZombieTimer(newTab.id);  // Track zombie potential
      }
      break;
    }

    case 'check_recaptcha_ready': {
      // Layer 1: Deep readiness check — trial-execute a real token.
      // A simple `typeof execute === 'function'` check is NOT sufficient:
      // it returns true before the widget is fully initialized, causing
      // 330-char garbage tokens. Instead, we actually call execute() and
      // check that the returned token is > 500 chars.
      // The valid token is sent back for caching (not wasted).
      const tabId = findTabForEmail(msg.email);
      if (!tabId) {
        wsSend({
          action: 'recaptcha_ready',
          requestId: msg.requestId,
          ready: false,
          details: { error: `No tab found for ${msg.email}` },
        });
        return;
      }

      try {
        // Race: trial-execute vs 8s timeout (execute itself takes 3-5s)
        const scriptPromise = chrome.scripting.executeScript({
          target: { tabId },
          world: 'MAIN',
          func: async () => {
            const hasGrecaptcha = typeof grecaptcha !== 'undefined';
            const hasEnterprise = hasGrecaptcha && typeof grecaptcha.enterprise !== 'undefined';
            const hasExecute = hasEnterprise && typeof grecaptcha.enterprise.execute === 'function';
            const pageLoaded = document.readyState === 'complete';
            const hasRecaptchaScript = !!document.querySelector('script[src*="recaptcha"]');

            // Quick bail: no point trial-executing if basics fail
            if (!hasExecute || !pageLoaded) {
              return {
                ready: false,
                grecaptchaLoaded: hasGrecaptcha,
                enterpriseLoaded: hasEnterprise,
                executeAvailable: hasExecute,
                pageLoaded,
                hasRecaptchaScript,
                token: null,
                tokenLength: 0,
              };
            }

            // Extract site key (same logic as request_recaptcha)
            let siteKey = null;
            for (const s of document.querySelectorAll('script[src*="recaptcha"]')) {
              const m = s.src.match(/render=([^&]+)/);
              if (m && m[1] !== 'explicit') { siteKey = m[1]; break; }
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
              return {
                ready: false,
                grecaptchaLoaded: hasGrecaptcha,
                enterpriseLoaded: hasEnterprise,
                executeAvailable: hasExecute,
                pageLoaded,
                hasRecaptchaScript,
                token: null,
                tokenLength: 0,
                error: 'Could not extract site key',
              };
            }

            // Trial execute — the real test (async/await for proper serialization)
            try {
              const token = await grecaptcha.enterprise.execute(siteKey, { action: 'VIDEO_GENERATION' });
              return {
                ready: !!(token && token.length > 500),
                grecaptchaLoaded: true,
                enterpriseLoaded: true,
                executeAvailable: true,
                pageLoaded: true,
                hasRecaptchaScript: true,
                token: (token && token.length > 500) ? token : null,
                tokenLength: token ? token.length : 0,
              };
            } catch (err) {
              return {
                ready: false,
                grecaptchaLoaded: true,
                enterpriseLoaded: true,
                executeAvailable: true,
                pageLoaded: true,
                hasRecaptchaScript: true,
                token: null,
                tokenLength: 0,
                error: err.message,
              };
            }
          },
          args: [],
        });

        const timeoutPromise = new Promise((_, reject) =>
          setTimeout(() => reject(new Error('executeScript timeout (8s) — tab may be frozen')), 8000)
        );

        const results = await Promise.race([scriptPromise, timeoutPromise]);
        const details = results?.[0]?.result || {};
        wsSend({
          action: 'recaptcha_ready',
          requestId: msg.requestId,
          ready: details.ready || false,
          token: details.token || null,
          details,
        });
      } catch (e) {
        console.warn(`[VEO Bridge] check_recaptcha_ready failed for ${msg.email}: ${e.message}`);

        // If tab is frozen, try to wake it up by reloading
        if (e.message.includes('timeout') || e.message.includes('frozen')) {
          console.log(`[VEO Bridge] 🔄 Attempting to wake frozen tab ${tabId}...`);
          try {
            await chrome.tabs.reload(tabId, { bypassCache: false });
          } catch (reloadErr) {
            console.debug(`[VEO Bridge] Tab reload failed: ${reloadErr.message}`);
          }
        }

        wsSend({
          action: 'recaptcha_ready',
          requestId: msg.requestId,
          ready: false,
          details: { error: e.message },
        });
      }
      break;
    }

    case 'check_tab_alive': {
      // On-demand check if VEO tab is alive (not discarded/frozen)
      const tabId = findTabForEmail(msg.email);
      if (!tabId) {
        wsSend({ action: 'tab_alive', requestId: msg.requestId, alive: false, reason: 'no_tab' });
        return;
      }
      try {
        const results = await chrome.scripting.executeScript({
          target: { tabId },
          func: () => document.readyState,
        });
        wsSend({
          action: 'tab_alive',
          requestId: msg.requestId,
          alive: results?.[0]?.result === 'complete',
          tabState: results?.[0]?.result,
        });
      } catch (e) {
        wsSend({ action: 'tab_alive', requestId: msg.requestId, alive: false, reason: e.message });
      }
      break;
    }

    case 'reload_extension': {
      // Hot-reload extension from disk — reloads background.js + content.js
      // without killing Chrome. Used when extension code is updated.
      console.log('[VEO Bridge] 🔄 Reloading extension (chrome.runtime.reload)...');
      wsSend({
        action: 'extension_reloaded',
        requestId: msg.requestId || null,
        success: true,
      });
      // Small delay to ensure the WS message is sent before reload kills this context
      setTimeout(() => {
        chrome.runtime.reload();
      }, 200);
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
      tabState[tabId] = { email: null, headers: {}, accessToken: null, lastHeartbeat: 0, recaptchaReady: false };
    }
    tabState[tabId].email = msg.email;
    tabState[tabId].lastHeartbeat = Date.now();
    // Clear zombie timer if was pending
    if (tabState[tabId]._zombieTimer) {
      clearTimeout(tabState[tabId]._zombieTimer);
      delete tabState[tabId]._zombieTimer;
    }

    console.log(`[VEO Bridge] Tab ${tabId} registered: ${msg.email}`);

    // Notify app
    wsSend({
      action: 'register',
      email: msg.email,
      tabId: tabId,
    });

    sendResponse({ ok: true });
  }

  // ── Content Heartbeat ──
  if (msg.action === 'content_heartbeat' && sender.tab) {
    const tabId = sender.tab.id;
    const state = tabState[tabId];
    if (state) {
      state.lastHeartbeat = Date.now();
      // Forward heartbeat to Python app for tracking
      wsSend({
        action: 'content_heartbeat',
        email: state.email || msg.email,
        tabId,
        timestamp: msg.timestamp,
        readyState: msg.readyState,
      });
    }
    sendResponse({ ok: true });
  }

  // ── reCAPTCHA Warmth Report ──
  if (msg.action === 'recaptcha_warmth' && sender.tab) {
    const tabId = sender.tab.id;
    const state = tabState[tabId];
    if (state) {
      state.recaptchaReady = msg.ready;
      // Forward to Python app
      wsSend({
        action: 'recaptcha_warmth',
        email: state.email || msg.email,
        ready: msg.ready,
        details: msg.details,
      });
    }
    sendResponse({ ok: true });
  }

  // ── Logout Detection from content.js ──
  if (msg.action === 'tab_logout' && sender.tab) {
    const tabId = sender.tab.id;
    const state = tabState[tabId];
    const email = state?.email;

    console.warn(`[VEO Bridge] 🔴 Tab ${tabId} reported logout: ${msg.reason} (email: ${email || 'unknown'})`);

    if (email) {
      // Notify app that this account is logged out
      wsSend({
        action: 'account_logged_out',
        email: email,
        reason: msg.reason || 'unknown',
        tabId: tabId,
      });

      // Clear tab state — this tab is no longer useful
      delete tabState[tabId];
      console.log(`[VEO Bridge] Cleared state for logged-out tab ${tabId} (${email})`);
    }

    sendResponse({ ok: true });
  }

  // Forward popup requests
  if (msg.action === 'getStatus') {
    sendResponse({
      connected: wsConnected,
      tabs: Object.entries(tabState)
        .filter(([_, s]) => s.email)
        .map(([id, s]) => ({
          tabId: parseInt(id),
          email: s.email,
          headerCount: Object.keys(s.headers).length,
          lastHeartbeat: s.lastHeartbeat || 0,
          recaptchaReady: s.recaptchaReady || false,
        })),
    });
  }

  return false; // sync response
});


// ── URL-Based Logout Detection + Tab Discard Recovery ──────────────────
// Monitor VEO tabs for: logout redirects, Memory Saver discards

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  const state = tabState[tabId];
  if (!state) return;

  // ── Tab Discard Detection (Memory Saver) ──
  // Chrome can discard inactive tabs, killing content scripts.
  // Detect immediately → notify app → auto-reload.
  if (changeInfo.discarded === true && state.email) {
    console.warn(`[VEO Bridge] ⚠️ Tab ${tabId} (${state.email}) DISCARDED by Memory Saver`);
    wsSend({ action: 'tab_discarded', email: state.email, tabId });
    // Auto-reload to restore content script
    setTimeout(() => {
      chrome.tabs.reload(tabId, { bypassCache: false }).catch(() => { });
      console.log(`[VEO Bridge] 🔄 Auto-reloaded discarded tab ${tabId}`);
    }, 1000);
    return;
  }

  // ── Tab Restored from Discard — re-inject content.js ──
  if (changeInfo.discarded === false && changeInfo.status === 'complete' && state.email) {
    console.log(`[VEO Bridge] ✅ Tab ${tabId} restored from discard — re-injecting content.js`);
    chrome.scripting.executeScript({
      target: { tabId }, files: ['content.js'],
    }).catch(() => { });
    return;
  }

  // ── URL-Based Logout Detection ──
  if (!changeInfo.url) return;
  if (changeInfo.url.includes('accounts.google.com')) {
    const email = state.email;
    if (email) {
      console.warn(`[VEO Bridge] 🔴 Tab ${tabId} (${email}) navigated to Google login — LOGGED OUT`);
      wsSend({
        action: 'account_logged_out',
        email: email,
        reason: 'redirect_to_login',
        tabId: tabId,
      });
      delete tabState[tabId];
    }
  }
});


// ── Heartbeat Check — Detect Frozen Tabs ───────────────────────────────

function checkHeartbeats() {
  const now = Date.now();
  for (const [tabId, state] of Object.entries(tabState)) {
    if (!state.email || !state.lastHeartbeat) continue;

    const elapsed = now - state.lastHeartbeat;
    if (elapsed > HEARTBEAT_TIMEOUT) {
      console.warn(
        `[VEO Bridge] ⚠️ Tab ${tabId} (${state.email}) missed heartbeat ` +
        `(${Math.floor(elapsed / 1000)}s ago) — possible freeze`
      );

      // Notify Python app about the frozen tab
      wsSend({
        action: 'tab_frozen',
        email: state.email,
        tabId: parseInt(tabId),
        lastHeartbeat: state.lastHeartbeat,
        elapsedMs: elapsed,
      });

      // Try to wake it up by reloading
      chrome.tabs.reload(parseInt(tabId), { bypassCache: false }).then(() => {
        console.log(`[VEO Bridge] 🔄 Auto-reloaded frozen tab ${tabId}`);
        state.lastHeartbeat = now; // Reset to avoid immediate re-trigger
      }).catch(e => {
        console.debug(`[VEO Bridge] Tab ${tabId} reload failed: ${e.message}`);
      });
    }
  }
}

// Start heartbeat check every 20s
if (!_heartbeatCheckTimer) {
  _heartbeatCheckTimer = setInterval(checkHeartbeats, 20000);
}


// ── Zombie Tab Tracking ────────────────────────────────────────────────
// When a tab is created/tracked but gets no email within 30s, warn about it

function startZombieTimer(tabId) {
  if (!tabState[tabId]) return;
  tabState[tabId]._zombieTimer = setTimeout(() => {
    const state = tabState[tabId];
    if (state && !state.email) {
      console.warn(`[VEO Bridge] ⚠️ Zombie tab ${tabId}: no email assigned after 30s`);
      // Notify app about unresponsive tab
      wsSend({
        action: 'zombie_tab',
        tabId: tabId,
        message: 'Tab created but no email detected after 30 seconds',
      });
    }
  }, 30000); // 30 seconds
}

// Clean up on tab close + auto-reopen VEO tab
chrome.tabs.onRemoved.addListener((tabId) => {
  if (tabState[tabId]) {
    const email = tabState[tabId].email;
    const wasVeoTab = !!email; // VEO tabs have email registered
    delete tabState[tabId];
    if (email) {
      wsSend({ action: 'tab_closed', email, tabId });
    }
    // Auto-reopen VEO tab if it was closed AND no other VEO tabs exist
    if (wasVeoTab) {
      // Check if there are other VEO tabs still open
      const otherVeoTabs = Object.entries(tabState).filter(([_, s]) => s.email);
      if (otherVeoTabs.length === 0) {
        console.log(`[VEO Bridge] Last VEO tab ${tabId} closed — reopening in 2s...`);
        setTimeout(() => ensureVeoTab(), 2000);
      } else {
        console.log(`[VEO Bridge] VEO tab ${tabId} closed — ${otherVeoTabs.length} other VEO tab(s) still open`);
      }
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
// Reduced from 30s to 20s for faster keepalive.
chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: 0.33 });
// Refresh headers every 3 minutes via lightweight fetch (instead of 5 min full reload)
chrome.alarms.create(HEADER_REFRESH_ALARM, { periodInMinutes: 3 });

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === KEEPALIVE_ALARM) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      wsSend({ action: 'ping' });
    } else {
      connectWebSocket();
    }
  }

  if (alarm.name === HEADER_REFRESH_ALARM) {
    console.log('[VEO Bridge] ⏰ Periodic header refresh (lightweight)');
    // Use lightweight refresh first — content.js triggers a fetch
    // which causes onBeforeSendHeaders to fire and capture fresh headers
    lightweightRefreshAll();
  }
});

// Lightweight refresh all tabs (no page reload)
async function lightweightRefreshAll() {
  for (const [tabId, state] of Object.entries(tabState)) {
    if (!state.email) continue;
    try {
      await chrome.tabs.sendMessage(parseInt(tabId), { action: 'lightweight_header_refresh' });
      console.log(`[VEO Bridge] 🔄 Lightweight refresh for tab ${tabId} (${state.email})`);
    } catch (e) {
      // Content script not responding — try full reload as fallback
      console.debug(`[VEO Bridge] Lightweight refresh failed for tab ${tabId}, using full reload`);
      try {
        await chrome.tabs.reload(parseInt(tabId), { bypassCache: false });
      } catch (re) {
        console.debug(`[VEO Bridge] Full reload also failed for tab ${tabId}: ${re.message}`);
      }
    }
  }
}


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
    // Check if any VEO tab already exists (broad match: any locale/path)
    const existing = await chrome.tabs.query({ url: '*://labs.google/*' });
    if (existing.length > 0) {
      // Pin any unpinned VEO tabs
      for (const tab of existing) {
        if (!tab.pinned) {
          try {
            await chrome.tabs.update(tab.id, { pinned: true });
            console.log(`[VEO Bridge] 📌 Pinned existing VEO tab ${tab.id}: ${tab.url}`);
          } catch (e) {
            console.debug(`[VEO Bridge] Could not pin tab ${tab.id}: ${e.message}`);
          }
        }
      }
      console.log(`[VEO Bridge] ✅ ${existing.length} VEO tab(s) already exist — skipping creation`);
      return;
    }

    // Also check tabState — a tab might be loading and not yet queryable
    const trackedVeoTabs = Object.entries(tabState).filter(([_, s]) => s.email);
    if (trackedVeoTabs.length > 0) {
      console.log(`[VEO Bridge] ✅ ${trackedVeoTabs.length} VEO tab(s) tracked in state — skipping creation`);
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
    startZombieTimer(tab.id);  // Track zombie potential

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
  chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: 0.33 });
  connectWebSocket();
  // Inject into already-open VEO tabs, then ensure one exists
  injectExistingTabs().then(() => ensureVeoTab());
});

// ── Startup ─────────────────────────────────────────────────────────────

connectWebSocket();
// Also inject on service worker startup (not just install)
injectExistingTabs().then(() => ensureVeoTab());
console.log('[VEO Bridge] Background service worker started');