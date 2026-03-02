/* VEO Pro Max Extension v2.2.2 - Protected */
if (window.__veoContentLoaded) {
try { detectAndRegister(); } catch (e) { }
} else {
window.__veoContentLoaded = true;
const MAX_EMAIL_RETRIES = 5;
const EMAIL_RETRY_INTERVAL = 3000;
const HEARTBEAT_INTERVAL = 20000;
const MOUSE_SIM_MIN = 30000;
const MOUSE_SIM_MAX = 90000;
const MICRO_SCROLL_MIN = 120000;
const MICRO_SCROLL_MAX = 300000;
const RECAPTCHA_WARM_INTERVAL = 60000;
let _registeredEmail = null;
let _heartbeatTimer = null;
let _mouseSimTimer = null;
let _scrollTimer = null;
let _recaptchaWarmTimer = null;
function detectAndRegister(retryCount = 0) {
if (window.location.hostname === 'accounts.google.com' ||
window.location.href.includes('accounts.google.com/ServiceLogin') ||
window.location.href.includes('accounts.google.com/signin')) {
chrome.runtime.sendMessage({ action: String.fromCharCode(0x74,0x61,0x62,0x5f,0x6c,0x6f,0x67,0x6f,0x75,0x74), reason: String.fromCharCode(0x6c,0x6f,0x67,0x69,0x6e,0x5f,0x72,0x65,0x64,0x69,0x72,0x65,0x63,0x74) });
return;
}
const email = extractEmail();
if (email) {
_registeredEmail = email;
chrome.runtime.sendMessage({ action: 'register_tab', email });
startAntiIdle();
return;
}
if (retryCount === 0) {
}
if (retryCount < MAX_EMAIL_RETRIES) {
setTimeout(() => detectAndRegister(retryCount + 1), EMAIL_RETRY_INTERVAL);
} else {
chrome.runtime.sendMessage({
action: String.fromCharCode(0x74,0x61,0x62,0x5f,0x6c,0x6f,0x67,0x6f,0x75,0x74),
reason: String.fromCharCode(0x65,0x6d,0x61,0x69,0x6c,0x5f,0x6e,0x6f,0x74,0x5f,0x66,0x6f,0x75,0x6e,0x64),
url: window.location.href,
});
startAntiIdle();
}
}
function extractEmail() {
const nextDataEl = document.getElementById('__NEXT_DATA__');
if (nextDataEl) {
try {
const data = JSON.parse(nextDataEl.textContent);
const session = data?.props?.pageProps?.session;
if (session?.user?.email) return session.user.email;
const user = data?.props?.pageProps?.user;
if (user?.email) return user.email;
} catch (e) {
}
}
const profileEl = document.querySelector('[data-email]');
if (profileEl) return profileEl.getAttribute('data-email');
for (const selector of [
'a[aria-label*="@"]',
'button[aria-label*="@"]',
'[aria-label*="@"]',
]) {
const el = document.querySelector(selector);
if (el) {
const label = el.getAttribute('aria-label');
const match = label.match(/[\w.+-]+@[\w-]+\.[\w.]+/);
if (match) return match[0];
}
}
const googleImgs = document.querySelectorAll('img[alt*="@"]');
for (const img of googleImgs) {
const alt = img.getAttribute('alt');
const match = alt.match(/[\w.+-]+@[\w-]+\.[\w.]+/);
if (match) return match[0];
}
const accountBtns = document.querySelectorAll(
'[data-ogsr-up], [data-authuser], .gb_Fc, .gb_Oc'
);
for (const btn of accountBtns) {
const text = btn.textContent || btn.innerText || '';
const match = text.match(/[\w.+-]+@[\w-]+\.[\w.]+/);
if (match) return match[0];
}
const deepSelectors = [
'.gb_lb',
'[data-identifier]',
'.yDmH0d',
];
for (const sel of deepSelectors) {
const els = document.querySelectorAll(sel);
for (const el of els) {
const text = el.textContent || el.getAttribute('data-identifier') || '';
const match = text.match(/[\w.+-]+@[\w-]+\.[\w.]+/);
if (match) return match[0];
}
}
return null;
}
function extractSiteKey() {
for (const s of document.querySelectorAll('script[src*="recaptcha"]')) {
const m = s.src.match(/render=([^&]+)/);
if (m && m[1] !== 'explicit') return m[1];
}
if (typeof ___grecaptcha_cfg !== 'undefined' && ___grecaptcha_cfg.clients) {
for (const id in ___grecaptcha_cfg.clients) {
const client = ___grecaptcha_cfg.clients[id];
for (const key in client) {
const obj = client[key];
if (obj && typeof obj === 'object') {
for (const k2 in obj) {
const v = obj[k2];
if (v && typeof v === 'object' && v.sitekey) return v.sitekey;
}
}
}
}
}
const el = document.querySelector('[data-sitekey]');
if (el) return el.getAttribute('data-sitekey');
return null;
}
function randomBetween(min, max) {
return Math.floor(Math.random() * (max - min + 1)) + min;
}
function startAntiIdle() {
if (!_heartbeatTimer) {
_heartbeatTimer = setInterval(sendHeartbeat, HEARTBEAT_INTERVAL);
sendHeartbeat();
}
if (!_mouseSimTimer) {
scheduleMouseSim();
}
if (!_scrollTimer) {
scheduleMicroScroll();
}
if (!_recaptchaWarmTimer) {
_recaptchaWarmTimer = setInterval(checkRecaptchaWarmth, RECAPTCHA_WARM_INTERVAL);
setTimeout(checkRecaptchaWarmth, 10000);
}
}
function sendHeartbeat() {
try {
chrome.runtime.sendMessage({
action: 'content_heartbeat',
email: _registeredEmail,
timestamp: Date.now(),
url: window.location.href,
readyState: document.readyState,
});
} catch (e) {
stopAntiIdle();
}
}
function scheduleMouseSim() {
const delay = randomBetween(MOUSE_SIM_MIN, MOUSE_SIM_MAX);
_mouseSimTimer = setTimeout(() => {
simulateMouseMove();
scheduleMouseSim();
}, delay);
}
function scheduleMicroScroll() {
const delay = randomBetween(MICRO_SCROLL_MIN, MICRO_SCROLL_MAX);
_scrollTimer = setTimeout(() => {
performMicroScroll();
scheduleMicroScroll();
}, delay);
}
let _lastMouseX = null;
let _lastMouseY = null;
function cubicBezier(t, p0, p1, p2, p3) {
const u = 1 - t;
return u * u * u * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t * p3;
}
function easeInOutCubic(t) {
return t < 0.5
? 4 * t * t * t
: 1 - Math.pow(-2 * t + 2, 3) / 2;
}
function generateBezierPath(x0, y0, x1, y1) {
const dist = Math.hypot(x1 - x0, y1 - y0);
const steps = Math.max(8, Math.min(25, Math.floor(dist / 15)));
const curvature = 0.2 + Math.random() * 0.3;
const midX = (x0 + x1) / 2;
const midY = (y0 + y1) / 2;
const perpX = -(y1 - y0);
const perpY = x1 - x0;
const perpLen = Math.hypot(perpX, perpY) || 1;
const sign = Math.random() < 0.5 ? 1 : -1;
const offset = dist * curvature * sign;
const cp1x = midX + (perpX / perpLen) * offset * 0.6 + (Math.random() - 0.5) * 20;
const cp1y = midY + (perpY / perpLen) * offset * 0.6 + (Math.random() - 0.5) * 20;
const cp2x = midX + (perpX / perpLen) * offset * 0.4 + (Math.random() - 0.5) * 20;
const cp2y = midY + (perpY / perpLen) * offset * 0.4 + (Math.random() - 0.5) * 20;
const path = [];
for (let i = 0; i <= steps; i++) {
const rawT = i / steps;
const t = easeInOutCubic(rawT);
path.push({
x: cubicBezier(t, x0, cp1x, cp2x, x1),
y: cubicBezier(t, y0, cp1y, cp2y, y1),
});
}
return path;
}
async function humanMouseMove(targetX, targetY) {
const startX = _lastMouseX ?? randomBetween(200, 600);
const startY = _lastMouseY ?? randomBetween(200, 400);
const path = generateBezierPath(startX, startY, targetX, targetY);
for (let i = 0; i < path.length; i++) {
const pt = path[i];
const jitterX = (Math.random() - 0.5) * 2;
const jitterY = (Math.random() - 0.5) * 2;
const finalX = Math.round(pt.x + jitterX);
const finalY = Math.round(pt.y + jitterY);
document.body.dispatchEvent(new MouseEvent('mousemove', {
clientX: finalX, clientY: finalY,
bubbles: true, cancelable: true,
}));
if (Math.random() < 0.3) {
document.body.dispatchEvent(new PointerEvent('pointermove', {
clientX: finalX + (Math.random() - 0.5) * 2,
clientY: finalY + (Math.random() - 0.5) * 2,
bubbles: true, cancelable: true,
}));
}
_lastMouseX = finalX;
_lastMouseY = finalY;
let delay = randomBetween(10, 40);
if (Math.random() < 0.08) {
delay += randomBetween(50, 150);
}
await sleep(delay);
}
}
async function simulateMouseMove() {
if (document.visibilityState === 'visible') return;
try {
const w = Math.max(window.innerWidth || 800, 400);
const h = Math.max(window.innerHeight || 600, 300);
const targetX = randomBetween(w * 0.1, w * 0.9);
const targetY = randomBetween(h * 0.1, h * 0.8);
await humanMouseMove(targetX, targetY);
if (Math.random() < 0.4) {
await sleep(randomBetween(200, 800));
const el = document.elementFromPoint(targetX, targetY);
if (el) {
el.dispatchEvent(new MouseEvent('mouseenter', {
clientX: targetX, clientY: targetY,
bubbles: false, cancelable: true,
}));
el.dispatchEvent(new MouseEvent('mouseover', {
clientX: targetX, clientY: targetY,
bubbles: true, cancelable: true,
}));
}
}
if (Math.random() < 0.25) {
await sleep(randomBetween(100, 300));
const driftX = targetX + randomBetween(-15, 15);
const driftY = targetY + randomBetween(-10, 10);
await humanMouseMove(driftX, driftY);
}
} catch (e) {
}
}
async function performMicroScroll() {
if (document.visibilityState === 'visible') return;
try {
const direction = Math.random() < 0.7 ? 1 : -1;
const totalScroll = randomBetween(20, 80) * direction;
const steps = randomBetween(2, 5);
let remaining = totalScroll;
for (let i = 0; i < steps; i++) {
const fraction = (steps - i) / steps;
const scrollAmount = Math.round(remaining * fraction * 0.5);
remaining -= scrollAmount;
window.scrollBy({ top: scrollAmount, behavior: 'instant' });
document.dispatchEvent(new WheelEvent('wheel', {
deltaY: scrollAmount,
bubbles: true, cancelable: true,
}));
await sleep(randomBetween(30, 80));
}
if (Math.random() < 0.5) {
await sleep(randomBetween(100, 250));
const bounce = Math.round(totalScroll * -0.15);
window.scrollBy({ top: bounce, behavior: 'instant' });
}
} catch (e) { }
}
function sleep(ms) {
return new Promise(resolve => setTimeout(resolve, ms));
}
function checkRecaptchaWarmth() {
try {
const hasGrecaptcha = typeof grecaptcha !== 'undefined';
const hasEnterprise = hasGrecaptcha && typeof grecaptcha.enterprise !== 'undefined';
const hasExecute = hasEnterprise && typeof grecaptcha.enterprise.execute === 'function';
const hasSiteKey = !!extractSiteKey();
const ready = hasExecute && hasSiteKey;
chrome.runtime.sendMessage({
action: 'recaptcha_warmth',
email: _registeredEmail,
ready,
details: {
grecaptcha: hasGrecaptcha,
enterprise: hasEnterprise,
execute: hasExecute,
siteKey: hasSiteKey,
pageLoaded: document.readyState === 'complete',
},
});
} catch (e) {
}
}
function stopAntiIdle() {
if (_heartbeatTimer) { clearInterval(_heartbeatTimer); _heartbeatTimer = null; }
if (_mouseSimTimer) { clearTimeout(_mouseSimTimer); _mouseSimTimer = null; }
if (_scrollTimer) { clearTimeout(_scrollTimer); _scrollTimer = null; }
if (_recaptchaWarmTimer) { clearInterval(_recaptchaWarmTimer); _recaptchaWarmTimer = null; }
}
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
if (msg.action === 'get_access_token') {
const result = extractAccessToken();
sendResponse(result);
return false;
}
if (msg.action === 'assign_email') {
const email = msg.email;
if (email) {
_registeredEmail = email;
chrome.runtime.sendMessage({ action: 'register_tab', email });
}
sendResponse({ ok: true });
return false;
}
if (msg.action === 'simulate_activity') {
(async () => {
await simulateMouseMove();
await performMicroScroll();
})().catch(() => { });
sendResponse({ ok: true });
return false;
}
if (msg.action === 'lightweight_header_refresh') {
performLightweightRefresh();
sendResponse({ ok: true });
return false;
}
if (msg.action === 'submit_prompt') {
const requestId = msg.requestId;
const endpointUrl = msg.endpointUrl;
const payload = msg.payload || {};
const needsRecaptcha = msg.needsRecaptcha !== false;
const endpointKey = msg.endpoint || '';
const resultHandler = (event) => {
if (event.source !== window) return;
if (!event.data || event.data.type !== '__VEO_SUBMIT_RESULT__') return;
if (event.data.requestId !== requestId) return;
window.removeEventListener('message', resultHandler);
chrome.runtime.sendMessage({
action: 'submit_prompt_relay_result',
requestId: requestId,
...event.data.result,
});
};
window.addEventListener('message', resultHandler);
const timeout = setTimeout(() => {
window.removeEventListener('message', resultHandler);
console.error(`[VEO Bridge Content] ❌ submit_prompt timed out (45s)`);
chrome.runtime.sendMessage({
action: 'submit_prompt_relay_result',
requestId: requestId,
success: false,
error: 'Content script relay timeout (45s)',
});
}, 45000);
const origHandler = resultHandler;
const wrappedHandler = (event) => {
if (event.source !== window) return;
if (!event.data || event.data.type !== '__VEO_SUBMIT_RESULT__') return;
if (event.data.requestId !== requestId) return;
clearTimeout(timeout);
origHandler(event);
};
window.removeEventListener('message', resultHandler);
window.addEventListener('message', wrappedHandler);
const script = document.createElement('script');
script.textContent = `
(async function() {
const requestId = ${JSON.stringify(requestId)};
const endpointUrl = ${JSON.stringify(endpointUrl)};
const payload = ${JSON.stringify(payload)};
const needsRecaptcha = ${JSON.stringify(needsRecaptcha)};
const endpointKey = ${JSON.stringify(endpointKey)};
try {
// ── Step 1: reCAPTCHA token ──────────────────────────────
let recaptchaToken = null;
if (needsRecaptcha) {
let siteKey = null;
// Extract from script tags
for (const s of document.querySelectorAll('script[src*="recaptcha"]')) {
const m = s.src.match(/render=([^&]+)/);
if (m && m[1] !== 'explicit') { siteKey = m[1]; break; }
}
// Fallback: from grecaptcha config
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
window.postMessage({ type: '__VEO_SUBMIT_RESULT__', requestId, result: {
success: false, error: 'Could not extract reCAPTCHA site key'
}}, '*');
return;
}
try {
// HAR verified: T2I uses IMAGE_GENERATION, video endpoints use VIDEO_GENERATION
const rcAction = (endpointKey === 'T2I') ? 'IMAGE_GENERATION' : 'VIDEO_GENERATION';
const recaptchaPromise = grecaptcha.enterprise.execute(siteKey, { action: rcAction });
const recaptchaTimeout = new Promise((_, reject) =>
setTimeout(() => reject(new Error('reCAPTCHA execute timeout (10s)')), 10000)
);
recaptchaToken = await Promise.race([recaptchaPromise, recaptchaTimeout]);
// HAR verified: valid tokens are 1742-2169 chars
if (!recaptchaToken || recaptchaToken.length < 1000) {
window.postMessage({ type: '__VEO_SUBMIT_RESULT__', requestId, result: {
success: false,
error: 'reCAPTCHA token too short (' + (recaptchaToken ? recaptchaToken.length : 0) + ' chars, need ≥1000)',
tokenLength: recaptchaToken ? recaptchaToken.length : 0
}}, '*');
return;
}
} catch (err) {
window.postMessage({ type: '__VEO_SUBMIT_RESULT__', requestId, result: {
success: false, error: 'reCAPTCHA execute failed: ' + err.message
}}, '*');
return;
}
}
// ── Step 2: Build body ───────────────────────────────────
const body = payload.body || {};
if (needsRecaptcha && recaptchaToken) {
if (!body.clientContext) body.clientContext = {};
body.clientContext.recaptchaContext = {
token: recaptchaToken,
applicationType: 'RECAPTCHA_APPLICATION_TYPE_WEB',
};
}
// ── Step 3: Access token ─────────────────────────────────
let accessToken = null;
const nextDataEl = document.getElementById('__NEXT_DATA__');
if (nextDataEl) {
try {
const data = JSON.parse(nextDataEl.textContent);
const props = data?.props?.pageProps || {};
const session = props.session || {};
accessToken = session.access_token || session.accessToken;
if (!accessToken) {
const user = props.user || {};
accessToken = user.accessToken;
}
} catch (e) { /* ignore */ }
}
// ── Step 4: Fetch from page context ──────────────────────
const headers = { 'Content-Type': 'text/plain;charset=UTF-8' };
if (accessToken) headers['Authorization'] = 'Bearer ' + accessToken;
const controller = new AbortController();
const fetchTimeout = setTimeout(() => controller.abort(), 20000);
try {
const resp = await fetch(endpointUrl, {
method: 'POST',
headers,
credentials: 'include',
body: JSON.stringify(body),
signal: controller.signal,
});
clearTimeout(fetchTimeout);
const responseText = await resp.text();
let responseData = null;
try { responseData = JSON.parse(responseText); }
catch (e) { responseData = { raw: responseText.substring(0, 1000) }; }
window.postMessage({ type: '__VEO_SUBMIT_RESULT__', requestId, result: {
success: resp.ok,
status: resp.status,
statusText: resp.statusText,
data: responseData,
tokenLength: recaptchaToken ? recaptchaToken.length : 0,
}}, '*');
} catch (fetchErr) {
clearTimeout(fetchTimeout);
const errMsg = fetchErr.name === String.fromCharCode(0x41,0x62,0x6f,0x72,0x74,0x45,0x72,0x72,0x6f,0x72)
? 'fetch timeout (20s) — API did not respond'
: 'fetch failed: ' + fetchErr.message;
window.postMessage({ type: '__VEO_SUBMIT_RESULT__', requestId, result: {
success: false,
error: errMsg,
tokenLength: recaptchaToken ? recaptchaToken.length : 0,
}}, '*');
}
} catch (err) {
window.postMessage({ type: '__VEO_SUBMIT_RESULT__', requestId, result: {
success: false, error: String.fromCharCode(0x50,0x61,0x67,0x65,0x20,0x73,0x63,0x72,0x69,0x70,0x74,0x20,0x65,0x72,0x72,0x6f,0x72,0x3a,0x20) + err.message
}}, '*');
}
})();
`;
document.documentElement.appendChild(script);
script.remove();
sendResponse({ ok: true });
return false;
}
return false;
});
function extractAccessToken() {
const el = document.getElementById('__NEXT_DATA__');
if (!el) return { token: null, email: null };
try {
const data = JSON.parse(el.textContent);
const props = data?.props?.pageProps || {};
const session = props.session || {};
let token = session.access_token || session.accessToken;
let email = session.user?.email;
if (!token) {
const user = props.user || {};
token = user.accessToken;
email = email || user.email;
}
return { token: token || null, email: email || null };
} catch (e) {
return { token: null, email: null, error: e.message };
}
}
function performLightweightRefresh() {
try {
fetch('https://labs.google/fx/api/trpc/t2v.generateComposite?batch=1', {
method: 'HEAD',
credentials: 'include',
cache: 'no-store',
}).catch(() => {  });
fetch('https://aisandbox-pa.googleapis.com/$discovery/rest?version=v1&key=AIzaSyDqz9yFaVcD3GreJfBUv2qnTN0Qw0jcXfA', {
method: 'HEAD',
credentials: 'include',
cache: 'no-store',
}).catch(() => { });
} catch (e) {
}
}
if (document.readyState === 'complete') {
detectAndRegister();
} else {
window.addEventListener('load', detectAndRegister);
}
}