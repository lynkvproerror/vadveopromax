/**
 * VEO Pro Max Bridge — Offscreen WebSocket Client
 *
 * This script runs in an offscreen document (persistent, never suspended).
 * It maintains the WebSocket connection to the Python app and relays
 * messages to/from the background service worker via chrome.runtime.
 *
 * Architecture:
 *   Python App ←→ [WebSocket] ←→ offscreen.js ←→ [chrome.runtime] ←→ background.js
 *
 * Why: MV3 service workers get suspended after 30s of inactivity,
 * killing WebSocket connections. Offscreen documents are NOT suspended.
 */

// ── Config ─────────────────────────────────────────────────────────────
const WEBSOCKET_PORTS = [8765, 8766, 8767];
const RECONNECT_BASE_MS = 3000;
const RECONNECT_MAX_MS = 60000;
const KEEPALIVE_RETRY_COOLDOWN_MS = 8000;
const FAST_SCAN_PORT_DELAY_MS = 350;
const FAST_SCAN_MAX_ROUNDS = 1;
const SAME_PORT_RETRY_BEFORE_SCAN = 2;

let ws = null;
let wsConnected = false;
let currentPortIndex = 0;
let reconnectDelay = RECONNECT_BASE_MS;
let reconnectTimer = null;
let _reconnectScheduled = false;  // Prevent keepalive from competing
let _lastConnectAttemptAt = 0;
let _lastConnectPort = null;
let _lastConnectUrl = '';
let _lastOpenAt = 0;
let _lastOpenPort = null;
let _lastCloseAt = 0;
let _lastCloseCode = null;
let _lastCloseReason = '';
let _lastCloseWasClean = null;
let _lastErrorAt = 0;
let _lastErrorMessage = '';
let _lastDebugEvent = 'startup';
let _preferredPort = WEBSOCKET_PORTS[0];
let _samePortFailureCount = 0;
let _startupInitialized = false;
let _connectMode = 'startup';

function getCurrentPort() {
    return WEBSOCKET_PORTS[currentPortIndex] ?? WEBSOCKET_PORTS[0];
}

function setCurrentPort(port) {
    const idx = WEBSOCKET_PORTS.indexOf(port);
    if (idx >= 0) {
        currentPortIndex = idx;
        _preferredPort = port;
    }
}

function getPortOrder(seedPort = null) {
    const preferred = seedPort ?? getCurrentPort();
    return [
        preferred,
        ...WEBSOCKET_PORTS.filter(p => p !== preferred),
    ];
}

async function loadPreferredPort() {
    try {
        const stored = await chrome.runtime.sendMessage({
            type: 'offscreen_pref_port_get',
        });
        const port = Number(stored?.port);
        if (WEBSOCKET_PORTS.includes(port)) {
            setCurrentPort(port);
            notifyBackground('preferred_port_loaded', { preferredPort: port });
        }
    } catch (_) { }
}

function persistPreferredPort(port) {
    if (!WEBSOCKET_PORTS.includes(port)) return;
    setCurrentPort(port);
    chrome.runtime.sendMessage({
        type: 'offscreen_pref_port_set',
        port,
    }).catch(() => { });
}

function readyStateName() {
    if (!ws) return 'NONE';
    switch (ws.readyState) {
        case WebSocket.CONNECTING: return 'CONNECTING';
        case WebSocket.OPEN: return 'OPEN';
        case WebSocket.CLOSING: return 'CLOSING';
        case WebSocket.CLOSED: return 'CLOSED';
        default: return `UNKNOWN(${ws.readyState})`;
    }
}

function buildWsDebug(extra = {}) {
    return {
        connected: wsConnected,
        currentPort: getCurrentPort(),
        preferredPort: _preferredPort,
        readyState: ws ? ws.readyState : null,
        readyStateName: readyStateName(),
        reconnectDelayMs: reconnectDelay,
        reconnectScheduled: _reconnectScheduled,
        fastScanActive: _fastScanActive,
        samePortFailureCount: _samePortFailureCount,
        connectMode: _connectMode,
        lastConnectAttemptAt: _lastConnectAttemptAt,
        lastConnectPort: _lastConnectPort,
        lastConnectUrl: _lastConnectUrl,
        lastOpenAt: _lastOpenAt,
        lastOpenPort: _lastOpenPort,
        lastCloseAt: _lastCloseAt,
        lastCloseCode: _lastCloseCode,
        lastCloseReason: _lastCloseReason,
        lastCloseWasClean: _lastCloseWasClean,
        lastErrorAt: _lastErrorAt,
        lastErrorMessage: _lastErrorMessage,
        lastDebugEvent: _lastDebugEvent,
        ...extra,
    };
}

function notifyBackground(event, extra = {}) {
    _lastDebugEvent = event;
    chrome.runtime.sendMessage({
        type: 'offscreen_ws_debug',
        event,
        debug: buildWsDebug(extra),
    }).catch(() => { });
}

// ── WebSocket Connection ───────────────────────────────────────────────

function connectWebSocket(mode = 'normal') {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        return;
    }

    const port = getCurrentPort();
    const url = `ws://127.0.0.1:${port}`;
    const managedByFastScan = mode === 'fast_scan';
    _connectMode = mode;
    _lastConnectAttemptAt = Date.now();
    _lastConnectPort = port;
    _lastConnectUrl = url;
    notifyBackground('connect_attempt', { message: `dial ${url}`, mode });

    try {
        ws = new WebSocket(url);

        ws.onopen = () => {
            wsConnected = true;
            reconnectDelay = RECONNECT_BASE_MS; // reset backoff
            _fastScanActive = false; // stop fast scan if running
            _samePortFailureCount = 0;
            _lastOpenAt = Date.now();
            _lastOpenPort = port;
            _lastErrorMessage = '';
            persistPreferredPort(port);
            console.log(`[Offscreen] ✅ WebSocket connected on port ${port}`);
            notifyBackground('connected', { message: `open ${url}` });

            // Notify background.js that WS is connected
            chrome.runtime.sendMessage({
                type: 'offscreen_ws_state',
                connected: true,
                port: port,
            }).catch(() => { }); // background may not be listening yet
        };

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                // Relay incoming message to background.js
                chrome.runtime.sendMessage({
                    type: 'offscreen_ws_incoming',
                    data: msg,
                }).catch((err) => {
                    // Background SW might be waking up — message will be retried by Python
                    console.debug(`[Offscreen] Relay to background failed: ${err.message}`);
                });
            } catch (e) {
                console.error('[Offscreen] Failed to parse WS message:', e);
            }
        };

        ws.onclose = (event) => {
            wsConnected = false;
            _lastCloseAt = Date.now();
            _lastCloseCode = event.code;
            _lastCloseReason = event.reason || '';
            _lastCloseWasClean = event.wasClean;
            notifyBackground('closed', {
                message: `close code=${event.code} clean=${event.wasClean}`,
            });
            ws = null;

            // Notify background that WS is disconnected
            chrome.runtime.sendMessage({
                type: 'offscreen_ws_state',
                connected: false,
            }).catch(() => { });

            if (managedByFastScan || _fastScanActive) {
                return;
            }

            _samePortFailureCount += 1;

            if (_samePortFailureCount <= SAME_PORT_RETRY_BEFORE_SCAN) {
                const retryDelay = Math.min(reconnectDelay, 1500);
                console.debug(
                    `[Offscreen] WebSocket closed on port ${port} ` +
                    `(clean=${event.wasClean}) — retrying same port in ${retryDelay}ms...`
                );
                scheduleReconnect('same_port_retry', retryDelay);
            } else {
                console.debug(
                    `[Offscreen] WebSocket still unavailable on preferred port ${port}, ` +
                    'starting bounded port scan...'
                );
                fastPortScan(`close:${port}`);
            }
        };

        ws.onerror = () => {
            _lastErrorAt = Date.now();
            _lastErrorMessage = _fastScanActive
                ? `ws_error_fast_scan_port_${port}`
                : `ws_error_or_refused_port_${port}`;
            notifyBackground('error', { message: _lastErrorMessage });
            // Only log if NOT in fast scan (avoids our own console spam).
            if (!_fastScanActive) {
                console.debug(`[Offscreen] WebSocket connection refused on port ${port}`);
            }
        };
    } catch (e) {
        _lastErrorAt = Date.now();
        _lastErrorMessage = e.message || 'connect_exception';
        notifyBackground('connect_exception', { message: _lastErrorMessage });
        console.debug('[Offscreen] WebSocket connection failed:', e.message);
        if (!managedByFastScan) {
            _samePortFailureCount += 1;
            if (_samePortFailureCount <= SAME_PORT_RETRY_BEFORE_SCAN) {
                scheduleReconnect('connect_exception', Math.min(reconnectDelay, 1500));
            } else {
                fastPortScan('connect_exception');
            }
        }
    }
}

// ── Fast Port Scan (for app restart recovery) ──────────────────────────
// Tries all 3 ports rapidly (500ms per port) before falling back to normal
// exponential backoff. Reconnects within 1.5s instead of up to 45s.
let _fastScanActive = false;

async function fastPortScan(reason = 'unknown') {
    if (_fastScanActive) return;
    _fastScanActive = true;
    notifyBackground('fast_scan_start', { reason });

    // Clear any scheduled normal reconnect
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }

    const portOrder = getPortOrder(_preferredPort);

    // Try each port rapidly, but only one bounded sweep. This keeps recovery
    // fast without flooding DevTools with repeated failed socket dials.
    for (let attempt = 0; attempt < FAST_SCAN_MAX_ROUNDS && _fastScanActive; attempt++) {
        for (const port of portOrder) {
            if (!_fastScanActive) break;
            setCurrentPort(port);
            connectWebSocket('fast_scan');

            // Wait briefly — if connected, fast scan stops immediately.
            await new Promise(r => setTimeout(r, FAST_SCAN_PORT_DELAY_MS));
            if (wsConnected) {
                _fastScanActive = false;
                return;
            }

            // Close failed attempt
            if (ws && ws.readyState !== WebSocket.OPEN) {
                try { ws.close(); } catch (_) { }
                ws = null;
            }
        }
    }

    // Fast scan exhausted — fall back to normal reconnect with backoff
    _fastScanActive = false;
    reconnectDelay = RECONNECT_BASE_MS;
    setCurrentPort(_preferredPort);
    _samePortFailureCount = 0;
    notifyBackground('fast_scan_exhausted');
    console.debug('[Offscreen] Fast scan exhausted, falling back to normal reconnect...');
    scheduleReconnect('post_fast_scan', 5000);
}

function scheduleReconnect(reason = 'normal', delayMs = reconnectDelay) {
    if (reconnectTimer) clearTimeout(reconnectTimer);
    _reconnectScheduled = true;
    notifyBackground('reconnect_scheduled', { nextDelayMs: delayMs, reason });
    reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        _reconnectScheduled = false;
        notifyBackground('reconnect_firing', { reason });
        connectWebSocket(reason);
    }, delayMs);
    reconnectDelay = Math.min(Math.max(delayMs, reconnectDelay) * 1.5, RECONNECT_MAX_MS);
}

function wsSend(data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(data));
        return true;
    }
    return false;
}

// ── Listen for messages from background.js ─────────────────────────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === 'offscreen_ws_send') {
        // Background wants to send a WS message
        const ok = wsSend(msg.data);
        sendResponse({ sent: ok });
        return false; // sync
    }

    if (msg.type === 'offscreen_ws_status') {
        // Background wants to check WS status
        sendResponse(buildWsDebug());
        return false;
    }

    if (msg.type === 'offscreen_ws_reconnect') {
        // Background wants to force reconnect
        if (ws) {
            try { ws.close(); } catch (_) { }
        }
        ws = null;
        wsConnected = false;
        reconnectDelay = RECONNECT_BASE_MS;
        _samePortFailureCount = 0;
        notifyBackground('manual_reconnect');
        connectWebSocket('manual_reconnect');
        sendResponse({ ok: true });
        return false;
    }

    return false;
});

// ── Keepalive ping (offscreen → WS server) ─────────────────────────────
// Send ping every 20s to keep connection alive and detect dead connections
setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
        wsSend({ action: 'ping' });
    } else if (
        !_reconnectScheduled &&
        !_fastScanActive &&
        (Date.now() - _lastConnectAttemptAt) > KEEPALIVE_RETRY_COOLDOWN_MS
    ) {
        // Avoid extra failed dials while a recent reconnect attempt is still settling.
        connectWebSocket('keepalive_retry');
    }
}, 20000);

// ── Start ──────────────────────────────────────────────────────────────
async function initializeOffscreen() {
    if (_startupInitialized) return;
    _startupInitialized = true;
    await loadPreferredPort();
    console.log(`[Offscreen] Offscreen document started — establishing WebSocket (preferred=${getCurrentPort()})...`);
    connectWebSocket('startup');
}

initializeOffscreen();
