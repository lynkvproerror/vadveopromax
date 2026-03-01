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
const EXT_VERSION = chrome.runtime.getManifest().version; // e.g. '2.1'
const WEBSOCKET_PORTS = [8765, 8766, 8767]; // Primary + fallback ports
const RECONNECT_INTERVAL = 3000; // 3 seconds
const MAX_TABS = 3; // Maximum number of browser tabs allowed (Gmail, YouTube, VEO Flow)

let ws = null;
let wsConnected = false;
let currentPortIndex = 0; // Which port to try next

// Per-tab state: tabId → {email, headers, accessToken, lastHeartbeat, recaptchaReady}
const tabState = {};

// Global x-browser-validation captured from ANY request (including Chrome internal)
// This header is only present on cross-origin requests to googleapis.com
let globalBrowserValidation = null;

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

// ★ Debounce timers for headers_update (email → timerId)
// Collapses 6+ duplicate sends from a single page reload into 1
const _headersDebounceTimers = {};
const HEADERS_DEBOUNCE_MS = 2000;  // 2s window

// Content heartbeat tracking
const HEARTBEAT_TIMEOUT = 45000;  // 45s without heartbeat = frozen tab
const FROZEN_RELOAD_MAX = 3;      // Max reloads per window before declaring tab dead
const FROZEN_RELOAD_WINDOW = 300000; // 5 min window for reload cap
let _heartbeatCheckTimer = null;

// ★ Global tab reload cooldown: prevents cascading reloads during startup.
// Multiple systems (recaptcha check, heartbeat, header refresh) can all try
// to reload the same tab. Without cooldown, the VEO page (13s+ load time)
// never finishes loading → grecaptcha never initializes → 330-char tokens.
const RELOAD_COOLDOWN_MS = 20000; // 20s between reloads per tab
const tabLastReloadTime = {};     // tabId → Date.now() of last reload

/**
 * Reload a tab with global cooldown protection.
 * Returns true if reload was executed, false if skipped (cooldown active).
 */
async function safeTabReload(tabId, reason, bypassCache = false) {
  const now = Date.now();
  const lastReload = tabLastReloadTime[tabId] || 0;
  const elapsed = now - lastReload;

  if (elapsed < RELOAD_COOLDOWN_MS) {
    console.debug(
      `[VEO Bridge] ⏳ Skipping reload for tab ${tabId} — ` +
      `cooldown active (${Math.ceil((RELOAD_COOLDOWN_MS - elapsed) / 1000)}s remaining, reason: ${reason})`
    );
    return false;
  }

  try {
    await chrome.tabs.reload(tabId, { bypassCache });
    tabLastReloadTime[tabId] = now;
    console.log(`[VEO Bridge] 🔄 Reloaded tab ${tabId} (reason: ${reason})`);
    return true;
  } catch (e) {
    console.debug(`[VEO Bridge] Tab ${tabId} reload failed: ${e.message}`);
    return false;
  }
}


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
            version: EXT_VERSION,
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
        handleAppMessage(msg).catch(e => {
          console.error('[VEO Bridge] Async handler error:', e.message || e);
        });
      } catch (e) {
        console.error('[VEO Bridge] Failed to parse message:', e);
      }
    };

    ws.onclose = (event) => {
      wsConnected = false;
      ws = null;
      // Only rotate port on clean close (server intentionally closed).
      // Idle/network disconnects stay on same port — Python WS server
      // only listens on port 8765, rotating to 8766/8767 causes error flood.
      if (event.wasClean) {
        currentPortIndex = (currentPortIndex + 1) % WEBSOCKET_PORTS.length;
      }
      const nextPort = WEBSOCKET_PORTS[currentPortIndex];
      console.debug(`[VEO Bridge] WebSocket closed (port ${port}, clean=${event.wasClean}), trying port ${nextPort} in ${wsReconnectDelay / 1000}s...`);
      setTimeout(connectWebSocket, wsReconnectDelay);
      // Exponential backoff: 3s → 6s → 12s → 24s → max 30s
      // Only increase backoff after cycling all ports on clean close
      if (event.wasClean && currentPortIndex === 0) {
        wsReconnectDelay = Math.min(wsReconnectDelay * 2, 30000);
      } else if (!event.wasClean) {
        // Idle disconnect: use moderate backoff (3s → 6s → max 10s)
        wsReconnectDelay = Math.min(wsReconnectDelay * 1.5, 10000);
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
              if (token && token.length >= 1000) {
                return { token, tokenLength: token.length };
              }
              return { token: null, error: `Token too short (${token ? token.length : 0} chars, need ≥1000)`, tokenLength: token ? token.length : 0 };
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
            const reloaded = await safeTabReload(tabId, 'short-token-threshold', true);
            if (reloaded) {
              // Wait for page to reload and reCAPTCHA to re-initialize
              await new Promise(r => setTimeout(r, 5000));
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

    case 'reload_extension': {
      // Bridge detected version mismatch → self-reload to pick up new code
      const reason = msg.reason || 'version mismatch';
      const targetVer = msg.target_version || 'unknown';
      console.warn(
        `[VEO Bridge] 🔄 Reload requested: ${reason} → target v${targetVer} (current v${EXT_VERSION})`
      );
      // Small delay to let the log message be sent
      setTimeout(() => {
        chrome.runtime.reload();
      }, 1000);
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
        wsSend({ action: 'register', email, tabId: existingTabId, version: EXT_VERSION });
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
        wsSend({ action: 'register', email, tabId, version: EXT_VERSION });
      } else {
        // No VEO tab exists — check tab limit before creating
        const allTabs = await chrome.tabs.query({ currentWindow: true });
        if (allTabs.length >= MAX_TABS) {
          console.warn(`[VEO Bridge] ⚠️ Tab limit reached (${allTabs.length}/${MAX_TABS}) — NOT creating tab for ${email}`);
          wsSend({
            action: 'register',
            email,
            tabId: null,
            version: EXT_VERSION,
            error: `Tab limit reached (${MAX_TABS})`,
          });
        } else {
          console.log(`[VEO Bridge] Creating VEO tab for ${email} (${allTabs.length}/${MAX_TABS} tabs)...`);
          const newTab = await chrome.tabs.create({
            url: VEO_URL,
            active: false,
            pinned: true,
          });
          tabState[newTab.id] = { email, headers: {}, accessToken: null, lastHeartbeat: 0, recaptchaReady: false };
          console.log(`[VEO Bridge] Created VEO tab ${newTab.id} for ${email}`);
          wsSend({ action: 'register', email, tabId: newTab.id, version: EXT_VERSION });
          try { chrome.tabs.update(newTab.id, { autoDiscardable: false }); } catch (_) { }
          startZombieTimer(newTab.id);
        }
      }
      break;
    }

    case 'reload_extension': {
      // Reload extension via chrome.runtime.reload()
      // Called from Python extension_bridge when extension code is updated.
      console.log('[VEO Bridge] 🔄 Reloading extension...');
      wsSend({
        action: 'extension_reloading',
        requestId: msg.requestId || '',
      });
      // Brief delay to let the response send before reload
      setTimeout(() => {
        chrome.runtime.reload();
      }, 500);
      break;
    }

    case 'check_recaptcha_ready': {
      // Layer 1: Deep readiness check — trial-execute a real token.
      // A simple `typeof execute === 'function'` check is NOT sufficient:
      // it returns true before the widget is fully initialized, causing
      // 330-538 char garbage tokens. Instead, we actually call execute() and
      // check that the returned token is ≥ 1500 chars (HAR: valid = 1742-2169).
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

            // Only bail if grecaptcha.enterprise.execute doesn't exist yet.
            // Don't require document.readyState === 'complete' — reCAPTCHA
            // can be functional before the full page load finishes (the VEO
            // page takes 13+ seconds to reach 'complete' after reload).
            if (!hasExecute) {
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
            // NOTE: Use VIDEO_GENERATION as the trial action (most common endpoint).
            // The actual submit_prompt handler always generates its own fresh token
            // with the correct action (IMAGE_GENERATION for T2I/UPSCALE_IMAGE,
            // VIDEO_GENERATION for video endpoints). The trial token here is only
            // used to verify widget health — but since it may be cached by the pool,
            // we tag it with trialAction so Python can avoid action mismatches.
            const trialAction = 'VIDEO_GENERATION';
            try {
              const token = await grecaptcha.enterprise.execute(siteKey, { action: trialAction });
              return {
                ready: !!(token && token.length >= 1500),
                grecaptchaLoaded: true,
                enterpriseLoaded: true,
                executeAvailable: true,
                pageLoaded: true,
                hasRecaptchaScript: true,
                token: (token && token.length >= 1500) ? token : null,
                tokenLength: token ? token.length : 0,
                trialAction,  // tag so pool knows what action this token was generated for
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

        // VEO page takes 13+ seconds to fully load after reload.
        // Use 20s timeout to avoid premature "frozen" detection during startup.
        const timeoutPromise = new Promise((_, reject) =>
          setTimeout(() => reject(new Error('executeScript timeout (20s) — tab may be frozen')), 20000)
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

        // If tab is frozen, try to wake it up (with cooldown protection)
        if (e.message.includes('timeout') || e.message.includes('frozen')) {
          await safeTabReload(tabId, 'recaptcha-check-timeout');
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

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // submit_prompt — FULL API SUBMISSION FROM PAGE CONTEXT
    //
    // Flow: reCAPTCHA token → build body → fetch() from page → return result
    // Token is used IMMEDIATELY (<100ms), headers auto-added by browser.
    // This eliminates token expiry issues and header mismatches.
    //
    // Uses chrome.scripting.executeScript (world: MAIN) which bypasses CSP.
    // Content.js <script> injection is blocked by labs.google CSP.
    //
    // MV3 keepalive: chrome.runtime.getPlatformInfo() every 25s resets
    // Chrome's 30s service worker inactivity timer, preventing termination
    // during long reCAPTCHA + fetch operations.
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    case 'submit_prompt': {
      const tabId = findTabForEmail(msg.email);
      if (!tabId) {
        wsSend({
          action: 'submit_prompt_result',
          requestId: msg.requestId,
          success: false,
          error: `No tab found for ${msg.email}`,
        });
        return;
      }

      // ── MV3 Keepalive ──────────────────────────────────────────────────
      // Call extension API every 25s to reset Chrome's 30s inactivity timer.
      // This prevents service worker termination during long operations
      // (reCAPTCHA ≤10s + fetch ≤20s = up to 30s total).
      const keepaliveTimer = setInterval(() => {
        chrome.runtime.getPlatformInfo(() => { });
      }, 25000);

      try {
        // Endpoint URLs mapped by type
        const ENDPOINTS = {
          T2V: 'https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoText',
          I2V_SINGLE: 'https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoStartImage',
          I2V_DUAL: 'https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoStartAndEndImage',
          R2V: 'https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoReferenceImages',
          // T2I: dynamic — requires projects/{projectId}/ prefix (see below)
          STATUS: 'https://aisandbox-pa.googleapis.com/v1/video:batchCheckAsyncVideoGenerationStatus',
          UPSCALE_VIDEO: 'https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoUpsampleVideo',
          UPLOAD: 'https://aisandbox-pa.googleapis.com/v1:uploadUserImage',
          UPSCALE_IMAGE: 'https://aisandbox-pa.googleapis.com/v1/flow/upsampleImage',
        };

        // T2I/I2I: URL requires projects/{projectId}/ prefix per HAR
        let endpointUrl;
        if (msg.endpoint === 'T2I') {
          const projectId = msg.payload?.body?.clientContext?.projectId || '';
          if (!projectId) {
            wsSend({
              action: 'submit_prompt_result',
              requestId: msg.requestId,
              success: false,
              error: 'T2I requires projectId in clientContext',
            });
            return;
          }
          endpointUrl = `https://aisandbox-pa.googleapis.com/v1/projects/${projectId}/flowMedia:batchGenerateImages`;
        } else {
          endpointUrl = ENDPOINTS[msg.endpoint] || msg.endpointUrl;
        }

        if (!endpointUrl) {
          wsSend({
            action: 'submit_prompt_result',
            requestId: msg.requestId,
            success: false,
            error: `Unknown endpoint: ${msg.endpoint}`,
          });
          return;
        }

        console.log(
          `[VEO Bridge] 🚀 submit_prompt for ${msg.email} → ${msg.endpoint} ` +
          `(tab ${tabId}) [executeScript + keepalive]`
        );

        // Race: script execution vs 30s timeout (reCAPTCHA takes 3-5s + fetch 2-10s)
        const scriptPromise = chrome.scripting.executeScript({
          target: { tabId },
          world: 'MAIN',
          func: async (endpointUrl, payload, needsRecaptcha, cachedAccessToken, endpointKey) => {
            // ── Step 1: Extract reCAPTCHA site key ────────────────────────
            let siteKey = null;
            if (needsRecaptcha) {
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
                return { success: false, error: 'Could not extract reCAPTCHA site key' };
              }
            }

            // ── Step 2: Generate reCAPTCHA token (with 10s timeout) ───────
            let recaptchaToken = null;
            if (needsRecaptcha) {
              try {
                // HAR verified: T2I/UPSCALE_IMAGE use IMAGE_GENERATION, video endpoints use VIDEO_GENERATION
                // UPSCALE_IMAGE is an image-domain operation (upsampleImage API), same reCAPTCHA action as T2I
                const imageEndpoints = ['T2I', 'UPSCALE_IMAGE'];
                const rcAction = imageEndpoints.includes(endpointKey) ? 'IMAGE_GENERATION' : 'VIDEO_GENERATION';
                const rcPromise = grecaptcha.enterprise.execute(siteKey, { action: rcAction });
                const rcTimeout = new Promise((_, reject) =>
                  setTimeout(() => reject(new Error('reCAPTCHA execute timeout (10s)')), 10000)
                );
                recaptchaToken = await Promise.race([rcPromise, rcTimeout]);
                // HAR verified: valid tokens are 1742-2169 chars
                // A 538-char token passed old threshold (500) but was rejected by Google
                if (!recaptchaToken || recaptchaToken.length < 1000) {
                  return {
                    success: false,
                    error: `reCAPTCHA token too short (${recaptchaToken ? recaptchaToken.length : 0} chars, need ≥1000)`,
                    tokenLength: recaptchaToken ? recaptchaToken.length : 0,
                  };
                }
              } catch (err) {
                return { success: false, error: `reCAPTCHA execute failed: ${err.message}` };
              }
            }

            // ── Step 3: Build request body ────────────────────────────────
            const body = payload.body || {};
            if (needsRecaptcha && recaptchaToken) {
              const rcCtx = {
                token: recaptchaToken,
                applicationType: 'RECAPTCHA_APPLICATION_TYPE_WEB',
              };
              // Top-level clientContext
              if (!body.clientContext) body.clientContext = {};
              body.clientContext.recaptchaContext = rcCtx;
              // Per-request clientContext (HAR: T2I/I2I requires nested reCAPTCHA)
              if (Array.isArray(body.requests)) {
                for (const req of body.requests) {
                  if (req.clientContext) {
                    req.clientContext.recaptchaContext = rcCtx;
                  }
                }
              }
            }

            // ── Step 4: Get access token ──────────────────────────────────
            // Priority: 1) fresh Bearer token from webRequest headers
            //           2) fallback to __NEXT_DATA__ (may be stale after ~1h)
            // IMPORTANT: Only use Bearer tokens. SAPISIDHASH is Google internal
            // auth and causes 403 on VEO API (HAR-verified 27/02/2026).
            let authHeaderValue = (cachedAccessToken && cachedAccessToken.startsWith('Bearer ')) ? cachedAccessToken : null;
            if (!authHeaderValue) {
              const nextDataEl = document.getElementById('__NEXT_DATA__');
              if (nextDataEl) {
                try {
                  const data = JSON.parse(nextDataEl.textContent);
                  const props = data?.props?.pageProps || {};
                  const session = props.session || {};
                  let token = session.access_token || session.accessToken;
                  if (!token) {
                    const user = props.user || {};
                    token = user.accessToken;
                  }
                  if (token) {
                    authHeaderValue = `Bearer ${token}`;
                  }
                } catch (e) { /* ignore parse errors */ }
              }
            }

            // ── Step 5: Send API request (with 20s AbortController) ──────
            const headers = { 'Content-Type': 'text/plain;charset=UTF-8' };
            if (authHeaderValue) {
              headers['Authorization'] = authHeaderValue;
            }

            const controller = new AbortController();
            // T2I is synchronous — server generates images before responding (~37s per HAR)
            // Video endpoints are async — return operation name immediately
            const fetchTimeout = (endpointKey === 'T2I' || endpointKey === 'I2I') ? 90000 : 20000;
            const fetchTimer = setTimeout(() => controller.abort(), fetchTimeout);
            try {
              // Diagnostic: log what we're about to send
              const bodyStr = JSON.stringify(body);
              console.log(
                `[VEO Bridge] 📡 T2I fetch: url=${endpointUrl.substring(0, 120)}`,
                `\n  auth=${authHeaderValue ? authHeaderValue.substring(0, 30) + '...' : 'NONE'}`,
                `\n  bodySize=${bodyStr.length} bodyKeys=${Object.keys(body).join(',')}`,
                `\n  hasRecaptcha=${!!body.clientContext?.recaptchaContext}`,
                `\n  reqCount=${body.requests?.length || 0}`,
              );
              const resp = await fetch(endpointUrl, {
                method: 'POST',
                headers,
                credentials: 'include',
                body: bodyStr,
                signal: controller.signal,
              });
              clearTimeout(fetchTimer);

              const responseText = await resp.text();
              let responseData = null;
              try {
                responseData = JSON.parse(responseText);
              } catch (e) {
                responseData = { raw: responseText.substring(0, 1000) };
              }

              return {
                success: resp.ok,
                status: resp.status,
                statusText: resp.statusText,
                data: responseData,
                error: resp.ok ? undefined : (
                  // Extract error details from API response body for non-OK responses
                  (responseData?.error?.message) ||
                  (responseData?.error?.status) ||
                  (typeof responseData?.error === 'string' ? responseData.error : '') ||
                  (responseData?.raw ? responseData.raw.substring(0, 200) : '') ||
                  resp.statusText || `HTTP ${resp.status}`
                ),
                tokenLength: recaptchaToken ? recaptchaToken.length : 0,
              };
            } catch (fetchErr) {
              clearTimeout(fetchTimer);
              const errMsg = fetchErr.name === 'AbortError'
                ? `fetch timeout (${fetchTimeout / 1000}s) — API did not respond`
                : `fetch failed: ${fetchErr.message}`;
              return {
                success: false,
                error: errMsg,
                tokenLength: recaptchaToken ? recaptchaToken.length : 0,
              };
            }
          },
          args: [
            endpointUrl,
            msg.payload || {},
            msg.needsRecaptcha !== false, // default: true
            tabState[tabId]?.accessToken || null, // fresh token from webRequest headers
            msg.endpoint || '', // endpoint key for reCAPTCHA action selection
          ],
        });

        // T2I/I2I: synchronous response (up to ~90s), video: async (quick)
        const scriptTimeout = (msg.endpoint === 'T2I' || msg.endpoint === 'I2I') ? 120000 : 30000;
        const timeoutPromise = new Promise((_, reject) =>
          setTimeout(() => reject(new Error(`submit_prompt timeout (${scriptTimeout / 1000}s)`)), scriptTimeout)
        );

        const results = await Promise.race([scriptPromise, timeoutPromise]);
        const result = results?.[0]?.result || {};

        console.log(
          `[VEO Bridge] ${result.success ? '✅' : '❌'} submit_prompt result: ` +
          `status=${result.status || 'N/A'} token=${result.tokenLength || 0}chars` +
          (result.error ? ` error=${result.error}` : '') +
          (result.data?.error ? ` apiError=${JSON.stringify(result.data.error).substring(0, 200)}` : '')
        );

        // Trim large response data to prevent WebSocket overflow.
        // UPSCALE_VIDEO responses can be ~1MB+ (include video frame data).
        // Python only needs operation name/sceneId, not the video binary.
        let trimmedResult = { ...result };
        if (result.data) {
          const dataStr = JSON.stringify(result.data);
          if (dataStr.length > 50000) { // >50KB = likely contains video data
            console.log(
              `[VEO Bridge] ✂️ Trimming large response: ${(dataStr.length / 1024).toFixed(0)}KB → keeping metadata only`
            );
            // Deep-strip large binary fields while preserving structure.
            // API response: {operations: [{operation: {name: "..."}, sceneId: "...", response: {videos: [{encodedVideo: "HUGE"}]}}]}
            // Python needs: operations[].operation.name, operations[].sceneId
            const strip = (obj) => {
              if (!obj || typeof obj !== 'object') return obj;
              if (Array.isArray(obj)) return obj.map(strip);
              const out = {};
              for (const [k, v] of Object.entries(obj)) {
                // Skip known huge fields
                if (k === 'encodedVideo' || k === 'encodedImage') continue;
                // Recursively strip nested objects, but skip huge string values
                if (typeof v === 'string' && v.length > 10000) {
                  out[k] = `[trimmed ${v.length} chars]`;
                } else if (typeof v === 'object') {
                  out[k] = strip(v);
                } else {
                  out[k] = v;
                }
              }
              return out;
            };
            trimmedResult.data = strip(result.data);
            trimmedResult._trimmed = true;
          }
        }

        wsSend({
          action: 'submit_prompt_result',
          requestId: msg.requestId,
          ...trimmedResult,
        });
      } catch (e) {
        console.error(`[VEO Bridge] ❌ submit_prompt failed for ${msg.email}: ${e.message}`);
        wsSend({
          action: 'submit_prompt_result',
          requestId: msg.requestId,
          success: false,
          error: e.message,
        });
      } finally {
        clearInterval(keepaliveTimer);
      }
      break;
    }

    case 'navigate_tab': {
      // Navigate VEO tab to a specific URL (e.g. project page)
      // Uses chrome.tabs.update — cleaner than window.location.href
      const tabId = findTabForEmail(msg.email);
      if (!tabId) {
        wsSend({
          action: 'navigate_tab_result',
          requestId: msg.requestId,
          success: false,
          error: `No tab found for ${msg.email}`,
        });
        return;
      }

      const targetUrl = msg.url;
      if (!targetUrl) {
        wsSend({
          action: 'navigate_tab_result',
          requestId: msg.requestId,
          success: false,
          error: 'No URL specified',
        });
        return;
      }

      try {
        const startTime = Date.now();
        console.log(`[VEO Bridge] 📍 Navigating tab ${tabId} to: ${targetUrl}`);

        // Navigate using chrome.tabs.update
        await chrome.tabs.update(tabId, { url: targetUrl });

        // Wait 1.5s for tab to actually START loading
        // (tab.status can briefly remain 'complete' before navigation kicks in)
        await new Promise(r => setTimeout(r, 1500));

        // Poll for page to finish loading (every 500ms, max 25s)
        const maxWait = 25000;
        let loadComplete = false;
        while (Date.now() - startTime < maxWait + 1500) {
          try {
            const tab = await chrome.tabs.get(tabId);
            if (tab.status === 'complete') {
              loadComplete = true;
              break;
            }
          } catch (e) {
            // Tab might be mid-navigation — continue polling
          }
          await new Promise(r => setTimeout(r, 500));
        }

        const loadTime = ((Date.now() - startTime) / 1000).toFixed(1);

        if (loadComplete) {
          console.log(`[VEO Bridge] ✅ Navigation complete in ${loadTime}s: ${targetUrl}`);
        } else {
          console.warn(`[VEO Bridge] ⚠️ Navigation timeout (${loadTime}s): ${targetUrl}`);
        }

        wsSend({
          action: 'navigate_tab_result',
          requestId: msg.requestId,
          success: loadComplete,
          loadTime: parseFloat(loadTime),
          url: targetUrl,
          timedOut: !loadComplete,
        });
      } catch (e) {
        console.error(`[VEO Bridge] ❌ Navigation failed: ${e.message}`);
        wsSend({
          action: 'navigate_tab_result',
          requestId: msg.requestId,
          success: false,
          error: e.message,
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

    case 'probe_browser_headers': {
      // Trigger a cross-origin fetch from the VEO page to googleapis.com
      // This causes Chrome to add x-browser-validation header,
      // which is captured by the webRequest listener above.
      const tabId = findTabForEmail(msg.email);
      if (!tabId) {
        wsSend({
          action: 'probe_browser_headers_result',
          requestId: msg.requestId || null,
          success: false,
          error: `No tab found for ${msg.email}`,
        });
        break;
      }

      try {
        console.log(`[VEO Bridge] 🔍 Probing browser headers from tab ${tabId} (${msg.email})`);

        // Execute a simple fetch in the page's MAIN world context
        // The URL must be a cross-origin googleapis.com endpoint
        const results = await chrome.scripting.executeScript({
          target: { tabId },
          world: 'MAIN',
          func: async (apiKey) => {
            try {
              // Simple GET to credits endpoint — we don't care about the response,
              // only that Chrome adds x-browser-validation to this cross-origin request
              const resp = await fetch(
                `https://aisandbox-pa.googleapis.com/v1/credits?key=${apiKey}`,
                {
                  method: 'GET',
                  credentials: 'include',
                  headers: {
                    'Content-Type': 'application/json',
                    'Origin': 'https://labs.google',
                    'Referer': 'https://labs.google/',
                  },
                }
              );
              return { status: resp.status, triggered: true };
            } catch (e) {
              // Even if the fetch fails (CORS, etc.), the webRequest listener
              // should have already captured the headers before the response
              return { triggered: true, error: e.message };
            }
          },
          args: [msg.apiKey || 'AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY'],
        });

        const result = results?.[0]?.result;

        // Wait a bit for webRequest listener to process
        await new Promise(r => setTimeout(r, 500));

        // Send current state of headers back
        const state = tabState[tabId];
        const currentHeaders = state ? { ...state.headers } : {};

        // Also inject global x-browser-validation if captured
        if (globalBrowserValidation && !currentHeaders['x-browser-validation']) {
          currentHeaders['x-browser-validation'] = globalBrowserValidation;
        }

        wsSend({
          action: 'probe_browser_headers_result',
          requestId: msg.requestId || null,
          email: msg.email,
          success: true,
          probeResult: result,
          headers: currentHeaders,
          hasValidation: !!currentHeaders['x-browser-validation'],
          globalValidation: globalBrowserValidation,
        });

        // Also push a headers_update if we now have x-browser-validation
        if (state?.email && currentHeaders['x-browser-validation']) {
          if (state) Object.assign(state.headers, currentHeaders);
          wsSend({
            action: 'headers_update',
            email: state.email,
            headers: currentHeaders,
            accessToken: state?.accessToken,
          });
        }
      } catch (e) {
        console.error(`[VEO Bridge] Probe failed: ${e.message}`);
        wsSend({
          action: 'probe_browser_headers_result',
          requestId: msg.requestId || null,
          success: false,
          error: e.message,
        });
      }
      break;
    }
  }
}


// ── Header Interception ────────────────────────────────────────────────

chrome.webRequest.onBeforeSendHeaders.addListener(
  (details) => {
    if (!details.requestHeaders) return;

    const headers = {};
    let authHeader = null;

    for (const h of details.requestHeaders) {
      const name = h.name.toLowerCase();

      // Capture x-browser-* headers
      if (BROWSER_HEADERS.includes(name)) {
        headers[name] = h.value;
      }

      // Capture Authorization — ONLY Bearer tokens (OAuth2 access tokens).
      // SAPISIDHASH is Google's 1st-party internal auth (accounts.google.com)
      // and must NOT be used for VEO API calls (causes 403).
      // HAR-verified: VEO API requires "Bearer ya29..." format.
      if (name === 'authorization' && h.value && h.value.startsWith('Bearer ')) {
        authHeader = h.value;
      }
    }

    // Store x-browser-validation globally (from ANY request, even Chrome internal)
    if (headers['x-browser-validation']) {
      globalBrowserValidation = headers['x-browser-validation'];
      console.log(`[VEO Bridge] 🔒 Captured x-browser-validation globally: ${globalBrowserValidation.substring(0, 10)}... (tabId=${details.tabId}, url=${details.url.substring(0, 60)})`);
    }

    // For non-tab requests (Chrome internal), only capture global x-browser-validation above
    if (details.tabId < 0) return;
    if (!tabState[details.tabId]) return; // Only update per-tab state for registered tabs

    // Nothing useful captured for per-tab state
    if (Object.keys(headers).length === 0 && !authHeader) return;

    const state = tabState[details.tabId];

    // Merge headers (don't overwrite with empty)
    Object.assign(state.headers, headers);

    // Inject global x-browser-validation if not already present in per-tab headers
    if (globalBrowserValidation && !state.headers['x-browser-validation']) {
      state.headers['x-browser-validation'] = globalBrowserValidation;
    }

    if (authHeader) {
      state.accessToken = authHeader;
    }

    // Auto-push to app if connected and we have an email (debounced)
    if (state.email && Object.keys(headers).length > 0) {
      const email = state.email;
      // Clear existing timer — restart debounce window
      if (_headersDebounceTimers[email]) {
        clearTimeout(_headersDebounceTimers[email]);
      }
      _headersDebounceTimers[email] = setTimeout(() => {
        delete _headersDebounceTimers[email];
        const s = tabState[details.tabId];
        if (s && s.email) {
          wsSend({
            action: 'headers_update',
            email: s.email,
            headers: s.headers,
            accessToken: s.accessToken,
          });
        }
      }, HEADERS_DEBOUNCE_MS);
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

    // ★ Fix #4: Prevent Chrome from discarding/suspending this tab
    // Chrome Energy Saver suspends background tabs, killing reCAPTCHA widget
    // and causing token generation failures. autoDiscardable: false prevents this.
    try {
      chrome.tabs.update(tabId, { autoDiscardable: false });
      console.log(`[VEO Bridge] Tab ${tabId} marked autoDiscardable=false (anti-suspend)`);
    } catch (e) {
      console.debug(`[VEO Bridge] autoDiscardable update failed for tab ${tabId}: ${e.message}`);
    }

    // Notify app
    wsSend({
      action: 'register',
      email: msg.email,
      tabId: tabId,
      version: EXT_VERSION,
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
  // GAP #10: Content.js warmth check runs in isolated world and can't see
  // grecaptcha in MAIN world → false negatives. Override with MAIN world check.
  if (msg.action === 'recaptcha_warmth' && sender.tab) {
    const tabId = sender.tab.id;
    const state = tabState[tabId];
    if (state) {
      // Wrap in async IIFE — onMessage callback is not async
      (async () => {
        try {
          const results = await chrome.scripting.executeScript({
            target: { tabId },
            world: 'MAIN',
            func: () => {
              const hasGrecaptcha = typeof grecaptcha !== 'undefined';
              const hasEnterprise = hasGrecaptcha && typeof grecaptcha.enterprise !== 'undefined';
              const hasExecute = hasEnterprise && typeof grecaptcha.enterprise.execute === 'function';
              let hasSiteKey = false;
              for (const s of document.querySelectorAll('script[src*="recaptcha"]')) {
                const m = s.src.match(/render=([^&]+)/);
                if (m && m[1] !== 'explicit') { hasSiteKey = true; break; }
              }
              return {
                ready: hasExecute && hasSiteKey,
                grecaptcha: hasGrecaptcha,
                enterprise: hasEnterprise,
                execute: hasExecute,
                siteKey: hasSiteKey,
              };
            },
          });
          const mainResult = results?.[0]?.result;
          if (mainResult) {
            state.recaptchaReady = mainResult.ready;
            wsSend({
              action: 'recaptcha_warmth',
              email: state.email || msg.email,
              ready: mainResult.ready,
              details: mainResult,
            });
          }
        } catch (e) {
          // Fallback to content.js report if MAIN world check fails
          state.recaptchaReady = msg.ready;
          wsSend({
            action: 'recaptcha_warmth',
            email: state.email || msg.email,
            ready: msg.ready,
            details: msg.details,
          });
        }
        sendResponse({ ok: true });
      })();
      return true; // Keep sendResponse alive for async IIFE
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
    // Auto-reload to restore content script (with cooldown protection)
    setTimeout(() => {
      safeTabReload(tabId, 'memory-saver-discard');
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


// ── Tab Close Detection — Reassign Email to Remaining VEO Tab ──────────
// When a VEO tab with a registered email is closed, find another VEO tab
// and reassign the email so operations can continue without interruption.

chrome.tabs.onRemoved.addListener(async (tabId, removeInfo) => {
  const state = tabState[tabId];
  if (!state || !state.email) {
    // Tab wasn't tracked or had no email — just clean up
    delete tabState[tabId];
    delete tabLastReloadTime[tabId];
    return;
  }

  const orphanedEmail = state.email;
  console.warn(`[VEO Bridge] ❌ Tab ${tabId} (${orphanedEmail}) closed — looking for replacement...`);

  // Clean up closed tab state
  delete tabState[tabId];
  delete tabLastReloadTime[tabId];
  delete shortTokenCounts[tabId];

  // Notify app that the email's tab was closed
  wsSend({
    action: 'tab_closed',
    email: orphanedEmail,
    tabId: tabId,
  });

  // Check if email is already assigned to another tab (e.g., duplicate registration)
  const existingTabId = findTabForEmail(orphanedEmail);
  if (existingTabId) {
    console.log(`[VEO Bridge] ✅ Email ${orphanedEmail} already registered on tab ${existingTabId}`);
    wsSend({ action: 'register', email: orphanedEmail, tabId: existingTabId, version: EXT_VERSION });
    return;
  }

  // Find another VEO tab without an email assignment
  try {
    const veoTabs = await chrome.tabs.query({ url: '*://labs.google/*' });
    // Prefer unassigned tab, fallback to any VEO tab
    let targetTab = veoTabs.find(t => t.id !== tabId && !tabState[t.id]?.email);
    if (!targetTab) {
      targetTab = veoTabs.find(t => t.id !== tabId);
    }

    if (targetTab) {
      const newTabId = targetTab.id;
      if (!tabState[newTabId]) {
        tabState[newTabId] = { email: null, headers: {}, accessToken: null, lastHeartbeat: 0, recaptchaReady: false };
      }
      tabState[newTabId].email = orphanedEmail;
      console.log(`[VEO Bridge] 🔄 Reassigned ${orphanedEmail} to existing VEO tab ${newTabId}`);

      // Inject content.js to ensure the tab can communicate
      try {
        await chrome.scripting.executeScript({
          target: { tabId: newTabId },
          files: ['content.js'],
        });
      } catch (e) {
        console.debug(`[VEO Bridge] Content.js inject on reassign: ${e.message}`);
      }

      // Re-register with Python app
      wsSend({ action: 'register', email: orphanedEmail, tabId: newTabId, version: EXT_VERSION });

      // Prevent Chrome from discarding this tab (same as initial registration)
      try { chrome.tabs.update(newTabId, { autoDiscardable: false }); } catch (_) { }

      // Push any cached headers from the new tab
      const newState = tabState[newTabId];
      if (Object.keys(newState.headers).length > 0) {
        wsSend({
          action: 'headers_update',
          email: orphanedEmail,
          headers: newState.headers,
          accessToken: newState.accessToken,
        });
      }
    } else {
      console.warn(`[VEO Bridge] ⚠️ No remaining VEO tab for ${orphanedEmail} — will reconnect when new tab opens`);
    }
  } catch (e) {
    console.error(`[VEO Bridge] Tab reassignment failed: ${e.message}`);
  }
});

function checkHeartbeats() {
  const now = Date.now();
  for (const [tabId, state] of Object.entries(tabState)) {
    if (!state.email || !state.lastHeartbeat) continue;

    const elapsed = now - state.lastHeartbeat;
    if (elapsed > HEARTBEAT_TIMEOUT) {
      // Initialize reload tracking per tab
      if (!state._frozenReloadCount) state._frozenReloadCount = 0;
      if (!state._frozenWindowStart) state._frozenWindowStart = now;

      // Reset window if expired
      if (now - state._frozenWindowStart > FROZEN_RELOAD_WINDOW) {
        state._frozenReloadCount = 0;
        state._frozenWindowStart = now;
      }

      state._frozenReloadCount++;

      if (state._frozenReloadCount > FROZEN_RELOAD_MAX) {
        // Tab is truly dead — stop reloading, notify Python
        if (state._frozenReloadCount === FROZEN_RELOAD_MAX + 1) {
          console.error(
            `[VEO Bridge] 💀 Tab ${tabId} (${state.email}) DEAD — ` +
            `${FROZEN_RELOAD_MAX} reloads failed in ${FROZEN_RELOAD_WINDOW / 1000}s`
          );
          wsSend({
            action: 'tab_dead',
            email: state.email,
            tabId: parseInt(tabId),
            reloadAttempts: FROZEN_RELOAD_MAX,
            elapsedMs: elapsed,
          });
        }
        // Don't reload — just wait for manual intervention or window reset
        continue;
      }

      console.warn(
        `[VEO Bridge] ⚠️ Tab ${tabId} (${state.email}) missed heartbeat ` +
        `(${Math.floor(elapsed / 1000)}s ago) — ` +
        `reload attempt ${state._frozenReloadCount}/${FROZEN_RELOAD_MAX}`
      );

      // Notify Python app about the frozen tab
      wsSend({
        action: 'tab_frozen',
        email: state.email,
        tabId: parseInt(tabId),
        lastHeartbeat: state.lastHeartbeat,
        elapsedMs: elapsed,
        reloadAttempt: state._frozenReloadCount,
      });

      // Try to wake it up by reloading (with cooldown protection)
      safeTabReload(parseInt(tabId), `heartbeat-frozen-attempt-${state._frozenReloadCount}`).then(didReload => {
        if (didReload) {
          state.lastHeartbeat = now; // Reset to avoid immediate re-trigger
        }
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

// Close excess tabs whenever a new tab is created
chrome.tabs.onCreated.addListener((tab) => {
  // Delay cleanup slightly to allow the tab to settle (URL may still be about:blank)
  setTimeout(() => {
    closeExcessTabs().then(() => ensureVeoTab());
  }, 3000);
});


// ── Helpers ─────────────────────────────────────────────────────────────

function findTabForEmail(email) {
  for (const [tabId, state] of Object.entries(tabState)) {
    if (state.email === email) {
      return parseInt(tabId);
    }
  }
  // GAP #6: Removed fallback that returned ANY tab with an email.
  // Returning a wrong account's tab causes cross-account reCAPTCHA tokens.
  // Callers must handle null explicitly.
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
const TAB_CLEANUP_ALARM = 'tab-cleanup';

// Chrome suspends service workers after ~30s of inactivity.
// Reduced from 30s to 20s for faster keepalive.
chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: 0.33 });
// Refresh headers every 3 minutes via lightweight fetch (instead of 5 min full reload)
chrome.alarms.create(HEADER_REFRESH_ALARM, { periodInMinutes: 3 });
// Periodic tab cleanup every 2 minutes
chrome.alarms.create(TAB_CLEANUP_ALARM, { periodInMinutes: 2 });

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

  if (alarm.name === TAB_CLEANUP_ALARM) {
    closeExcessTabs().then(() => ensureVeoTab());
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
        const didReload = await safeTabReload(tab.id, 'header-refresh');
        if (didReload) reloaded++;
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

const VEO_URL = 'https://labs.google/fx/vi/tools/flow';
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

    // No VEO tab found — cleanup excess tabs first to make room
    let allTabs = await chrome.tabs.query({ currentWindow: true });
    if (allTabs.length >= MAX_TABS) {
      console.log(`[VEO Bridge] Tab limit reached (${allTabs.length}/${MAX_TABS}) — cleaning up to make room for VEO tab...`);
      await closeExcessTabs();
      // Re-check after cleanup
      allTabs = await chrome.tabs.query({ currentWindow: true });
      if (allTabs.length >= MAX_TABS) {
        // Still at limit — force-close one non-VEO tab to make room
        const nonVeo = allTabs.filter(t => !(t.url || '').includes('labs.google'));
        if (nonVeo.length > 0) {
          const victim = nonVeo[nonVeo.length - 1]; // close last non-VEO tab
          try {
            await chrome.tabs.remove(victim.id);
            if (tabState[victim.id]) delete tabState[victim.id];
            console.log(`[VEO Bridge] 🔻 Force-closed tab ${victim.id} to make room for VEO tab`);
          } catch (e) {
            console.debug(`[VEO Bridge] Could not force-close tab: ${e.message}`);
          }
        } else {
          console.warn(`[VEO Bridge] ⚠️ All tabs are VEO-related, cannot make room`);
          return;
        }
      }
    }

    console.log(`[VEO Bridge] 🆕 No VEO tab found, opening one...`);
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

chrome.runtime.onInstalled.addListener(async () => {
  console.log('[VEO Bridge] Extension installed/updated');
  chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: 0.33 });

  // Register stealth script to override navigator.webdriver BEFORE reCAPTCHA loads.
  // CDP sets webdriver=true which tanks reCAPTCHA scores → 403 on every request.
  // Uses programmatic registration (not manifest) so it fails gracefully if
  // Chrome version doesn't support world: 'MAIN'.
  try {
    // Unregister first (idempotent — avoids "already registered" errors on update)
    try { await chrome.scripting.unregisterContentScripts({ ids: ['stealth'] }); } catch (_) { }
    await chrome.scripting.registerContentScripts([{
      id: 'stealth',
      matches: ['*://labs.google/*'],
      js: ['stealth.js'],
      runAt: 'document_start',
      world: 'MAIN',
    }]);
    console.log('[VEO Bridge] ✅ Stealth script registered (navigator.webdriver override)');
  } catch (e) {
    console.warn('[VEO Bridge] ⚠️ Stealth script registration failed (Chrome too old?):', e.message);
  }

  connectWebSocket();
  // Inject into already-open VEO tabs, clean up excess, then ensure one exists
  injectExistingTabs().then(() => {
    closeExcessTabs();
    ensureVeoTab();
  });
});

// ── Startup ─────────────────────────────────────────────────────────────

connectWebSocket();
// Also inject on service worker startup (not just install)
injectExistingTabs().then(() => {
  closeExcessTabs(); // Clean up any accumulated tabs first
  ensureVeoTab();
});
console.log('[VEO Bridge] Background service worker started');


// ── Tab Cleanup ─────────────────────────────────────────────────────────
// Close excess tabs beyond MAX_TABS limit.
// Priority: about:blank > unrecognized > other allowed (Gmail, YouTube)
// VEO tabs (labs.google) are IMMUNE — never closed by cleanup.

const ALLOWED_URL_FRAGMENTS = [
  'mail.google.com',       // Gmail
  'youtube.com',           // YouTube
  'labs.google',           // Google Flow (VEO) — protected separately
];

async function closeExcessTabs() {
  try {
    const allTabs = await chrome.tabs.query({ currentWindow: true });
    if (allTabs.length <= MAX_TABS) return 0;

    console.log(`[VEO Bridge] Tab cleanup: ${allTabs.length} tabs found (max=${MAX_TABS})`);

    // Categorize tabs — VEO tabs are PROTECTED (never closed)
    const veoTabs = [];      // labs.google — IMMUNE from cleanup
    const otherAllowed = [];  // Gmail, YouTube — closeable if over limit
    const blank = [];         // about:blank, chrome://newtab — first to close
    const other = [];         // unrecognized URLs — second to close

    for (const tab of allTabs) {
      const url = tab.url || '';
      if (url === 'about:blank' || url === 'chrome://newtab/' || url === '') {
        blank.push(tab);
      } else if (url.includes('labs.google')) {
        veoTabs.push(tab);  // PROTECTED — never added to close list
      } else if (ALLOWED_URL_FRAGMENTS.some(frag => url.includes(frag))) {
        otherAllowed.push(tab);
      } else {
        other.push(tab);
      }
    }

    // How many non-VEO tabs can we keep? (VEO tabs always survive)
    const maxCloseable = allTabs.length - MAX_TABS;

    // Build close list: blank > other > excess otherAllowed
    // VEO tabs are NEVER included
    const candidates = [...blank, ...other, ...otherAllowed];
    const toClose = candidates.slice(0, maxCloseable);

    // Keep at least 1 tab alive total
    while (toClose.length > 0 && allTabs.length - toClose.length < 1) {
      toClose.pop();
    }

    let closed = 0;
    for (const tab of toClose) {
      try {
        await chrome.tabs.remove(tab.id);
        // Also clean up tabState
        if (tabState[tab.id]) {
          delete tabState[tab.id];
        }
        closed++;
        console.log(`[VEO Bridge] Closed excess tab ${tab.id}: ${(tab.url || '?').substring(0, 60)}`);
      } catch (e) {
        console.debug(`[VEO Bridge] Could not close tab ${tab.id}: ${e.message}`);
      }
    }

    if (closed > 0) {
      console.log(`[VEO Bridge] Tab cleanup complete: closed ${closed} tab(s), ${veoTabs.length} VEO tab(s) protected`);
    }
    return closed;
  } catch (e) {
    console.error('[VEO Bridge] closeExcessTabs failed:', e);
    return 0;
  }
}