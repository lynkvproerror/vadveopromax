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
const EXT_VERSION = chrome.runtime.getManifest().version; // e.g. '2.3.0'
const MAX_TABS = 3; // Maximum number of browser tabs allowed (Gmail, YouTube, VEO Flow)
const LAST_GOOD_PORT_KEY = 'veo_bridge_last_good_port';

// WebSocket is now managed by offscreen.js (persistent, not subject to SW suspension).
// background.js relays messages via chrome.runtime.
let wsConnected = false;

// Per-tab state: tabId → {email, headers, accessToken, lastHeartbeat, recaptchaReady}
const tabState = {};

// Fix G: Guard flag — prevents onWsConnected from running before tabState is restored
let _tabStateRestored = false;

// Fix J: Message queue for when offscreen is restarting
let _wsSendQueue = [];
const _bridgeDebug = {
  bgStartedAt: Date.now(),
  lastOffscreenCreatedAt: 0,
  lastOffscreenSyncAt: 0,
  lastOffscreenSyncOk: null,
  lastOffscreenSyncError: '',
  lastOffscreenEvent: 'startup',
  offscreen: null,
  lastWsConnectedAt: 0,
  lastWsDisconnectedAt: 0,
  lastTabRegisterAt: 0,
  lastTabRegisterEmail: '',
  lastQueuedAction: '',
  lastQueuedAt: 0,
  lastSentAction: '',
  lastSentAt: 0,
  lastGetStatusAt: 0,
};
const SNAPSHOT_PUSH_COOLDOWN_MS = 20000;
const _lastSnapshotPushAt = {};

// ── tabState Persistence ───────────────────────────────────────────────
// MV3 service workers get terminated/restarted by Chrome.
// Without persistence, tabState is lost → onWsConnected sends nothing
// → Python sees unregistered connection → "extension disconnected".
let _persistTimer = null;
function persistTabState() {
  // Debounce: batch rapid changes into one write
  if (_persistTimer) clearTimeout(_persistTimer);
  _persistTimer = setTimeout(() => {
    const serializable = {};
    for (const [tabId, state] of Object.entries(tabState)) {
      serializable[tabId] = {
        email: state.email,
        headers: state.headers || {},
        accessToken: state.accessToken,
        lastHeartbeat: state.lastHeartbeat,
        recaptchaReady: state.recaptchaReady || false,
        // Lifecycle state (survive SW restart)
        _lifecycle: state._lifecycle || TAB_LIFECYCLE.ALIVE,
        _lifecycleAt: state._lifecycleAt || 0,
        _recoveryAttempts: state._recoveryAttempts || 0,
        _deadNotified: state._deadNotified || false,
        _registerGeneration: state._registerGeneration || 0,
        // Timer state (survive SW restart)
        _frozenWindowStart: state._frozenWindowStart || 0,
        _lastReloadAt: state._lastReloadAt || 0,
      };
    }
    chrome.storage.session.set({ tabState: serializable }).catch(() => { });
  }, 1000);
}

async function restoreTabState() {
  try {
    const result = await chrome.storage.session.get('tabState');
    if (result.tabState && Object.keys(result.tabState).length > 0) {
      // Verify tabs still exist AND have valid URLs before restoring
      for (const [tabId, state] of Object.entries(result.tabState)) {
        try {
          const tab = await chrome.tabs.get(parseInt(tabId));
          // RC3 FIX: Skip about:blank and chrome:// tabs — they cause
          // Chrome to consider offscreen doc unnecessary and kill it
          if (tab && tab.url && !tab.url.startsWith('about:') && !tab.url.startsWith('chrome:')) {
            tabState[tabId] = state;

            // ★ Recompute lifecycle after SW restart
            const isVeoPage = tab.url && tab.url.includes('labs.google');
            const now = Date.now();

            // Reset stale frozen window — old attempts shouldn't count
            if (state._frozenWindowStart &&
              (now - state._frozenWindowStart) > FROZEN_RELOAD_WINDOW) {
              state._recoveryAttempts = 0;
              state._frozenWindowStart = 0;
              persistTabState(); // P2: persist timer reset across SW restart
            }

            if (state._lifecycle === TAB_LIFECYCLE.DEAD) {
              // Keep DEAD — user must intervene
            } else if (state._lifecycle === TAB_LIFECYCLE.SUSPENDED && !isVeoPage) {
              // Still on non-VEO page — keep SUSPENDED
            } else if (!isVeoPage) {
              setLifecycle(tabId, TAB_LIFECYCLE.SUSPENDED);
            } else if (state._lifecycle === TAB_LIFECYCLE.RELOADING ||
              state._lifecycle === TAB_LIFECYCLE.NAVIGATING ||
              state._lifecycle === TAB_LIFECYCLE.RECOVERING) {
              if (tab.status === 'complete') {
                setLifecycle(tabId, TAB_LIFECYCLE.RECOVERING);
              }
              // If still loading, keep current state — onUpdated will handle
            } else {
              // ALIVE or unknown — set RECOVERING (content.js may need re-init)
              setLifecycle(tabId, TAB_LIFECYCLE.RECOVERING);
            }
          } else if (tab) {
            console.debug(`[VEO Bridge] Skipping restored tab ${tabId} (URL: ${tab.url || 'none'})`);
          }
        } catch (_) {
          // Tab no longer exists — skip
        }
      }
      if (Object.keys(tabState).length > 0) {
        console.log(`[VEO Bridge] ✅ Restored ${Object.keys(tabState).length} tab state(s) from session storage`);
        return;
      }
    }
  } catch (e) {
    console.debug('[VEO Bridge] Session storage restore failed:', e.message);
  }

  // Fallback: discover VEO tabs by URL (only real VEO pages, not about:blank)
  try {
    const tabs = await chrome.tabs.query({ url: '*://labs.google/*' });
    for (const tab of tabs) {
      // RC3 FIX: Double-check URL is actually labs.google (not about:blank)
      if (!tabState[tab.id] && tab.url && tab.url.includes('labs.google')) {
        tabState[tab.id] = {
          email: null, headers: {}, accessToken: null,
          lastHeartbeat: 0, recaptchaReady: false,
        };
      }
    }
    if (tabs.length > 0) {
      console.log(`[VEO Bridge] 🔍 Discovered ${tabs.length} VEO tab(s) (no stored state)`);
    }
  } catch (e) {
    console.debug('[VEO Bridge] Tab discovery failed:', e.message);
  }
}

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
// NOTE: tabLastReloadTime replaced by tabState[tabId]._lastReloadAt (persisted)

// ── Tab Lifecycle State Machine ───────────────────────────────────────
// Prevents false "Tab DEAD" by tracking tab transitions explicitly.
// Watchdog skips heartbeat checks during NAVIGATING/RELOADING/RECOVERING/SUSPENDED.
const TAB_LIFECYCLE = {
  ALIVE: 'alive',
  NAVIGATING: 'navigating',  // Tab navigating/loading within VEO scope
  RELOADING: 'reloading',    // Explicit reload issued, waiting for status=complete
  RECOVERING: 'recovering',  // Reload done + complete, waiting for real heartbeat
  SUSPENDED: 'suspended',    // Tab navigated outside labs.google — watchdog skips
  DEAD: 'dead',
};

const RELOAD_RESULT = {
  RELOADED: 'reloaded',
  SKIPPED_COOLDOWN: 'skipped',
  FAILED: 'failed',
};

/**
 * Set tab lifecycle state and persist. ALL lifecycle mutations MUST go through this.
 * @param {string|number} tabId
 * @param {string} newState - TAB_LIFECYCLE value
 * @param {Object} extraFields - additional fields to merge (e.g. _recoveryAttempts)
 */
function setLifecycle(tabId, newState, extraFields = {}) {
  const state = tabState[tabId];
  if (!state) return;
  state._lifecycle = newState;
  state._lifecycleAt = Date.now();
  Object.assign(state, extraFields);
  persistTabState(); // Debounced — batches rapid changes
}

/**
 * Reload a tab with cooldown protection and lifecycle management.
 * safeTabReload() OWNS the RELOADING state — callers must NOT pre-set it.
 * Returns RELOAD_RESULT enum.
 */
async function safeTabReload(tabId, reason, bypassCache = false) {
  const now = Date.now();
  const state = tabState[tabId];
  const lastReload = state?._lastReloadAt || 0;
  const elapsed = now - lastReload;

  if (elapsed < RELOAD_COOLDOWN_MS) {
    console.debug(
      `[VEO Bridge] ⏳ Skipping reload for tab ${tabId} — ` +
      `cooldown active (${Math.ceil((RELOAD_COOLDOWN_MS - elapsed) / 1000)}s remaining, reason: ${reason})`
    );
    return RELOAD_RESULT.SKIPPED_COOLDOWN;
  }

  // ★ Save previous lifecycle to revert on failure
  const prevLifecycle = state?._lifecycle;

  // ★ Set RELOADING before reload attempt (owns this state)
  setLifecycle(tabId, TAB_LIFECYCLE.RELOADING);

  try {
    // Notify Python to suspend zombie detection
    if (state && state.email) {
      wsSend({
        action: 'tab_reloading',
        email: state.email,
        tabId: tabId,
        gracePeriodMs: 60000,
        reason: reason,
      });
    }

    await chrome.tabs.reload(tabId, { bypassCache });
    if (tabState[tabId]) {
      tabState[tabId]._lastReloadAt = now;
      persistTabState(); // P2: persist reload timestamp across SW restart
    }
    // ★ Do NOT set lastHeartbeat = now — that fakes liveness.
    // Stay in RELOADING — onUpdated will transition to RECOVERING.
    console.log(`[VEO Bridge] 🔄 Reloaded tab ${tabId} (reason: ${reason})`);
    return RELOAD_RESULT.RELOADED;
  } catch (e) {
    console.debug(`[VEO Bridge] Tab ${tabId} reload failed: ${e.message}`);
    // ★ Revert lifecycle — don't leave stuck in RELOADING
    setLifecycle(tabId, prevLifecycle || TAB_LIFECYCLE.ALIVE);
    return RELOAD_RESULT.FAILED;
  }
}


/**
 * Send a message to a content script with auto-retry on failure.
 * If first attempt fails (content script not loaded), re-injects content.js
 * and retries after 3s.
 */
async function sendMessageWithRetry(tabId, message, maxRetries = 1) {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await chrome.tabs.sendMessage(tabId, message);
    } catch (e) {
      if (attempt < maxRetries) {
        console.log(
          `[VEO Bridge] 🔁 sendMessage failed for tab ${tabId}, ` +
          `re-injecting content.js (retry ${attempt + 1}/${maxRetries})`
        );
        try {
          await chrome.scripting.executeScript({
            target: { tabId },
            files: ['content.js'],
          });
          await new Promise(r => setTimeout(r, 3000)); // Wait for content.js to init
        } catch (injectErr) {
          console.debug(`[VEO Bridge] Re-inject failed: ${injectErr.message}`);
        }
      } else {
        throw e;
      }
    }
  }
}


// ── Offscreen Document Management ──────────────────────────────────────
// WebSocket lives in offscreen.js — persistent, never suspended by Chrome.
// background.js manages its lifecycle and relays messages.

let _offscreenCreating = null; // Promise guard against concurrent creation

async function ensureOffscreenDocument() {
  // Check if offscreen doc already exists
  const existingContexts = await chrome.runtime.getContexts({
    contextTypes: ['OFFSCREEN_DOCUMENT'],
    documentUrls: [chrome.runtime.getURL('offscreen.html')],
  });
  if (existingContexts.length > 0) {
    return; // Already exists
  }

  // Prevent concurrent creation
  if (_offscreenCreating) {
    await _offscreenCreating;
    return;
  }

  // Fix I: Retry up to 3 times with 2s delay on creation failure
  for (let attempt = 1; attempt <= 3; attempt++) {
    _offscreenCreating = chrome.offscreen.createDocument({
      url: 'offscreen.html',
      reasons: ['WORKERS'],  // MV3 reason for persistent background work
      justification: 'Persistent WebSocket connection to Python app',
    });

    try {
      await _offscreenCreating;
      console.log('[VEO Bridge] ✅ Offscreen document created for persistent WebSocket');
      _bridgeDebug.lastOffscreenCreatedAt = Date.now();
      _offscreenCreating = null;
      return; // Success
    } catch (e) {
      _offscreenCreating = null;
      if (attempt < 3) {
        console.warn(`[VEO Bridge] ⚠️ Offscreen creation failed (attempt ${attempt}/3): ${e.message} — retrying in 2s...`);
        await new Promise(r => setTimeout(r, 2000));
      } else {
        console.error(`[VEO Bridge] ❌ Offscreen creation failed after 3 attempts: ${e.message}`);
      }
    }
  }
}

async function getOffscreenWsStatus() {
  try {
    const status = await chrome.runtime.sendMessage({ type: 'offscreen_ws_status' });
    if (status) {
      _bridgeDebug.offscreen = status;
    }
    return status || null;
  } catch (e) {
    _bridgeDebug.lastOffscreenSyncError = e.message || 'offscreen_status_failed';
    return null;
  }
}

async function getOffscreenContextCount() {
  try {
    const contexts = await chrome.runtime.getContexts({
      contextTypes: ['OFFSCREEN_DOCUMENT'],
      documentUrls: [chrome.runtime.getURL('offscreen.html')],
    });
    return contexts.length;
  } catch (_) {
    return 0;
  }
}

/**
 * Re-sync background.js with the already-running offscreen document.
 *
 * Why this matters:
 * - MV3 service workers restart frequently and lose in-memory `wsConnected`
 * - offscreen.js may still hold a live WebSocket to Python
 * - without an explicit status query, background stays "disconnected"
 *   forever until the socket reconnects again, so tabs remain orange
 *
 * Returns true if offscreen reports a live WebSocket.
 */
async function syncOffscreenWsState() {
  _bridgeDebug.lastOffscreenSyncAt = Date.now();
  try {
    const status = await getOffscreenWsStatus();
    const wasConnected = wsConnected;
    wsConnected = !!(status && status.connected);
    _bridgeDebug.lastOffscreenSyncOk = wsConnected;
    _bridgeDebug.lastOffscreenSyncError = '';

    if (wsConnected && !wasConnected) {
      console.log('[VEO Bridge] ♻️ Re-synced live WebSocket from existing offscreen document');
      await onWsConnected();
    } else if (!wsConnected && wasConnected) {
      console.log('[VEO Bridge] ⚠️ Offscreen reported WebSocket disconnected during resync');
    }

    return wsConnected;
  } catch (e) {
    _bridgeDebug.lastOffscreenSyncOk = false;
    _bridgeDebug.lastOffscreenSyncError = e.message || 'offscreen_sync_failed';
    console.debug('[VEO Bridge] Offscreen WS sync failed:', e.message);
    return false;
  }
}

/**
 * Recover the offscreen bridge eagerly instead of waiting for the watchdog.
 *
 * This is used on high-signal events such as:
 * - a VEO tab registering itself
 * - popup status checks while disconnected
 *
 * Without this, a missing offscreen document can leave the bridge orange/red
 * until the 15s watchdog and 45s startup grace eventually allow recreation.
 */
async function ensureBridgeReady(reason = 'unknown') {
  let offscreenCount = await getOffscreenContextCount();
  if (offscreenCount === 0) {
    console.warn(`[VEO Bridge] 🧩 Offscreen missing during ${reason} — recreating now`);
    await ensureOffscreenDocument();
    offscreenCount = await getOffscreenContextCount();
  }

  let status = await getOffscreenWsStatus();

  if (
    offscreenCount > 0 &&
    status &&
    !status.connected &&
    !status.reconnectScheduled &&
    !status.fastScanActive
  ) {
    console.log(`[VEO Bridge] 🔁 Forcing offscreen WS reconnect (${reason})`);
    try {
      await chrome.runtime.sendMessage({ type: 'offscreen_ws_reconnect' });
      await new Promise(r => setTimeout(r, 250));
      status = await getOffscreenWsStatus();
    } catch (e) {
      console.debug('[VEO Bridge] Forced offscreen reconnect failed:', e.message);
    }
  }

  return syncOffscreenWsState();
}

async function collectBridgeStatus(forceSync = false) {
  _bridgeDebug.lastGetStatusAt = Date.now();

  if (forceSync || !wsConnected) {
    await ensureBridgeReady(forceSync ? 'popup_status' : 'status_refresh');
  }

  const offscreen = await getOffscreenWsStatus();
  const offscreenCount = await getOffscreenContextCount();

  return {
    connected: wsConnected,
    port: (offscreen && offscreen.currentPort) || null,
    tabs: Object.entries(tabState)
      .filter(([_, s]) => s.email)
      .map(([id, s]) => ({
        tabId: parseInt(id),
        email: s.email,
        headerCount: Object.keys(s.headers).length,
        lastHeartbeat: s.lastHeartbeat || 0,
        recaptchaReady: s.recaptchaReady || false,
      })),
    debug: {
      offscreenExists: offscreenCount > 0,
      offscreenCount,
      background: {
        startedAt: _bridgeDebug.bgStartedAt,
        tabStateRestored: _tabStateRestored,
        wsConnected,
        wsQueueDepth: _wsSendQueue.length,
        lastOffscreenCreatedAt: _bridgeDebug.lastOffscreenCreatedAt,
        lastOffscreenSyncAt: _bridgeDebug.lastOffscreenSyncAt,
        lastOffscreenSyncOk: _bridgeDebug.lastOffscreenSyncOk,
        lastOffscreenSyncError: _bridgeDebug.lastOffscreenSyncError,
        lastOffscreenEvent: _bridgeDebug.lastOffscreenEvent,
        lastWsConnectedAt: _bridgeDebug.lastWsConnectedAt,
        lastWsDisconnectedAt: _bridgeDebug.lastWsDisconnectedAt,
        lastTabRegisterAt: _bridgeDebug.lastTabRegisterAt,
        lastTabRegisterEmail: _bridgeDebug.lastTabRegisterEmail,
        lastQueuedAction: _bridgeDebug.lastQueuedAction,
        lastQueuedAt: _bridgeDebug.lastQueuedAt,
        lastSentAction: _bridgeDebug.lastSentAction,
        lastSentAt: _bridgeDebug.lastSentAt,
        lastGetStatusAt: _bridgeDebug.lastGetStatusAt,
      },
      offscreen: offscreen || _bridgeDebug.offscreen,
    },
  };
}

// ── WebSocket Relay (via Offscreen Document) ───────────────────────────
// wsSend() no longer uses a direct WebSocket. Instead, it sends the data
// to offscreen.js via chrome.runtime.sendMessage, which forwards it over WS.

function wsSend(data) {
  if (!wsConnected) {
    // Fix J: Queue message for when WS reconnects (max 50 to prevent leak)
    if (_wsSendQueue.length < 50) {
      _wsSendQueue.push(data);
    }
    _bridgeDebug.lastQueuedAction = data?.action || '';
    _bridgeDebug.lastQueuedAt = Date.now();
    return false;
  }
  _bridgeDebug.lastSentAction = data?.action || '';
  _bridgeDebug.lastSentAt = Date.now();
  // Send via offscreen.js with error recovery
  chrome.runtime.sendMessage({
    type: 'offscreen_ws_send',
    data: data,
  }).catch(() => {
    // Offscreen doc might be restarting — queue for retry
    if (_wsSendQueue.length < 50) {
      _wsSendQueue.push(data);
    }
  });
  return true;
}

function pushTabSnapshotToApp(tabId, reason = 'snapshot', force = false) {
  const state = tabState[tabId];
  if (!state || !state.email) return false;

  const now = Date.now();
  const lastPushed = _lastSnapshotPushAt[tabId] || 0;
  if (!force && (now - lastPushed) < SNAPSHOT_PUSH_COOLDOWN_MS) {
    return false;
  }
  _lastSnapshotPushAt[tabId] = now;

  wsSend({
    action: 'register',
    email: state.email,
    tabId: parseInt(tabId),
    version: EXT_VERSION,
    source: 'tab_snapshot',  // ★ Layer A: distinguish from cdp_identity
  });

  let pushed = false;
  if (Object.keys(state.headers || {}).length > 0) {
    wsSend({
      action: 'headers_update',
      email: state.email,
      headers: state.headers,
      accessToken: state.accessToken,
    });
    pushed = true;
    console.log(`[VEO Bridge] 📤 Pushed cached headers for ${state.email} (${reason})`);
  }

  if (state.accessToken) {
    wsSend({
      action: 'access_token',
      requestId: null,
      email: state.email,
      token: state.accessToken,
      tokenEmail: state.email,
    });
  }

  return pushed;
}

// Handle WS connection state + reconnect on initial load
async function onWsConnected() {
  console.log('[VEO Bridge] ✅ WebSocket connected (via offscreen)');

  // Fix G: Wait for tabState restore before registering
  // Prevents sending empty tabState when offscreen connects before restore finishes
  if (!_tabStateRestored) {
    console.debug('[VEO Bridge] ⏳ Waiting for tabState restore before registering...');
    const start = Date.now();
    while (!_tabStateRestored && Date.now() - start < 2000) {
      await new Promise(r => setTimeout(r, 100));
    }
    if (!_tabStateRestored) {
      console.warn('[VEO Bridge] ⚠️ tabState restore timed out (2s) — proceeding with current state');
    }
  }

  // Fix J: Flush queued messages first
  if (_wsSendQueue.length > 0) {
    console.log(`[VEO Bridge] 📤 Flushing ${_wsSendQueue.length} queued message(s)`);
    const queue = [..._wsSendQueue];
    _wsSendQueue = [];
    for (const msg of queue) {
      wsSend(msg);
    }
  }

  // ★ Layer A: CDP Deterministic Identity Check
  // Read identity injected by Python app via CDP into chrome.storage.local.
  // This runs BEFORE tab registration so the app knows which profile this is.
  try {
    const stored = await chrome.storage.local.get('__veo_identity');
    const identityEmail = stored.__veo_identity;
    if (identityEmail) {
      console.log(`[VEO Bridge] 🔐 CDP identity found: ${identityEmail}`);
      // Send identity-based register FIRST
      // tabId=null signals Layer A resolved, Layer B tab not yet ready
      wsSend({
        action: 'register',
        email: identityEmail,
        tabId: null,
        version: EXT_VERSION,
        source: 'cdp_identity',
      });
    }
  } catch (e) {
    console.debug('[VEO Bridge] CDP identity check failed:', e.message);
  }

  // Register all known tabs + immediately push cached data
  for (const [tabId, state] of Object.entries(tabState)) {
    if (state.email) {
      pushTabSnapshotToApp(tabId, 'ws_connected', true);

      // Extract fresh access token from page
      extractAndPushToken(parseInt(tabId), state.email);
    }
  }
}


// ── Handle Messages from App ───────────────────────────────────────────

async function handleAppMessage(msg) {
  console.log('[VEO Bridge] App →', msg.action, msg);

  switch (msg.action) {
    case 'request_recaptcha': {
      // Find tab for this email (with stale tab recovery fallback)
      let tabId = findTabForEmail(msg.email);
      if (!tabId) {
        // ★ Stale Tab Recovery: try to discover orphaned VEO tab
        tabId = await recoverStaleTab(msg.email);
      }
      if (!tabId) {
        wsSend({
          action: 'recaptcha_token',
          requestId: msg.requestId,
          token: null,
          error: `No tab found for ${msg.email}`,
        });
        return;
      }

      const flowReady = await ensureTabOnFlow(tabId, 'request_recaptcha');
      if (!flowReady.success) {
        wsSend({
          action: 'recaptcha_token',
          requestId: msg.requestId,
          email: msg.email,
          token: null,
          error: flowReady.error || 'Flow page unavailable',
        });
        return;
      }
      tabId = flowReady.tabId;

      try {
        // Execute directly in page's MAIN world via chrome.scripting API
        // This bypasses CSP (no eval) and isolated world (direct grecaptcha access)
        const scriptPromise = chrome.scripting.executeScript({
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
              if (token && token.length >= 1500) {
                return { token, tokenLength: token.length };
              }
              return { token: null, error: `Token too short (${token ? token.length : 0} chars, need ≥1500)`, tokenLength: token ? token.length : 0 };
            } catch (err) {
              return { token: null, error: err.message, tokenLength: 0 };
            }
          },
          args: [msg.siteKey || null],
        });

        // Fix #1: Timeout guard — prevents grecaptcha.execute() from hanging forever
        // ★ Progressive timeout: use dynamic rcTimeout from Python (default 15000ms)
        const rcTimeoutMs = msg.rcTimeout || 15000;
        const timeoutPromise = new Promise((_, reject) =>
          setTimeout(() => reject(new Error(`reCAPTCHA execute timeout (${rcTimeoutMs / 1000}s) — widget may be frozen`)), rcTimeoutMs)
        );
        const results = await Promise.race([scriptPromise, timeoutPromise]);

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
            const reloadResult = await safeTabReload(tabId, 'short-token-threshold', true);
            if (reloadResult === RELOAD_RESULT.RELOADED) {
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
      // Return cached headers for email after ensuring the tab is on Flow.
      let tabId = findTabForEmail(msg.email);
      if (!tabId && msg.email) {
        const ensured = await ensureFlowForEmail(msg.email, 'request_headers');
        if (ensured.success) tabId = ensured.tabId;
      } else if (tabId) {
        await ensureTabOnFlow(tabId, 'request_headers');
      }
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
      let tabId = findTabForEmail(msg.email);
      if (!tabId && msg.email) {
        const ensured = await ensureFlowForEmail(msg.email, 'request_access_token');
        if (ensured.success) tabId = ensured.tabId;
      }
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

      const flowReady = await ensureTabOnFlow(tabId, 'request_access_token');
      if (!flowReady.success) {
        wsSend({
          action: 'access_token',
          requestId: msg.requestId,
          email: msg.email,
          token: null,
          error: flowReady.error || 'Flow page unavailable',
        });
        return;
      }
      tabId = flowReady.tabId;

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
      // Passive mode: do not reload Flow tabs just to refresh headers. Real
      // page traffic is the only trusted source for browser headers.
      console.log('[VEO Bridge] App requested header refresh — skipped (passive mode)');
      wsSend({
        action: 'headers_refreshed',
        requestId: msg.requestId || null,
        email: msg.email || null,
        tabsReloaded: 0,
        passive: true,
      });
      break;
    }

    case 'ensure_veo_tab': {
      const result = await ensureVeoTabForEmail(msg.email);
      wsSend({
        action: 'ensure_veo_tab_result',
        requestId: msg.requestId || null,
        email: msg.email || null,
        ...result,
      });
      break;
    }

    case 'refresh_headers_lightweight': {
      // Lightweight refresh — tell content.js to trigger a fetch (no page reload)
      console.log('[VEO Bridge] App requested lightweight header refresh');
      let tabId = findTabForEmail(msg.email);
      if (!tabId && msg.email) {
        const ensured = await ensureFlowForEmail(msg.email, 'refresh_headers_lightweight');
        if (ensured.success) tabId = ensured.tabId;
      }
      if (tabId) {
        try {
          const flowReady = await ensureTabOnFlow(tabId, 'refresh_headers_lightweight');
          if (!flowReady.success) throw new Error(flowReady.error || 'Flow page unavailable');
          tabId = flowReady.tabId;
          await chrome.tabs.sendMessage(tabId, { action: 'lightweight_header_refresh' });
          wsSend({
            action: 'headers_refreshed_lightweight',
            requestId: msg.requestId || null,
            email: msg.email || null,
            success: true,
          });
        } catch (e) {
          console.log('[VEO Bridge] Lightweight refresh skipped — content unavailable');
          wsSend({
            action: 'headers_refreshed_lightweight',
            requestId: msg.requestId || null,
            email: msg.email || null,
            success: false,
            passive: true,
            error: e.message,
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

      // ★ Persist identity — survive service worker restarts.
      // On next onWsConnected(), extension will read this and self-register.
      chrome.storage.local.set({ __veo_identity: email });

      const serverProfilePath = msg.profilePath || '';
      // NOTE: MV3 extensions cannot access the browser's user-data-dir,
      // so client-side profile verification is not possible. The profilePath
      // is logged for server-side diagnostics only.
      console.log(`[VEO Bridge] 📧 Server assigned email: ${email} (profilePath=${serverProfilePath || 'none'})`);

      // First: check if ANY tab already has this email assigned
      let existingTabId = findTabForEmail(email);
      if (existingTabId) {
        console.log(`[VEO Bridge] Email ${email} already assigned to tab ${existingTabId}`);
        wsSend({ action: 'register', email, tabId: existingTabId, version: EXT_VERSION, source: 'assign_email' });
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
        wsSend({ action: 'register', email, tabId, version: EXT_VERSION, source: 'assign_email' });
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
          wsSend({ action: 'register', email, tabId: newTab.id, version: EXT_VERSION, source: 'assign_email' });
          try { chrome.tabs.update(newTab.id, { autoDiscardable: false }); } catch (_) { }
          startZombieTimer(newTab.id);
        }
      }
      break;
    }

    case 'check_identity': {
      // ★ Corrective: App injected __veo_identity via CDP, now triggers re-read.
      // Extension re-reads storage and re-registers with the correct email.
      // This fixes wrong bindings from earlier assign_email guesses.
      try {
        const stored = await chrome.storage.local.get('__veo_identity');
        const identityEmail = stored.__veo_identity;
        if (identityEmail) {
          console.log(`[VEO Bridge] 🔐 check_identity: re-registering as ${identityEmail}`);
          const tabId = findTabForEmail(identityEmail);
          wsSend({
            action: 'register',
            email: identityEmail,
            tabId: tabId || null,
            version: EXT_VERSION,
            source: 'identity_refresh',
          });
        } else {
          console.debug('[VEO Bridge] check_identity: no __veo_identity in storage');
        }
      } catch (e) {
        console.debug('[VEO Bridge] check_identity failed:', e.message);
      }
      break;
    }

    case 'check_recaptcha_ready': {
      // Layer 1: Deep readiness check — trial-execute a real token.
      // A simple `typeof execute === 'function'` check is NOT sufficient:
      // it returns true before the widget is fully initialized, causing
      // 330-538 char garbage tokens. Instead, we actually call execute() and
      // check that the returned token is ≥ 1500 chars (HAR: valid = 1742-2169).
      // The valid token is sent back for caching (not wasted).
      let tabId = findTabForEmail(msg.email);
      if (!tabId) {
        // ★ Stale Tab Recovery
        tabId = await recoverStaleTab(msg.email);
      }
      if (!tabId) {
        wsSend({
          action: 'recaptcha_ready',
          requestId: msg.requestId,
          ready: false,
          details: { error: `No tab found for ${msg.email}` },
        });
        return;
      }

      const flowReady = await ensureTabOnFlow(tabId, 'check_recaptcha_ready');
      if (!flowReady.success) {
        wsSend({
          action: 'recaptcha_ready',
          requestId: msg.requestId,
          ready: false,
          details: { error: flowReady.error || 'Flow page unavailable' },
        });
        return;
      }
      tabId = flowReady.tabId;

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
      let tabId = findTabForEmail(msg.email);
      if (!tabId) {
        // ★ Stale Tab Recovery
        tabId = await recoverStaleTab(msg.email);
      }
      if (!tabId) {
        wsSend({
          action: 'submit_prompt_result',
          requestId: msg.requestId,
          success: false,
          error: `No tab found for ${msg.email}`,
        });
        return;
      }

      const flowReady = await ensureTabOnFlow(tabId, 'submit_prompt');
      if (!flowReady.success) {
        wsSend({
          action: 'submit_prompt_result',
          requestId: msg.requestId,
          success: false,
          error: flowReady.error || 'Flow page unavailable',
        });
        return;
      }
      tabId = flowReady.tabId;

      // ── MV3 Keepalive ──────────────────────────────────────────────────
      // Call extension API every 25s to reset Chrome's 30s inactivity timer.
      // This prevents service worker termination during long operations
      // (reCAPTCHA ≤10s + fetch ≤20s = up to 30s total).
      const keepaliveTimer = setInterval(() => {
        chrome.runtime.getPlatformInfo(() => { });
      }, 25000);

      // ── Pre-flight Tab Health Check ──────────────────────────────────
      // Verify tab DOM is alive before wasting reCAPTCHA + fetch attempt.
      // Chrome Memory Saver can discard tabs while they're still in tabState.
      // "Could not extract reCAPTCHA site key" = dead DOM → detect early.
      try {
        const tabInfo = await chrome.tabs.get(tabId);
        const isVeoPage = isFlowUrl(tabInfo.url || '');

        if (tabInfo.discarded || tabInfo.status === 'unloaded') {
          console.warn(
            `[VEO Bridge] ⚠️ Pre-flight: tab ${tabId} discarded/unloaded ` +
            `— reloading before submit`
          );
          // C8: safeTabReload() owns RELOADING
          await safeTabReload(tabId, 'submit-preflight-discarded');
          await new Promise(r => setTimeout(r, 15000)); // VEO needs 13-15s
        } else if (!isVeoPage) {
          console.warn(
            `[VEO Bridge] ⚠️ Pre-flight: tab ${tabId} not on VEO page ` +
            `(url=${tabInfo.url}) — navigating back`
          );
          // C5: NAVIGATING before VEO navigation
          setLifecycle(tabId, TAB_LIFECYCLE.NAVIGATING);
          await chrome.tabs.update(tabId, {
            url: VEO_URL
          });
          await new Promise(r => setTimeout(r, 15000));
        }
      } catch (preFlightErr) {
        console.warn(
          `[VEO Bridge] Pre-flight check failed for tab ${tabId}: ` +
          preFlightErr.message
        );
      }

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
          UPLOAD: 'https://aisandbox-pa.googleapis.com/v1/flow/uploadImage',
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
          func: async (endpointUrl, payload, needsRecaptcha, cachedAccessToken, endpointKey, rcTimeoutMs, fetchTimeoutMs) => {
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

            // ── Step 1.5: Simulate human behavior before reCAPTCHA ─────────
            // reCAPTCHA Enterprise scores based on behavioral signals collected
            // before execute(). Without prior user events, the execution context
            // looks suspicious (no mouse, no scroll, no timing signals).
            // F12 analysis: web has natural interaction before each token request.
            if (needsRecaptcha) {
              try {
                // 1. Mouse events (move → click pattern — realistic coordinates)
                const randomX = Math.floor(Math.random() * window.innerWidth * 0.6 + window.innerWidth * 0.2);
                const randomY = Math.floor(Math.random() * window.innerHeight * 0.6 + window.innerHeight * 0.2);
                ['mousemove', 'mouseover', 'mousedown', 'mouseup', 'click'].forEach(type => {
                  document.dispatchEvent(new MouseEvent(type, {
                    bubbles: true, clientX: randomX, clientY: randomY,
                    view: window, detail: type === 'click' ? 1 : 0,
                  }));
                });
                // 2. Small random scroll (mimics reading behavior)
                window.scrollBy(0, Math.floor(Math.random() * 50) - 25);
                // 3. Focus signals (tab attention)
                document.dispatchEvent(new Event('focus'));
                window.dispatchEvent(new Event('focus'));
                // 4. Natural human delay (200-600ms reaction time)
                await new Promise(r => setTimeout(r, 200 + Math.floor(Math.random() * 400)));
              } catch (_simErr) {
                // Non-fatal — proceed even if simulation fails
              }
            }

            // ── Step 2: Generate reCAPTCHA token ───────
            // ★ rcTimeoutMs comes from function parameter (progressive tier from Python)
            // HAR verified: T2I/UPSCALE_IMAGE use IMAGE_GENERATION, video endpoints use VIDEO_GENERATION
            const imageEndpoints = ['T2I', 'UPSCALE_IMAGE'];
            const rcAction = needsRecaptcha ? (imageEndpoints.includes(endpointKey) ? 'IMAGE_GENERATION' : 'VIDEO_GENERATION') : null;
            let recaptchaToken = null;
            if (needsRecaptcha) {
              try {
                const rcPromise = grecaptcha.enterprise.execute(siteKey, { action: rcAction });
                const rcTimeout_ = new Promise((_, reject) =>
                  setTimeout(() => reject(new Error(`reCAPTCHA execute timeout (${rcTimeoutMs / 1000}s)`)), rcTimeoutMs)
                );
                recaptchaToken = await Promise.race([rcPromise, rcTimeout_]);
                // HAR verified: valid tokens are 1742-2169 chars
                // A 538-char token passed old threshold (500) but was rejected by Google
                if (!recaptchaToken || recaptchaToken.length < 1500) {
                  return {
                    success: false,
                    error: `reCAPTCHA token too short (${recaptchaToken ? recaptchaToken.length : 0} chars, need ≥1500)`,
                    tokenLength: recaptchaToken ? recaptchaToken.length : 0,
                  };
                }
              } catch (err) {
                return { success: false, error: `reCAPTCHA execute failed: ${err.message}` };
              }
            }

            // ── Step 3: Build request body with per-request tokens ────────
            // F12 analysis: web generates a FRESH reCAPTCHA token per image
            // request (reload → submit → clr → reload → submit → clr...).
            // Match this pattern: first request uses initial token, subsequent
            // requests get fresh tokens with small delays between them.
            const body = payload.body || {};
            if (needsRecaptcha && recaptchaToken) {
              // Top-level clientContext gets first token
              if (!body.clientContext) body.clientContext = {};
              body.clientContext.recaptchaContext = {
                token: recaptchaToken,
                applicationType: 'RECAPTCHA_APPLICATION_TYPE_WEB',
              };
              // Per-request clientContext: each gets its own fresh token
              if (Array.isArray(body.requests)) {
                for (let i = 0; i < body.requests.length; i++) {
                  const req = body.requests[i];
                  let itemToken = recaptchaToken; // First uses initial token
                  if (i > 0 && req.clientContext) {
                    // Generate fresh token for subsequent requests (match web pattern)
                    try {
                      // Small delay between requests — web has reload/clr cycle (~300-500ms)
                      await new Promise(r => setTimeout(r, 300 + Math.floor(Math.random() * 200)));
                      itemToken = await grecaptcha.enterprise.execute(siteKey, { action: rcAction });
                      if (!itemToken || itemToken.length < 1500) {
                        itemToken = recaptchaToken; // Fallback to first token
                      }
                    } catch (_freshErr) {
                      itemToken = recaptchaToken; // Fallback to first token on error
                    }
                  }
                  if (req.clientContext) {
                    req.clientContext.recaptchaContext = {
                      token: itemToken,
                      applicationType: 'RECAPTCHA_APPLICATION_TYPE_WEB',
                    };
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

            // ── Step 4.5: Request Storage Access (if needed) ──────────────
            if (document.requestStorageAccess) {
              try {
                await document.requestStorageAccess();
              } catch (e) { /* non-fatal */ }
            }

            // ── Step 5: Send API request (with 20s AbortController) ──────
            const headers = { 'Content-Type': 'text/plain;charset=UTF-8' };
            if (authHeaderValue) {
              headers['Authorization'] = authHeaderValue;
            }

            const controller = new AbortController();
            // ★ Progressive timeout: T2I/I2I/UPSCALE_IMAGE synchronous → min 90s, others use dynamic fetchTimeoutMs
            const fetchTimeout = ['T2I', 'I2I', 'UPSCALE_IMAGE'].includes(endpointKey)
              ? Math.max(fetchTimeoutMs || 20000, 90000) : (fetchTimeoutMs || 20000);
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

              // Let the page's official reCAPTCHA runtime own reload/clr traffic.
              // A synthetic no-cors clr POST from the extension adds malformed
              // post-submit traffic and can degrade the profile's risk signals.

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
            msg.rcTimeout || 15000,   // ★ Dynamic reCAPTCHA timeout from Python tier
            msg.fetchTimeout || 20000, // ★ Dynamic fetch timeout from Python tier
          ],
        });

        // T2I/I2I: synchronous response (up to ~90s), video: async (quick)
        const scriptTimeout = ['T2I', 'I2I', 'UPSCALE_IMAGE'].includes(msg.endpoint) ? 120000 : 30000;
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
          if (dataStr.length > 50000 && msg.endpoint !== 'UPSCALE_IMAGE') { // >50KB = likely contains video data (skip trim for UPSCALE_IMAGE — encodedImage IS the result)
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

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // relay_fetch — GENERIC FETCH FROM PAGE CONTEXT
    //
    // Allows Python to make arbitrary HTTP requests from the VEO tab's
    // browser context. Cookies are auto-attached (same-origin for labs.google).
    // Used for: TRPC project creation/listing, checkAppAvailability, etc.
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    case 'relay_fetch': {
      let tabId = findTabForEmail(msg.email);
      if (!tabId && msg.email) {
        const ensured = await ensureFlowForEmail(msg.email, 'relay_fetch');
        if (ensured.success) tabId = ensured.tabId;
      }
      if (!tabId) {
        wsSend({
          action: 'relay_fetch_result',
          requestId: msg.requestId,
          success: false,
          error: `No tab found for ${msg.email}`,
        });
        return;
      }

      try {
        console.log(
          `[VEO Bridge] 🔄 relay_fetch for ${msg.email} → ${msg.method || 'POST'} ` +
          `${(msg.url || '').substring(0, 100)} (tab ${tabId})`
        );

        // Domain check: TRPC endpoints require tab on labs.google domain
        // (same-origin cookies). If tab is on myaccount.google.com or other
        // domain, navigate to VEO flow page first.
        const requestUrl = msg.url || '';
        if (requestUrl.includes('labs.google')) {
          const flowReady = await ensureTabOnFlow(tabId, 'relay_fetch');
          if (!flowReady.success) {
            wsSend({
              action: 'relay_fetch_result',
              requestId: msg.requestId,
              success: false,
              error: flowReady.error || 'Flow page unavailable',
            });
            return;
          }
          tabId = flowReady.tabId;
          console.log(`[VEO Bridge] ✅ relay_fetch Flow guard passed — proceeding with fetch`);
        }

        const scriptResult = await chrome.scripting.executeScript({
          target: { tabId },
          world: 'MAIN',
          func: async (url, method, body, headers, credentials) => {
            try {
              const controller = new AbortController();
              const timeoutId = setTimeout(() => controller.abort(), 15000);

              const fetchOpts = {
                method: method || 'POST',
                signal: controller.signal,
              };

              // Add credentials if specified
              if (credentials) fetchOpts.credentials = credentials;

              // Add headers
              if (headers && Object.keys(headers).length > 0) {
                fetchOpts.headers = headers;
              } else {
                fetchOpts.headers = { 'Content-Type': 'application/json' };
              }

              // Add body for non-GET methods
              if (body && method !== 'GET') {
                fetchOpts.body = JSON.stringify(body);
              }

              const resp = await fetch(url, fetchOpts);
              clearTimeout(timeoutId);

              let data = null;
              const contentType = resp.headers.get('content-type') || '';
              if (contentType.includes('json')) {
                data = await resp.json().catch(() => null);
              } else {
                const text = await resp.text().catch(() => '');
                try { data = JSON.parse(text); } catch { data = { text }; }
              }

              return {
                success: resp.ok,
                status: resp.status,
                statusText: resp.statusText,
                data,
              };
            } catch (e) {
              return {
                success: false,
                status: 0,
                error: e.message || String(e),
              };
            }
          },
          args: [
            msg.url,
            msg.method || 'POST',
            msg.body || null,
            msg.headers || {},
            msg.credentials || 'include',
          ],
        });

        const result = scriptResult?.[0]?.result || {
          success: false,
          error: 'executeScript returned no result',
        };

        console.log(
          `[VEO Bridge] ${result.success ? '✅' : '❌'} relay_fetch result: ` +
          `status=${result.status} for ${msg.email}`
        );

        wsSend({
          action: 'relay_fetch_result',
          requestId: msg.requestId,
          ...result,
        });
      } catch (e) {
        console.error(`[VEO Bridge] ❌ relay_fetch failed for ${msg.email}: ${e.message}`);
        wsSend({
          action: 'relay_fetch_result',
          requestId: msg.requestId,
          success: false,
          error: e.message,
        });
      }
      break;
    }

    case 'navigate_tab': {
      // Navigate VEO tab to a specific URL (e.g. project page)
      // Uses chrome.tabs.update — cleaner than window.location.href
      let tabId = findTabForEmail(msg.email);
      if (!tabId) {
        const ensured = await ensureVeoTabForEmail(msg.email, msg.url || VEO_URL);
        if (ensured.success) tabId = ensured.tabId;
      }
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

        // C5: Set NAVIGATING or SUSPENDED based on target scope
        const isVeoScope = targetUrl.includes('labs.google');
        setLifecycle(tabId, isVeoScope
          ? TAB_LIFECYCLE.NAVIGATING
          : TAB_LIFECYCLE.SUSPENDED);

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
          // Fix #2: Navigation timeout — log warning + continue (don't hang)
          console.warn(`[VEO Bridge] ⚠️ Navigation timeout after ${loadTime}s (max 25s): ${targetUrl} — proceeding without full load`);
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

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // reload_tab: Reload VEO tab for soft recovery (extension-only accounts)
    // Used when soft_recover_browser() fails (no Playwright page).
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    case 'reload_tab': {
      const tabId = findTabForEmail(msg.email);
      if (!tabId) {
        wsSend({
          action: 'reload_tab_result',
          requestId: msg.requestId,
          success: false,
          error: `No tab found for ${msg.email}`,
        });
        return;
      }

      try {
        console.log(`[VEO Bridge] 🔄 Reloading tab ${tabId} for ${msg.email} (soft recovery)`);
        // C8: safeTabReload() owns RELOADING
        await safeTabReload(tabId, 'reload-tab-soft-recovery');

        // Wait for tab to finish loading (up to 15s)
        await new Promise((resolve) => {
          const onUpdated = (updatedTabId, changeInfo) => {
            if (updatedTabId === tabId && changeInfo.status === 'complete') {
              chrome.tabs.onUpdated.removeListener(onUpdated);
              resolve();
            }
          };
          chrome.tabs.onUpdated.addListener(onUpdated);
          setTimeout(() => {
            chrome.tabs.onUpdated.removeListener(onUpdated);
            resolve();
          }, 15000);
        });

        console.log(`[VEO Bridge] ✅ Tab ${tabId} reloaded successfully`);
        wsSend({
          action: 'reload_tab_result',
          requestId: msg.requestId,
          success: true,
        });
      } catch (e) {
        console.warn(`[VEO Bridge] ❌ Tab reload failed: ${e.message}`);
        wsSend({
          action: 'reload_tab_result',
          requestId: msg.requestId,
          success: false,
          error: e.message,
        });
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
      // Passive probe only: report headers captured from real Flow traffic.
      // Do not create synthetic googleapis requests from the page context.
      let tabId = findTabForEmail(msg.email);
      if (!tabId && msg.email) {
        const ensured = await ensureFlowForEmail(msg.email, 'probe_browser_headers');
        if (ensured.success) tabId = ensured.tabId;
      }
      if (!tabId) {
        wsSend({
          action: 'probe_browser_headers_result',
          requestId: msg.requestId || null,
          success: false,
          error: `No tab found for ${msg.email}`,
        });
        break;
      }

      const flowReady = await ensureTabOnFlow(tabId, 'probe_browser_headers');
      if (!flowReady.success) {
        wsSend({
          action: 'probe_browser_headers_result',
          requestId: msg.requestId || null,
          success: false,
          error: flowReady.error || 'Flow page unavailable',
        });
        break;
      }
      tabId = flowReady.tabId;

      // C8: Layer 1 — Check lifecycle before running probe
      try {
        const tab = await chrome.tabs.get(tabId);
        const lifecycle = tabState[tabId]?._lifecycle;
        if (tab.status !== 'complete' ||
          !isFlowUrl(tab.url || '') ||
          lifecycle === TAB_LIFECYCLE.RELOADING ||
          lifecycle === TAB_LIFECYCLE.NAVIGATING) {
          wsSend({
            action: 'probe_browser_headers_result',
            requestId: msg.requestId || null,
            success: false, error: 'tab_transitioning',
          });
          break;
        }
      } catch (e) { /* tab gone */ break; }

      try {
        console.log(`[VEO Bridge] 🔍 Passive browser-header probe for tab ${tabId} (${msg.email})`);

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
          probeResult: { passive: true },
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
        // C8: Layer 2 — Classify transient frame errors vs real errors
        const isTransient = e.message?.includes('Frame with ID') ||
          e.message?.includes('No frame with id') ||
          e.message?.includes('Cannot access') ||
          e.message?.includes('No tab with id');
        console.error(`[VEO Bridge] Probe failed: ${e.message}${isTransient ? ' (transient)' : ''}`);
        wsSend({
          action: 'probe_browser_headers_result',
          requestId: msg.requestId || null,
          success: false,
          error: isTransient ? 'tab_transitioning' : e.message,
          transient: isTransient,
        });
      }
      break;
    }

    case 'provision_gemini_key': {
      // Auto-provision Gemini API key via AI Studio's gRPC-web service.
      // 2-Phase approach:
      //   Phase 1: Use chrome.cookies.get for SAPISID → run on VEO tab (no navigate)
      //   Phase 2: Only if no GCP project → navigate to AI Studio for SNlM0e token
      const requestId = msg.requestId;
      const email = msg.email;
      const RPC_BASE = 'https://alkalimakersuite-pa.clients6.google.com/$rpc/google.internal.alkali.applications.makersuite.v1.MakerSuiteService';
      const STATIC_KEY = 'AIzaSyDdP816MREB3SkjZO04QXbjsigfcI0GWOs';

      const tabId = findTabForEmail(email) || Object.keys(tabState).find(tid => tabState[tid].email);

      if (!tabId) {
        wsSend({
          action: 'provision_gemini_key_result',
          requestId, email, success: false,
          error: 'No tab available for Gemini key provisioning',
        });
        break;
      }

      try {
        console.log(`[VEO Bridge] 🔑 Provisioning Gemini key for ${email} via tab ${tabId}...`);

        // ── Read SAPISID via chrome.cookies API (no navigation needed!) ──
        const sapisidCookie = await chrome.cookies.get({
          url: 'https://aistudio.google.com',
          name: 'SAPISID',
        });
        const sapisid = sapisidCookie?.value;
        if (!sapisid) {
          wsSend({
            action: 'provision_gemini_key_result',
            requestId, email, success: false,
            error: 'no_sapisid', msg: 'SAPISID cookie not found — user may not be logged in',
          });
          break;
        }
        console.log(`[VEO Bridge] 🍪 SAPISID obtained via chrome.cookies API (no navigation)`);

        // ── Phase 1: Run gRPC-web on current tab (no navigate) ──
        // Pass SAPISID as argument instead of reading document.cookie
        const phase1Fn = async (RPC, KEY, sapisidValue) => {
          // Build SAPISIDHASH from passed SAPISID value
          async function buildSapisidHash(sapisid) {
            try {
              const ORIGIN = "https://aistudio.google.com";
              const ts = Math.floor(Date.now() / 1000);
              const input = `${ts} ${sapisid} ${ORIGIN}`;
              const buf = await crypto.subtle.digest("SHA-1",
                new TextEncoder().encode(input));
              const hex = [...new Uint8Array(buf)]
                .map(b => b.toString(16).padStart(2, '0')).join('');
              const hash = `${ts}_${hex}`;
              return `SAPISIDHASH ${hash} SAPISID1PHASH ${hash} SAPISID3PHASH ${hash}`;
            } catch (e) { return null; }
          }

          const authHeader = await buildSapisidHash(sapisidValue);
          const H = {
            "Content-Type": "application/json+protobuf",
            "x-goog-api-key": KEY,
            "x-goog-authuser": "0",
            "x-user-agent": "grpc-web-javascript/0.1",
            "x-goog-ext-519733851-bin": "CAESAUwwATgEQAA="
          };
          if (authHeader) H["authorization"] = authHeader;

          try {
            // Step 1: List Cloud Projects
            let r = await fetch(RPC + "/ListCloudProjects", {
              method: "POST", credentials: "include", headers: H,
              body: JSON.stringify([null, null, null, 1, null, null])
            });
            if (!r.ok) return { error: "list_projects_http_" + r.status };
            let projects = await r.json();

            let projectRef = null;
            let projectId = null;
            if (projects && Array.isArray(projects)) {
              const flat = JSON.stringify(projects);
              const m = flat.match(/projects\/(\d+)/);
              if (m) projectRef = "projects/" + m[1];
              const m2 = flat.match(/gen-lang-client-[\w-]+/);
              if (m2) projectId = m2[0];
            }

            if (!projectRef) {
              // No project found — Phase 2 needed (navigate for token)
              return { error: "no_project", needs_navigate: true };
            }

            // Step 2: List existing API Keys
            r = await fetch(RPC + "/ListCloudApiKeys", {
              method: "POST", credentials: "include", headers: H,
              body: JSON.stringify([100, null, 1, [projectRef]])
            });
            if (!r.ok) return { error: "list_keys_http_" + r.status };
            let keys = await r.json();
            const keysFlat = JSON.stringify(keys);
            const km = keysFlat.match(/AIza[\w-]{35}/);
            if (km) return { key: km[0], source: "existing" };

            // Step 3: Generate new API Key (no token needed for this!)
            // GenerateCloudApiKey only needs projectId, not SNlM0e token
            if (!projectId) return { error: "no_project_id" };
            r = await fetch(RPC + "/GenerateCloudApiKey", {
              method: "POST", credentials: "include", headers: H,
              body: JSON.stringify([projectId, null, null, "GEMINI API AUTO"])
            });
            if (!r.ok) return { error: "gen_key_http_" + r.status };
            let newKey = await r.json();
            const nkm = JSON.stringify(newKey).match(/AIza[\w-]{35}/);
            if (nkm) return { key: nkm[0], source: "created" };

            // If GenerateCloudApiKey without token fails, try with null token
            return { error: "create_failed", needs_navigate: true };
          } catch (e) {
            return { error: e.message };
          }
        };

        // Execute Phase 1 on current VEO tab (no navigation!)
        // Fix #3: Timeout guard for gRPC fetch calls (30s)
        const phase1Script = chrome.scripting.executeScript({
          target: { tabId: parseInt(tabId) },
          world: 'MAIN',
          func: phase1Fn,
          args: [RPC_BASE, STATIC_KEY, sapisid],
        });
        const phase1Timeout = new Promise((_, reject) =>
          setTimeout(() => reject(new Error('Gemini provision Phase 1 timeout (30s)')), 30000)
        );
        const phase1Results = await Promise.race([phase1Script, phase1Timeout]);

        let result = phase1Results?.[0]?.result;

        // ── Phase 2: Navigate to AI Studio ONLY if no project ──
        if (result?.needs_navigate) {
          console.log(`[VEO Bridge] 🔑 Phase 2: Account has no GCP project — navigating to AI Studio for token...`);

          const origUrl = (await chrome.tabs.get(parseInt(tabId))).url;

          // Navigate to AI Studio to get SNlM0e token from DOM
          // C5: SUSPENDED — AI Studio is outside VEO scope
          setLifecycle(tabId, TAB_LIFECYCLE.SUSPENDED);
          await chrome.tabs.update(parseInt(tabId), { url: 'https://aistudio.google.com/api-keys' });
          await new Promise(r => setTimeout(r, 6000)); // Wait for SPA to load

          // Phase 2: Full provision with token extraction (on AI Studio page)
          const phase2Fn = async (RPC, KEY, sapisidValue) => {
            async function buildSapisidHash(sapisid) {
              try {
                const ORIGIN = "https://aistudio.google.com";
                const ts = Math.floor(Date.now() / 1000);
                const input = `${ts} ${sapisid} ${ORIGIN}`;
                const buf = await crypto.subtle.digest("SHA-1",
                  new TextEncoder().encode(input));
                const hex = [...new Uint8Array(buf)]
                  .map(b => b.toString(16).padStart(2, '0')).join('');
                const hash = `${ts}_${hex}`;
                return `SAPISIDHASH ${hash} SAPISID1PHASH ${hash} SAPISID3PHASH ${hash}`;
              } catch (e) { return null; }
            }

            // Token extraction (only works on AI Studio page)
            function extractToken() {
              try {
                if (typeof WIZ_global_data !== 'undefined' && WIZ_global_data.SNlM0e) return WIZ_global_data.SNlM0e;
              } catch (e) { }
              try {
                if (window.__WIZ_global_data__ && window.__WIZ_global_data__.SNlM0e) return window.__WIZ_global_data__.SNlM0e;
              } catch (e) { }
              try {
                const scripts = document.querySelectorAll('script');
                for (const s of scripts) {
                  const txt = s.textContent || '';
                  if (txt.length < 50) continue;
                  let tm = txt.match(/SNlM0e['"]\s*[:,=]\s*['"](![^'"]{20,})['"]/);
                  if (tm) return tm[1];
                  tm = txt.match(/"(![A-Za-z0-9_\-]{20,})"/);
                  if (tm) return tm[1];
                }
              } catch (e) { }
              return null;
            }

            const authHeader = await buildSapisidHash(sapisidValue);
            const H = {
              "Content-Type": "application/json+protobuf",
              "x-goog-api-key": KEY,
              "x-goog-authuser": "0",
              "x-user-agent": "grpc-web-javascript/0.1",
              "x-goog-ext-519733851-bin": "CAESAUwwATgEQAA="
            };
            if (authHeader) H["authorization"] = authHeader;

            try {
              const token = extractToken();
              if (!token) return { error: "no_token", msg: "Cannot extract SNlM0e token from AI Studio" };

              // Create project
              let r = await fetch(RPC + "/CreateCloudProject", {
                method: "POST", credentials: "include", headers: H,
                body: JSON.stringify([token, "GEMINI API FOR AUTO FLOW"])
              });
              if (!r.ok) return { error: "create_project_http_" + r.status };
              let newProj = await r.json();
              const npFlat = JSON.stringify(newProj);
              let projectRef = null, projectId = null;
              const npm = npFlat.match(/projects\/(\d+)/);
              if (npm) projectRef = "projects/" + npm[1];
              const npm2 = npFlat.match(/gen-lang-client-[\w-]+/);
              if (npm2) projectId = npm2[0];
              if (!projectRef) return { error: "create_project_failed" };

              // List keys for new project
              r = await fetch(RPC + "/ListCloudApiKeys", {
                method: "POST", credentials: "include", headers: H,
                body: JSON.stringify([100, null, 1, [projectRef]])
              });
              if (r.ok) {
                let keys = await r.json();
                const km = JSON.stringify(keys).match(/AIza[\w-]{35}/);
                if (km) return { key: km[0], source: "existing" };
              }

              // Generate new key
              if (!projectId) return { error: "no_project_id" };
              r = await fetch(RPC + "/GenerateCloudApiKey", {
                method: "POST", credentials: "include", headers: H,
                body: JSON.stringify([projectId, token, null, "GEMINI API FOR AUTO FLOW"])
              });
              if (!r.ok) return { error: "gen_key_http_" + r.status };
              let newKey = await r.json();
              const nkm = JSON.stringify(newKey).match(/AIza[\w-]{35}/);
              if (nkm) return { key: nkm[0], source: "created" };
              return { error: "create_failed" };
            } catch (e) {
              return { error: e.message };
            }
          };

          // Fix #3: Timeout guard for Phase 2 gRPC calls (30s)
          const phase2Script = chrome.scripting.executeScript({
            target: { tabId: parseInt(tabId) },
            world: 'MAIN',
            func: phase2Fn,
            args: [RPC_BASE, STATIC_KEY, sapisid],
          });
          const phase2Timeout = new Promise((_, reject) =>
            setTimeout(() => reject(new Error('Gemini provision Phase 2 timeout (30s)')), 30000)
          );
          const phase2Results = await Promise.race([phase2Script, phase2Timeout]);

          result = phase2Results?.[0]?.result;

          // Navigate back to VEO
          setTimeout(() => {
            // C5: NAVIGATING — returning to VEO scope
            setLifecycle(tabId, TAB_LIFECYCLE.NAVIGATING);
            chrome.tabs.update(parseInt(tabId), { url: origUrl || VEO_URL });
          }, 1000);
        }

        // ── Send result ──
        if (result?.key) {
          console.log(`[VEO Bridge] 🔑 Gemini key ${result.source} for ${email}: ${result.key.substring(0, 10)}...`);
          wsSend({
            action: 'provision_gemini_key_result',
            requestId, email, success: true,
            key: result.key, source: result.source,
          });
        } else {
          console.warn(`[VEO Bridge] ❌ Gemini key provision failed for ${email}:`, result);
          wsSend({
            action: 'provision_gemini_key_result',
            requestId, email, success: false,
            error: result?.error || 'unknown', msg: result?.msg || '',
          });
        }
      } catch (e) {
        console.error(`[VEO Bridge] Gemini key provision error: ${e.message}`);
        wsSend({
          action: 'provision_gemini_key_result',
          requestId, email, success: false,
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

    // C6: Reset lifecycle on header capture (liveness signal)
    // Only if tab is on VEO scope — SUSPENDED tabs must NOT be unsuspended
    if (state._lifecycle &&
      state._lifecycle !== TAB_LIFECYCLE.ALIVE &&
      state._lifecycle !== TAB_LIFECYCLE.SUSPENDED &&
      Object.keys(headers).length > 0) {
      // Async URL check (onBeforeSendHeaders is synchronous)
      setTimeout(async () => {
        try {
          const currentTab = await chrome.tabs.get(details.tabId);
          if (currentTab.url && currentTab.url.includes('labs.google')) {
            console.log(`[VEO Bridge] ✅ Tab ${details.tabId} alive — headers captured`);
            setLifecycle(details.tabId, TAB_LIFECYCLE.ALIVE, {
              _recoveryAttempts: 0, _deadNotified: false,
            });
          }
        } catch (_) { /* tab gone */ }
      }, 0);
    }

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


// ── Offscreen Document Message Relay ───────────────────────────────────
// Handle messages FROM offscreen.js (WebSocket state + incoming WS messages)
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'offscreen_pref_port_get') {
    (async () => {
      try {
        const stored = await chrome.storage.local.get(LAST_GOOD_PORT_KEY);
        sendResponse({ ok: true, port: Number(stored?.[LAST_GOOD_PORT_KEY]) || null });
      } catch (e) {
        sendResponse({ ok: false, port: null, error: e.message || 'storage_get_failed' });
      }
    })();
    return true;
  }

  if (msg.type === 'offscreen_pref_port_set') {
    (async () => {
      try {
        const port = Number(msg.port);
        if (!Number.isFinite(port)) {
          sendResponse({ ok: false, error: 'invalid_port' });
          return;
        }
        await chrome.storage.local.set({ [LAST_GOOD_PORT_KEY]: port });
        sendResponse({ ok: true });
      } catch (e) {
        sendResponse({ ok: false, error: e.message || 'storage_set_failed' });
      }
    })();
    return true;
  }

  // ── Offscreen: WS state change ──
  if (msg.type === 'offscreen_ws_state') {
    const wasConnected = wsConnected;
    wsConnected = msg.connected;
    if (msg.port) {
      _bridgeDebug.offscreen = {
        ...(_bridgeDebug.offscreen || {}),
        currentPort: msg.port,
        connected: msg.connected,
      };
    }
    if (msg.connected && !wasConnected) {
      _bridgeDebug.lastWsConnectedAt = Date.now();
      onWsConnected();
    } else if (!msg.connected && wasConnected) {
      _bridgeDebug.lastWsDisconnectedAt = Date.now();
      console.log('[VEO Bridge] ⚠️ WebSocket disconnected (offscreen)');
    }
    sendResponse({ ok: true });
    return false;
  }

  if (msg.type === 'offscreen_ws_debug') {
    _bridgeDebug.lastOffscreenEvent = msg.event || 'debug';
    if (msg.debug) {
      _bridgeDebug.offscreen = msg.debug;
    }
    sendResponse({ ok: true });
    return false;
  }

  // ── Offscreen: incoming WS message ──
  if (msg.type === 'offscreen_ws_incoming') {
    handleAppMessage(msg.data).catch(e => {
      console.error('[VEO Bridge] Async handler error:', e.message || e);
    });
    sendResponse({ ok: true });
    return false;
  }

  // ── Below: existing Tab/Content message handling ──
  return undefined; // Fall through to other handlers
});


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
    // C12: Increment register generation for fresh-detection tracking
    tabState[tabId]._registerGeneration = (tabState[tabId]._registerGeneration || 0) + 1;
    _bridgeDebug.lastTabRegisterAt = Date.now();
    _bridgeDebug.lastTabRegisterEmail = msg.email;
    // C6: Reset lifecycle — register_tab proves tab is alive
    setLifecycle(tabId, TAB_LIFECYCLE.ALIVE, {
      _recoveryAttempts: 0, _deadNotified: false,
    });
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

    // Notify app and push any already-captured headers immediately.
    pushTabSnapshotToApp(tabId, 'register_tab', true);

    // Fresh tab registration is the strongest signal that the bridge should
    // be alive right now. Recover eagerly instead of waiting for the watchdog.
    if (!wsConnected) {
      ensureBridgeReady(`register_tab:${msg.email}`).catch(() => { });
    }

    sendResponse({ ok: true });
  }


  // ── Content Heartbeat ──
  if (msg.action === 'content_heartbeat' && sender.tab) {
    const tabId = sender.tab.id;
    // C11: Auto-create placeholder if tabState doesn't exist yet
    if (!tabState[tabId]) {
      tabState[tabId] = {
        email: msg.email || null,
        headers: {},
        accessToken: null,
        lastHeartbeat: 0,
        recaptchaReady: false,
      };
      console.log(`[VEO Bridge] 📝 Created placeholder tabState for ${tabId} (early heartbeat)`);
    }
    const state = tabState[tabId];
    state.lastHeartbeat = Date.now();
    // Update email if provided and not yet set
    if (msg.email && !state.email) {
      state.email = msg.email;
    }
    // C6: Reset lifecycle via helper — tab is alive
    if (state._lifecycle && state._lifecycle !== TAB_LIFECYCLE.ALIVE) {
      console.log(`[VEO Bridge] ✅ Tab ${tabId} recovered — heartbeat`);
    }
    setLifecycle(tabId, TAB_LIFECYCLE.ALIVE, {
      _recoveryAttempts: 0, _deadNotified: false,
    });

    // If the tab is alive but the bridge is not, recover immediately
    if (!wsConnected) {
      ensureBridgeReady(`content_heartbeat:${state.email || tabId}`).catch(() => { });
    } else if (state.email && Object.keys(state.headers || {}).length > 0) {
      pushTabSnapshotToApp(tabId, 'content_heartbeat');
    }

    // Forward heartbeat to Python app for tracking
    wsSend({
      action: 'content_heartbeat',
      email: state.email || msg.email,
      tabId,
      timestamp: msg.timestamp,
      readyState: msg.readyState,
    });
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
            // C6: Reset lifecycle — reCAPTCHA warmth proves tab is alive
            if (mainResult.ready && state._lifecycle && state._lifecycle !== TAB_LIFECYCLE.ALIVE) {
              setLifecycle(tabId, TAB_LIFECYCLE.ALIVE, {
                _recoveryAttempts: 0, _deadNotified: false,
              });
            }
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
    (async () => {
      try {
        sendResponse(await collectBridgeStatus(true));
      } catch (e) {
        sendResponse({
          connected: wsConnected,
          tabs: [],
          debug: {
            offscreenExists: false,
            offscreenCount: 0,
            background: {
              startedAt: _bridgeDebug.bgStartedAt,
              tabStateRestored: _tabStateRestored,
              wsConnected,
              wsQueueDepth: _wsSendQueue.length,
              lastOffscreenSyncError: e.message || 'get_status_failed',
            },
            offscreen: _bridgeDebug.offscreen,
          },
        });
      }
    })();
    return true;
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

    return;
  }

  const orphanedEmail = state.email;
  console.warn(`[VEO Bridge] ❌ Tab ${tabId} (${orphanedEmail}) closed — looking for replacement...`);

  // Clean up closed tab state
  delete tabState[tabId];
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

      // C12a: Record generation BEFORE waiting — detect fresh register_tab
      const genBefore = tabState[newTabId]._registerGeneration || 0;

      // Inject content.js → it will detectAndRegister() with correct email
      try {
        await chrome.scripting.executeScript({
          target: { tabId: newTabId },
          files: ['content.js'],
        });
      } catch (e) {
        console.debug(`[VEO Bridge] Content.js inject on reassign: ${e.message}`);
      }

      // Wait for a NEW register_tab (generation must increment)
      const confirmed = await new Promise(resolve => {
        const timeout = setTimeout(() => resolve(false), 40000);
        const check = setInterval(() => {
          const gen = tabState[newTabId]?._registerGeneration || 0;
          if (gen > genBefore) {
            clearInterval(check);
            clearTimeout(timeout);
            resolve(true);
          }
        }, 2000);
      });

      if (confirmed) {
        const detectedEmail = tabState[newTabId].email;
        if (detectedEmail === orphanedEmail) {
          console.log(`[VEO Bridge] ✅ Reassign verified: tab ${newTabId} = ${orphanedEmail}`);
        } else {
          console.warn(
            `[VEO Bridge] ⚠️ Tab ${newTabId} belongs to ${detectedEmail}, ` +
            `not orphaned ${orphanedEmail} — no forced reassign`
          );
        }
      } else {
        console.warn(
          `[VEO Bridge] ⚠️ Tab ${newTabId} did not register in 40s — ` +
          `${orphanedEmail} has no tab`
        );
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
    // Email required for watchdog monitoring
    if (!state.email) continue;

    const lifecycle = state._lifecycle || TAB_LIFECYCLE.ALIVE;

    // ── DEAD / SUSPENDED: skip entirely ──
    if (lifecycle === TAB_LIFECYCLE.DEAD) continue;
    if (lifecycle === TAB_LIFECYCLE.SUSPENDED) continue;

    // ── NAVIGATING / RELOADING: skip heartbeat check, but timeout at 60s ──
    if (lifecycle === TAB_LIFECYCLE.NAVIGATING ||
      lifecycle === TAB_LIFECYCLE.RELOADING) {
      if (now - (state._lifecycleAt || 0) > 60000) {
        setLifecycle(tabId, TAB_LIFECYCLE.ALIVE, {
          _recoveryAttempts: (state._recoveryAttempts || 0) + 1,
        });
        console.warn(
          `[VEO Bridge] ⚠️ Tab ${tabId} stuck in ${lifecycle} for >60s — ` +
          `recovery cycle ${state._recoveryAttempts}/${FROZEN_RELOAD_MAX} failed`
        );
      }
      continue;
    }

    // ── RECOVERING: waiting for heartbeat after reload+complete ──
    if (lifecycle === TAB_LIFECYCLE.RECOVERING) {
      if (now - (state._lifecycleAt || 0) > 60000) {
        const attempts = (state._recoveryAttempts || 0) + 1;
        console.warn(
          `[VEO Bridge] ⚠️ Recovery cycle ${attempts}/${FROZEN_RELOAD_MAX} ` +
          `failed for tab ${tabId} (${state.email}) — no heartbeat in 60s settle`
        );
        if (attempts >= FROZEN_RELOAD_MAX) {
          setLifecycle(tabId, TAB_LIFECYCLE.DEAD, {
            _recoveryAttempts: attempts,
            _deadNotified: true,
          });
          console.error(
            `[VEO Bridge] 💀 Tab ${tabId} (${state.email}) DEAD — ` +
            `${FROZEN_RELOAD_MAX} recovery cycles exhausted`
          );
          wsSend({
            action: 'tab_dead', email: state.email,
            tabId: parseInt(tabId), reloadAttempts: attempts,
          });
        } else {
          // Try next cycle — revert to ALIVE so next check triggers reload
          setLifecycle(tabId, TAB_LIFECYCLE.ALIVE, {
            _recoveryAttempts: attempts,
          });
        }
      }
      continue;
    }

    // ── ALIVE: normal heartbeat timeout check ──
    // Only ALIVE tabs need lastHeartbeat to be set
    if (!state.lastHeartbeat) continue;
    const elapsed = now - state.lastHeartbeat;
    if (elapsed <= HEARTBEAT_TIMEOUT) continue;

    // Window reset
    if (!state._frozenWindowStart) {
      state._frozenWindowStart = now;
      persistTabState(); // P2: persist initial window start
    }
    if (now - state._frozenWindowStart > FROZEN_RELOAD_WINDOW) {
      setLifecycle(tabId, TAB_LIFECYCLE.ALIVE, {
        _recoveryAttempts: 0,
        _frozenWindowStart: now, // P2: include in setLifecycle for auto-persist
      });
    }

    // Already exhausted?
    if ((state._recoveryAttempts || 0) >= FROZEN_RELOAD_MAX) {
      if (!state._deadNotified) {
        setLifecycle(tabId, TAB_LIFECYCLE.DEAD, { _deadNotified: true });
        wsSend({
          action: 'tab_dead', email: state.email,
          tabId: parseInt(tabId), reloadAttempts: FROZEN_RELOAD_MAX,
        });
      }
      continue;
    }

    // Notify Python (info only — Python does NOT recover/escalate)
    wsSend({
      action: 'tab_frozen', email: state.email,
      tabId: parseInt(tabId), lastHeartbeat: state.lastHeartbeat,
      elapsedMs: elapsed,
      reloadAttempt: (state._recoveryAttempts || 0) + 1,
    });

    // ★ safeTabReload() owns RELOADING — DO NOT pre-set lifecycle here
    console.warn(
      `[VEO Bridge] ⚠️ Tab ${tabId} (${state.email}) heartbeat miss ` +
      `(${Math.floor(elapsed / 1000)}s) — recovery cycle ` +
      `${(state._recoveryAttempts || 0) + 1}/${FROZEN_RELOAD_MAX}`
    );

    safeTabReload(parseInt(tabId),
      `heartbeat-recovery-${(state._recoveryAttempts || 0) + 1}`
    ).then(result => {
      if (result === RELOAD_RESULT.RELOADED) {
        // safeTabReload() set RELOADING — onUpdated transitions to RECOVERING
      } else if (result === RELOAD_RESULT.SKIPPED_COOLDOWN) {
        // Didn't change state — retry next cycle
      } else {
        // FAILED — safeTabReload() reverted. Count as failed cycle.
        setLifecycle(tabId, TAB_LIFECYCLE.ALIVE, {
          _recoveryAttempts: (state._recoveryAttempts || 0) + 1,
        });
      }
    });
  }
}

// Start heartbeat check every 20s
if (!_heartbeatCheckTimer) {
  _heartbeatCheckTimer = setInterval(checkHeartbeats, 20000);
}

// ── Change 4: Tab lifecycle transition listener ──────────────────────────
// Transitions RELOADING/NAVIGATING → RECOVERING (VEO page) or SUSPENDED (non-VEO)
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status !== 'complete') return;
  const state = tabState[tabId];
  if (!state) return;

  if (state._lifecycle === TAB_LIFECYCLE.RELOADING ||
    state._lifecycle === TAB_LIFECYCLE.NAVIGATING) {
    const isVeoPage = tab.url && tab.url.includes('labs.google');
    if (isVeoPage) {
      setLifecycle(tabId, TAB_LIFECYCLE.RECOVERING);
      console.log(
        `[VEO Bridge] Tab ${tabId} complete — RECOVERING ` +
        `(waiting for heartbeat, 60s settle)`
      );
    } else {
      setLifecycle(tabId, TAB_LIFECYCLE.SUSPENDED);
      console.log(
        `[VEO Bridge] Tab ${tabId} complete on non-VEO page — SUSPENDED`
      );
    }
  }

  // SUSPENDED tab returned to VEO? → start RECOVERING
  if (state._lifecycle === TAB_LIFECYCLE.SUSPENDED) {
    if (tab.url && tab.url.includes('labs.google')) {
      setLifecycle(tabId, TAB_LIFECYCLE.RECOVERING);
      console.log(
        `[VEO Bridge] Tab ${tabId} returned to VEO — RECOVERING`
      );
    }
  }
});


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


/**
 * ★ Stale Tab Recovery: when findTabForEmail() returns null but a Chrome tab
 * with the VEO URL still exists, re-inject content.js and re-register it.
 *
 * Root cause: Chrome can discard tabs (memory saving) or the MV3 service worker
 * can restart, losing tabState entries. The tab is still open in Chrome but
 * invisible to the extension → "No tab found" → engine stalls permanently.
 *
 * Recovery strategy:
 * 1. Query Chrome for all labs.google tabs
 * 2. Find an orphaned tab (not in tabState with an email)
 * 3. If tab was discarded by Chrome, reload it
 * 4. Re-inject content.js to revive the content script
 * 5. Assign the email and re-register with Python
 *
 * Cooldown: 30s between recovery attempts per email to prevent spam.
 *
 * @param {string} email - Account email to recover tab for
 * @returns {number|null} - Recovered tabId or null if recovery failed
 */
const _recoveryCooldown = {};  // email → Date.now() of last attempt
const RECOVERY_COOLDOWN_MS = 30000;  // 30s between attempts

async function recoverStaleTab(email) {
  // Cooldown check
  const now = Date.now();
  const lastAttempt = _recoveryCooldown[email] || 0;
  if (now - lastAttempt < RECOVERY_COOLDOWN_MS) {
    return null;  // Cooldown active
  }
  _recoveryCooldown[email] = now;

  try {
    // 1. Query Chrome for all VEO tabs
    const veoTabs = await chrome.tabs.query({ url: '*://labs.google/*' });
    if (veoTabs.length === 0) {
      console.debug(`[VEO Bridge] 🔍 No VEO tabs found in Chrome for recovery (${email})`);
      return null;
    }

    // 2. Find orphaned tab: exists in Chrome but not in tabState with an email,
    //    OR has a different/null email in tabState
    let targetTab = null;

    // Priority 1: Tab that has this email but lost its tabState
    for (const tab of veoTabs) {
      if (!tabState[tab.id] || !tabState[tab.id].email) {
        targetTab = tab;
        break;
      }
    }

    // Priority 2: ANY VEO tab where tabState.email doesn't match any connected email
    if (!targetTab) {
      const connectedEmails = new Set(
        Object.values(tabState).map(s => s.email).filter(Boolean)
      );
      for (const tab of veoTabs) {
        // If this tab's email is not the one we're looking for,
        // but there's only one VEO tab and it has wrong email → might be ours
        if (veoTabs.length === 1 && !connectedEmails.has(email)) {
          targetTab = tab;
          break;
        }
      }
    }

    if (!targetTab) {
      console.debug(`[VEO Bridge] 🔍 All ${veoTabs.length} VEO tabs already assigned — no orphan for ${email}`);
      return null;
    }

    console.warn(
      `[VEO Bridge] 🔄 Recovering stale tab ${targetTab.id} for ${email} ` +
      `(discarded=${targetTab.discarded || false}, url=${targetTab.url})`
    );

    // 3. If tab was discarded by Chrome, reload it
    if (targetTab.discarded) {
      try {
        // C8: safeTabReload() owns RELOADING
        await safeTabReload(targetTab.id, 'recover-stale-discarded');
        console.log(`[VEO Bridge] 🔄 Reloaded discarded tab ${targetTab.id}`);
        await new Promise(r => setTimeout(r, 15000));
      } catch (e) {
        console.warn(`[VEO Bridge] Failed to reload discarded tab: ${e.message}`);
        return null;
      }
    }

    // 3.5. Verify tab is on correct VEO tool page (not just labs.google/*)
    // Tab may be on labs.google/some-other-tool → no reCAPTCHA widget
    try {
      const updatedTab = await chrome.tabs.get(targetTab.id);
      const isVeoPage = isFlowUrl(updatedTab.url || '');
      if (!isVeoPage) {
        console.warn(
          `[VEO Bridge] 🔄 Tab ${targetTab.id} on wrong page ` +
          `(${updatedTab.url}) — navigating to VEO tool`
        );
        // C5: NAVIGATING before VEO navigation
        setLifecycle(targetTab.id, TAB_LIFECYCLE.NAVIGATING);
        await chrome.tabs.update(targetTab.id, {
          url: VEO_URL
        });
        await new Promise(r => setTimeout(r, 15000)); // Full VEO load
      }
    } catch (urlErr) {
      console.warn(`[VEO Bridge] URL verification failed: ${urlErr.message}`);
    }

    // 4. Create placeholder tabState if needed
    if (!tabState[targetTab.id]) {
      tabState[targetTab.id] = {
        email: null, headers: {}, accessToken: null,
        lastHeartbeat: 0, recaptchaReady: false,
      };
    }
    // NOTE: Removed optimistic email binding — was poisoning reCAPTCHA tokens

    // C12: Capture generation BEFORE inject — content.js may register_tab immediately
    const genBefore = tabState[targetTab.id]._registerGeneration || 0;

    // 5. Re-inject content.js to revive the content script
    try {
      await chrome.scripting.executeScript({
        target: { tabId: targetTab.id },
        files: ['content.js'],
      });
      console.log(`[VEO Bridge] 💉 Re-injected content.js into tab ${targetTab.id}`);
    } catch (e) {
      console.warn(`[VEO Bridge] Content.js injection failed for tab ${targetTab.id}: ${e.message}`);
      // Don't return null — tab might still be usable
    }

    // 6. Prevent Chrome from auto-discarding this tab again
    try {
      await chrome.tabs.update(targetTab.id, { autoDiscardable: false });
    } catch (_) { }

    // 7. Wait for content.js to self-register (generation must increment)
    // C12: Verified email + generation check prevents wrong-tab binding
    const confirmed = await new Promise(resolve => {
      const timeout = setTimeout(() => resolve(false), 40000);
      const check = setInterval(() => {
        const gen = tabState[targetTab.id]?._registerGeneration || 0;
        if (gen > genBefore) {
          clearInterval(check);
          clearTimeout(timeout);
          resolve(true);
        }
      }, 2000);
    });

    if (confirmed) {
      const detectedEmail = tabState[targetTab.id].email;
      if (detectedEmail === email) {
        console.log(
          `[VEO Bridge] ✅ Recovered tab ${targetTab.id} confirmed for ${email}`
        );
        return targetTab.id;
      } else {
        console.warn(
          `[VEO Bridge] ⚠️ Tab ${targetTab.id} = ${detectedEmail}, ` +
          `not ${email} — recovery did not match`
        );
        return null;
      }
    } else {
      console.warn(
        `[VEO Bridge] ⚠️ Tab ${targetTab.id} did not self-register in 40s — ` +
        `aborting recovery for ${email}`
      );
      return null;
    }

  } catch (e) {
    console.error(`[VEO Bridge] Stale tab recovery failed for ${email}: ${e.message}`);
    return null;
  }
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
// Header refresh is passive. Do not schedule periodic page-context probes/reloads;
// real Flow traffic updates captured headers naturally.
chrome.alarms.clear(HEADER_REFRESH_ALARM);
// Periodic tab cleanup every 2 minutes
chrome.alarms.create(TAB_CLEANUP_ALARM, { periodInMinutes: 2 });

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === KEEPALIVE_ALARM) {
    // RC2 FIX: Skip offscreen check during startup grace period (45s)
    // Tab may still be about:blank → Chrome kills offscreen → recreate loop
    if (Date.now() - _startupTime < STARTUP_GRACE_MS) return;
    // Ensure offscreen document is alive (it handles WS keepalive internally)
    ensureOffscreenDocument();
  }

  if (alarm.name === HEADER_REFRESH_ALARM) {
    console.log('[VEO Bridge] ⏰ Periodic header refresh skipped (passive mode)');
    chrome.alarms.clear(HEADER_REFRESH_ALARM);
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
      await sendMessageWithRetry(parseInt(tabId), { action: 'lightweight_header_refresh' });
      console.log(`[VEO Bridge] 🔄 Passive header refresh for tab ${tabId} (${state.email})`);
    } catch (e) {
      console.debug(`[VEO Bridge] Passive header refresh skipped for tab ${tabId}: ${e.message}`);
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
        const reloadResult = await safeTabReload(tab.id, 'header-refresh');
        if (reloadResult === RELOAD_RESULT.RELOADED) reloaded++;
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

        // Do not reload an existing Flow tab just to capture headers. The app
        // should not mutate a tab the user is already using.
        const existingState = tabState[tab.id];
        const hasHeaders = existingState && Object.keys(existingState.headers || {}).length > 0;
        const hasRecentHeartbeat = existingState &&
          existingState.lastHeartbeat > 0 &&
          (Date.now() - existingState.lastHeartbeat) < 120000; // 2 min
        if (hasHeaders && hasRecentHeartbeat) {
          console.log(`[VEO Bridge] ⏭️ Skipping reload for tab ${tab.id} — has valid headers + recent heartbeat`);
        } else {
          console.log(`[VEO Bridge] ⏭️ Skipping startup reload for tab ${tab.id} — passive header capture`);
        }

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
const FLOW_PATH_RE = /^\/fx\/(?:[a-z]{2}\/)?tools\/flow(?:\/|$)/;
let _ensureVeoTabRunning = false; // debounce guard

function isFlowUrl(url) {
  if (!url || typeof url !== 'string') return false;
  try {
    const parsed = new URL(url);
    return parsed.hostname === 'labs.google' && FLOW_PATH_RE.test(parsed.pathname);
  } catch (_) {
    return url.includes('/fx/tools/flow') ||
      url.includes('/fx/vi/tools/flow') ||
      url.includes('/tools/flow');
  }
}

async function waitForTabLoad(tabId, maxWaitMs = 25000) {
  const start = Date.now();
  while (Date.now() - start < maxWaitMs) {
    try {
      const tab = await chrome.tabs.get(tabId);
      if (tab.status === 'complete') return true;
    } catch (_) {
      // Tab can be transiently unavailable while navigating.
    }
    await new Promise(r => setTimeout(r, 500));
  }
  return false;
}

async function ensureTabOnFlow(tabId, reason = 'flow_guard', targetUrl = VEO_URL) {
  if (!tabId) {
    return { success: false, error: 'missing_tab' };
  }

  let lastUrl = '';
  let lastError = '';
  for (let attempt = 1; attempt <= 3; attempt++) {
    let tab = null;
    try {
      tab = await chrome.tabs.get(tabId);
      lastUrl = tab?.url || '';
    } catch (e) {
      return { success: false, tabId, error: `tab_get_failed: ${e.message}` };
    }

    if (isFlowUrl(lastUrl) && tab.status === 'complete' && !tab.discarded) {
      try {
        await chrome.tabs.update(tabId, { pinned: true, autoDiscardable: false });
      } catch (_) { /* best effort */ }
      try {
        await chrome.scripting.executeScript({
          target: { tabId },
          files: ['content.js'],
        });
      } catch (e) {
        console.debug(`[VEO Bridge] Flow guard content.js refresh skipped for ${tabId}: ${e.message}`);
      }
      return { success: true, tabId, url: lastUrl, loadComplete: true };
    }

    console.warn(
      `[VEO Bridge] Flow guard (${reason}): tab ${tabId} at ` +
      `${lastUrl || '<blank>'} — navigating to ${targetUrl || VEO_URL} ` +
      `(attempt ${attempt}/3)`
    );

    try {
      if (tabState[tabId]) {
        tabState[tabId].recaptchaReady = false;
        setLifecycle(tabId, TAB_LIFECYCLE.NAVIGATING);
        persistTabState();
      }

      await chrome.tabs.update(tabId, {
        url: targetUrl || VEO_URL,
        pinned: true,
        autoDiscardable: false,
      });
      const loadComplete = await waitForTabLoad(tabId, 30000);
      await new Promise(r => setTimeout(r, 1200));

      const after = await chrome.tabs.get(tabId).catch(() => null);
      lastUrl = after?.url || lastUrl;
      if (loadComplete && isFlowUrl(lastUrl)) {
        try {
          await chrome.scripting.executeScript({
            target: { tabId },
            files: ['content.js'],
          });
        } catch (e) {
          console.debug(`[VEO Bridge] Flow guard content.js inject failed for ${tabId}: ${e.message}`);
        }
        if (tabState[tabId]) {
          setLifecycle(tabId, TAB_LIFECYCLE.RECOVERING);
          persistTabState();
        }
        return { success: true, tabId, url: lastUrl, loadComplete };
      }
    } catch (e) {
      lastError = e.message || String(e);
    }
  }

  return {
    success: false,
    tabId,
    url: lastUrl,
    error: `flow_navigation_failed: ${lastError || lastUrl || 'unknown_url'}`,
  };
}

async function ensureFlowForEmail(email, reason = 'flow_guard') {
  const ensured = await ensureVeoTabForEmail(email, VEO_URL);
  if (!ensured.success) return ensured;
  return ensureTabOnFlow(ensured.tabId, reason, VEO_URL);
}

async function ensureVeoTabForEmail(email, targetUrl = VEO_URL) {
  if (!email) {
    return { success: false, error: 'missing_email' };
  }

  try {
    const stored = await chrome.storage.local.get('__veo_identity');
    const identityEmail = stored.__veo_identity || '';
    const knownEmails = new Set(
      Object.values(tabState).map(s => s.email).filter(Boolean)
    );

    // Avoid cross-account binding. CDP identity is the strongest signal for
    // the browser profile that owns this extension instance.
    if (identityEmail && identityEmail !== email) {
      return {
        success: false,
        error: `identity_mismatch (${identityEmail} != ${email})`,
      };
    }
    if (!identityEmail && knownEmails.size > 0 && !knownEmails.has(email)) {
      return {
        success: false,
        error: 'ambiguous_profile_identity',
      };
    }

    let tabId = findTabForEmail(email);
    // Do not call recoverStaleTab() here. It waits up to 40s for content.js
    // self-registration and can make startup ensure_veo_tab exceed the Python
    // timeout. This ensure path has an identity guard above, so it can safely
    // bind an existing Flow tab directly or create one below.

    let tab = null;
    if (tabId) {
      try {
        tab = await chrome.tabs.get(tabId);
      } catch (_) {
        tabId = null;
      }
    }

    if (!tabId) {
      const tabs = await chrome.tabs.query({ url: '*://labs.google/*' });
      tab = tabs.find(t => (t.url || '').includes('/tools/flow')) || tabs[0] || null;

      if (!tab) {
        console.warn(`[VEO Bridge] 🆕 Creating VEO tab for ${email}`);
        tab = await chrome.tabs.create({
          url: targetUrl || VEO_URL,
          active: false,
          pinned: true,
        });
      }
      tabId = tab.id;
    }

    if (!tabState[tabId]) {
      tabState[tabId] = {
        email: null,
        headers: {},
        accessToken: null,
        lastHeartbeat: 0,
        recaptchaReady: false,
      };
    }

    // CDP identity/one-profile ownership makes this binding deterministic.
    tabState[tabId].email = email;
    tabState[tabId]._deadNotified = false;
    persistTabState();

    const currentUrl = tab?.url || '';
    const isAlreadyFlow = isFlowUrl(currentUrl);
    let loadComplete = true;

    try {
      if (isAlreadyFlow) {
        // Do not navigate an already-good Flow tab. Re-navigation can keep the
        // tab in NAVIGATING/RECOVERING long enough for Python startup to time out.
        await chrome.tabs.update(tabId, {
          pinned: true,
          autoDiscardable: false,
        });
      } else {
        tabState[tabId].recaptchaReady = false;
        setLifecycle(tabId, TAB_LIFECYCLE.NAVIGATING);
        persistTabState();
        await chrome.tabs.update(tabId, {
          url: targetUrl || VEO_URL,
          pinned: true,
          autoDiscardable: false,
        });
        loadComplete = await waitForTabLoad(tabId, 30000);
      }
    } catch (e) {
      return { success: false, error: `tab_update_failed: ${e.message}` };
    }

    try {
      await chrome.scripting.executeScript({
        target: { tabId },
        files: ['content.js'],
      });
      console.log(`[VEO Bridge] 💉 Ensured content.js in tab ${tabId} for ${email}`);
    } catch (e) {
      console.debug(`[VEO Bridge] ensure content.js inject failed for ${tabId}: ${e.message}`);
    }

    const hasFreshHeartbeat =
      Boolean(tabState[tabId].lastHeartbeat) &&
      Date.now() - tabState[tabId].lastHeartbeat < 30000;
    if (isAlreadyFlow && hasFreshHeartbeat) {
      setLifecycle(tabId, TAB_LIFECYCLE.ALIVE);
    } else {
      setLifecycle(tabId, TAB_LIFECYCLE.RECOVERING);
    }
    tabState[tabId]._registerGeneration = (tabState[tabId]._registerGeneration || 0) + 1;
    persistTabState();

    wsSend({
      action: 'register',
      email,
      tabId,
      version: EXT_VERSION,
      source: 'ensure_veo_tab',
    });

    return {
      success: true,
      tabId,
      url: targetUrl || VEO_URL,
      loadComplete,
    };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

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

  // RC1 FIX: Do NOT create offscreen here — let initializeStartup() handle it
  // to avoid race with restoreTabState() below.
  // Inject into already-open VEO tabs, clean up excess, then ensure one exists
  injectExistingTabs().then(() => {
    closeExcessTabs();
    ensureVeoTab();
  });
});

// ── Startup ─────────────────────────────────────────────────────────────

// RC1 FIX: Consolidated startup — single sequential flow
// Old code had 3 separate ensureOffscreenDocument() calls racing each other.
async function initializeStartup() {
  // Step 1: Restore tabState (filters out about:blank via RC3 fix)
  try {
    await restoreTabState();
  } catch (_) { }
  _tabStateRestored = true; // Fix G: Signal restore complete

  // Step 2: Create offscreen document ONCE
  await ensureOffscreenDocument();

  // Step 2.5: Service worker may have restarted while offscreen.js kept the
  // WebSocket alive. Re-sync state so existing tabs can register immediately.
  await syncOffscreenWsState();

  // Step 3: Inject into existing VEO tabs
  try {
    await injectExistingTabs();
    closeExcessTabs();
    ensureVeoTab();
  } catch (e) {
    console.debug('[VEO Bridge] Startup tab injection failed:', e.message);
  }
}
initializeStartup();
console.log(`[VEO Bridge] Background service worker started (v${EXT_VERSION} — offscreen WS + persistence)`);

// RC2 FIX: Startup grace period — skip offscreen health checks during first 45s
// During startup, tab is often about:blank → Chrome kills offscreen → loop
const _startupTime = Date.now();
const STARTUP_GRACE_MS = 45000; // 45s grace for tab to navigate to labs.google

// ── Offscreen Health Monitor ────────────────────────────────────────────
// Chrome may destroy offscreen documents under memory pressure.
// RC2+RC4 FIX: Grace period + exponential backoff on rapid failures.
let _offscreenRecreateFailCount = 0;
let _lastOffscreenRecreateTime = 0;
setInterval(async () => {
  const hasRegisteredTabs = Object.values(tabState).some(s => !!s.email);
  const hasQueuedWsTraffic = _wsSendQueue.length > 0;

  // RC2: Skip during startup grace period only while nothing is actively
  // waiting for the bridge. Once a real tab has registered or traffic is
  // queued, recover immediately.
  if (
    Date.now() - _startupTime < STARTUP_GRACE_MS &&
    !hasRegisteredTabs &&
    !hasQueuedWsTraffic
  ) {
    return;
  }

  // RC4: Exponential backoff — if recreate keeps failing, slow down
  const backoffMs = Math.min(15000 * Math.pow(2, _offscreenRecreateFailCount), 120000);
  if (_offscreenRecreateFailCount > 0 && Date.now() - _lastOffscreenRecreateTime < backoffMs) {
    return; // Still in backoff period
  }

  try {
    const contexts = await chrome.runtime.getContexts({
      contextTypes: ['OFFSCREEN_DOCUMENT'],
      documentUrls: [chrome.runtime.getURL('offscreen.html')],
    });
    if (contexts.length === 0) {
      console.warn(`[VEO Bridge] ⚠️ Offscreen document destroyed — recreating... (attempt ${_offscreenRecreateFailCount + 1})`);
      wsConnected = false;
      _lastOffscreenRecreateTime = Date.now();
      await ensureOffscreenDocument();
      await syncOffscreenWsState();

      // Check if it actually survived
      await new Promise(r => setTimeout(r, 2000)); // Wait 2s
      const recheck = await chrome.runtime.getContexts({
        contextTypes: ['OFFSCREEN_DOCUMENT'],
        documentUrls: [chrome.runtime.getURL('offscreen.html')],
      });
      if (recheck.length > 0) {
        console.log('[VEO Bridge] ✅ Offscreen document survived — resetting backoff');
        _offscreenRecreateFailCount = 0; // Success — reset backoff
      } else {
        _offscreenRecreateFailCount++; // Failed again — increase backoff
        console.warn(`[VEO Bridge] ⚠️ Offscreen killed again — backoff ${Math.ceil(backoffMs / 1000)}s`);
      }
    } else {
      // Background SW may have restarted and lost `wsConnected` while the
      // offscreen document stayed alive. Re-sync cheaply here as a safeguard.
      if (!wsConnected) {
        await syncOffscreenWsState();
      }
      // Healthy — reset failure counter
      if (_offscreenRecreateFailCount > 0) {
        _offscreenRecreateFailCount = 0;
      }
    }
  } catch (e) {
    console.debug('[VEO Bridge] Offscreen health check failed:', e.message);
  }
}, 15000);


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
