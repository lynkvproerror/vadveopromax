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
const RECONNECT_MAX_MS = 15000;

let ws = null;
let wsConnected = false;
let currentPortIndex = 0;
let reconnectDelay = RECONNECT_BASE_MS;
let reconnectTimer = null;

// ── WebSocket Connection ───────────────────────────────────────────────

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
            reconnectDelay = RECONNECT_BASE_MS; // reset backoff
            _fastScanActive = false; // stop fast scan if running
            console.log(`[Offscreen] ✅ WebSocket connected on port ${port}`);

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
            ws = null;

            // Notify background that WS is disconnected
            chrome.runtime.sendMessage({
                type: 'offscreen_ws_state',
                connected: false,
            }).catch(() => { });

            if (event.wasClean) {
                // Clean close (server intentionally closed) — rotate port + normal backoff
                currentPortIndex = (currentPortIndex + 1) % WEBSOCKET_PORTS.length;
                console.debug(
                    `[Offscreen] WebSocket closed cleanly (port ${port}), ` +
                    `reconnecting in ${reconnectDelay / 1000}s...`
                );
                scheduleReconnect();
                if (currentPortIndex === 0) {
                    reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS);
                }
            } else {
                // Non-clean close (app restart/crash) — FAST port scan
                console.debug(
                    `[Offscreen] WebSocket lost (port ${port}, non-clean), ` +
                    `starting fast port scan...`
                );
                fastPortScan();
            }
        };

        ws.onerror = () => {
            console.debug(`[Offscreen] WebSocket connection refused on port ${port}`);
        };
    } catch (e) {
        console.debug('[Offscreen] WebSocket connection failed:', e.message);
        currentPortIndex = (currentPortIndex + 1) % WEBSOCKET_PORTS.length;
        scheduleReconnect();
        reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS);
    }
}

// ── Fast Port Scan (for app restart recovery) ──────────────────────────
// Tries all 3 ports rapidly (500ms per port) before falling back to normal
// exponential backoff. Reconnects within 1.5s instead of up to 45s.
let _fastScanActive = false;

async function fastPortScan() {
    if (_fastScanActive) return;
    _fastScanActive = true;

    // Clear any scheduled normal reconnect
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }

    // Try each port rapidly
    for (let attempt = 0; attempt < 3 && _fastScanActive; attempt++) {
        for (let i = 0; i < WEBSOCKET_PORTS.length && _fastScanActive; i++) {
            currentPortIndex = i;
            connectWebSocket();

            // Wait 500ms — if connected, _fastScanActive will be set to false
            await new Promise(r => setTimeout(r, 500));
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
    currentPortIndex = 0;
    console.debug('[Offscreen] Fast scan exhausted, falling back to normal reconnect...');
    scheduleReconnect();
}

function scheduleReconnect() {
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connectWebSocket();
    }, reconnectDelay);
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
        sendResponse({ connected: wsConnected });
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
        connectWebSocket();
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
    } else {
        connectWebSocket();
    }
}, 20000);

// ── Start ──────────────────────────────────────────────────────────────
console.log('[Offscreen] Offscreen document started — establishing WebSocket...');
connectWebSocket();
