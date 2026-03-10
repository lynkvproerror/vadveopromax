/* VEO Pro Max Extension v2.2.2 - Protected */
const WEBSOCKET_PORTS = [8765, 8766, 8767];
const RECONNECT_BASE_MS = 3000;
const RECONNECT_MAX_MS = 15000;
let ws = null;
let wsConnected = false;
let currentPortIndex = 0;
let reconnectDelay = RECONNECT_BASE_MS;
let reconnectTimer = null;
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
reconnectDelay = RECONNECT_BASE_MS;
_fastScanActive = false;
chrome.runtime.sendMessage({
type: 'offscreen_ws_state',
connected: true,
port: port,
}).catch(() => { });
};
ws.onmessage = (event) => {
try {
const msg = JSON.parse(event.data);
chrome.runtime.sendMessage({
type: 'offscreen_ws_incoming',
data: msg,
}).catch((err) => {
});
} catch (e) {
console.error('[Offscreen] Failed to parse WS message:', e);
}
};
ws.onclose = (event) => {
wsConnected = false;
ws = null;
chrome.runtime.sendMessage({
type: 'offscreen_ws_state',
connected: false,
}).catch(() => { });
if (event.wasClean) {
currentPortIndex = (currentPortIndex + 1) % WEBSOCKET_PORTS.length;
scheduleReconnect();
if (currentPortIndex === 0) {
reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS);
}
} else {
fastPortScan();
}
};
ws.onerror = () => {
};
} catch (e) {
currentPortIndex = (currentPortIndex + 1) % WEBSOCKET_PORTS.length;
scheduleReconnect();
reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS);
}
}
let _fastScanActive = false;
async function fastPortScan() {
if (_fastScanActive) return;
_fastScanActive = true;
if (reconnectTimer) {
clearTimeout(reconnectTimer);
reconnectTimer = null;
}
for (let attempt = 0; attempt < 3 && _fastScanActive; attempt++) {
for (let i = 0; i < WEBSOCKET_PORTS.length && _fastScanActive; i++) {
currentPortIndex = i;
connectWebSocket();
await new Promise(r => setTimeout(r, 500));
if (wsConnected) {
_fastScanActive = false;
return;
}
if (ws && ws.readyState !== WebSocket.OPEN) {
try { ws.close(); } catch (_) { }
ws = null;
}
}
}
_fastScanActive = false;
reconnectDelay = RECONNECT_BASE_MS;
currentPortIndex = 0;
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
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
if (msg.type === 'offscreen_ws_send') {
const ok = wsSend(msg.data);
sendResponse({ sent: ok });
return false;
}
if (msg.type === String.fromCharCode(0x6f,0x66,0x66,0x73,0x63,0x72,0x65,0x65,0x6e,0x5f,0x77,0x73,0x5f,0x73,0x74,0x61,0x74,0x75,0x73)) {
sendResponse({ connected: wsConnected });
return false;
}
if (msg.type === 'offscreen_ws_reconnect') {
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
setInterval(() => {
if (ws && ws.readyState === WebSocket.OPEN) {
wsSend({ action: 'ping' });
} else {
connectWebSocket();
}
}, 20000);
connectWebSocket();