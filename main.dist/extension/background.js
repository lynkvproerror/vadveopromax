/* VEO Pro Max Extension v2.2.2 - Protected */
const EXT_VERSION = chrome.runtime.getManifest().version;
const MAX_TABS = 3;
let wsConnected = false;
const tabState = {};
let _tabStateRestored = false;
let _wsSendQueue = [];
let _persistTimer = null;
function persistTabState() {
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
};
}
chrome.storage.session.set({ tabState: serializable }).catch(() => { });
}, 1000);
}
async function restoreTabState() {
try {
const result = await chrome.storage.session.get('tabState');
if (result.tabState && Object.keys(result.tabState).length > 0) {
for (const [tabId, state] of Object.entries(result.tabState)) {
try {
const tab = await chrome.tabs.get(parseInt(tabId));
if (tab) {
tabState[tabId] = state;
}
} catch (_) {
}
}
if (Object.keys(tabState).length > 0) {
return;
}
}
} catch (e) {
}
try {
const tabs = await chrome.tabs.query({ url: '*://labs.google/*' });
for (const tab of tabs) {
if (!tabState[tab.id]) {
tabState[tab.id] = {
email: null, headers: {}, accessToken: null,
lastHeartbeat: 0, recaptchaReady: false,
};
}
}
if (tabs.length > 0) {
}
} catch (e) {
}
}
let globalBrowserValidation = null;
const BROWSER_HEADERS = [
'x-browser-channel',
'x-browser-copyright',
'x-browser-year',
'x-browser-validation',
'x-client-data',
];
const pendingRecaptcha = {};
const shortTokenCounts = {};
const SHORT_TOKEN_RELOAD_THRESHOLD = 3;
const _headersDebounceTimers = {};
const HEADERS_DEBOUNCE_MS = 2000;
const HEARTBEAT_TIMEOUT = 45000;
const FROZEN_RELOAD_MAX = 3;
const FROZEN_RELOAD_WINDOW = 300000;
let _heartbeatCheckTimer = null;
const RELOAD_COOLDOWN_MS = 20000;
const tabLastReloadTime = {};
async function safeTabReload(tabId, reason, bypassCache = false) {
const now = Date.now();
const lastReload = tabLastReloadTime[tabId] || 0;
const elapsed = now - lastReload;
if (elapsed < RELOAD_COOLDOWN_MS) {
return false;
}
try {
await chrome.tabs.reload(tabId, { bypassCache });
tabLastReloadTime[tabId] = now;
return true;
} catch (e) {
return false;
}
}
let _offscreenCreating = null;
async function ensureOffscreenDocument() {
const existingContexts = await chrome.runtime.getContexts({
contextTypes: ['OFFSCREEN_DOCUMENT'],
documentUrls: [chrome.runtime.getURL('offscreen.html')],
});
if (existingContexts.length > 0) {
return;
}
if (_offscreenCreating) {
await _offscreenCreating;
return;
}
for (let attempt = 1; attempt <= 3; attempt++) {
_offscreenCreating = chrome.offscreen.createDocument({
url: 'offscreen.html',
reasons: ['WORKERS'],
justification: 'Persistent WebSocket connection to Python app',
});
try {
await _offscreenCreating;
_offscreenCreating = null;
return;
} catch (e) {
_offscreenCreating = null;
if (attempt < 3) {
await new Promise(r => setTimeout(r, 2000));
} else {
console.error(`[VEO Bridge] ❌ Offscreen creation failed after 3 attempts: ${e.message}`);
}
}
}
}
function wsSend(data) {
if (!wsConnected) {
if (_wsSendQueue.length < 50) {
_wsSendQueue.push(data);
}
return false;
}
chrome.runtime.sendMessage({
type: 'offscreen_ws_send',
data: data,
}).catch(() => {
if (_wsSendQueue.length < 50) {
_wsSendQueue.push(data);
}
});
return true;
}
async function onWsConnected() {
if (!_tabStateRestored) {
const start = Date.now();
while (!_tabStateRestored && Date.now() - start < 2000) {
await new Promise(r => setTimeout(r, 100));
}
if (!_tabStateRestored) {
}
}
if (_wsSendQueue.length > 0) {
const queue = [..._wsSendQueue];
_wsSendQueue = [];
for (const msg of queue) {
wsSend(msg);
}
}
for (const [tabId, state] of Object.entries(tabState)) {
if (state.email) {
wsSend({
action: 'register',
email: state.email,
tabId: parseInt(tabId),
version: EXT_VERSION,
});
if (Object.keys(state.headers).length > 0) {
wsSend({
action: 'headers_update',
email: state.email,
headers: state.headers,
accessToken: state.accessToken,
});
}
extractAndPushToken(parseInt(tabId), state.email);
}
}
}
async function handleAppMessage(msg) {
switch (msg.action) {
case 'request_recaptcha': {
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
const scriptPromise = chrome.scripting.executeScript({
target: { tabId },
world: 'MAIN',
func: async (siteKey) => {
if (typeof grecaptcha === 'undefined' ||
typeof grecaptcha.enterprise === 'undefined' ||
typeof grecaptcha.enterprise.execute !== 'function') {
return { token: null, error: 'reCAPTCHA Enterprise not available on page' };
}
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
const timeoutPromise = new Promise((_, reject) =>
setTimeout(() => reject(new Error('reCAPTCHA execute timeout (15s) — widget may be frozen')), 15000)
);
const results = await Promise.race([scriptPromise, timeoutPromise]);
const result = results?.[0]?.result;
if (result?.error?.includes('too short')) {
shortTokenCounts[tabId] = (shortTokenCounts[tabId] || 0) + 1;
if (shortTokenCounts[tabId] >= SHORT_TOKEN_RELOAD_THRESHOLD) {
shortTokenCounts[tabId] = 0;
const reloaded = await safeTabReload(tabId, 'short-token-threshold', true);
if (reloaded) {
await new Promise(r => setTimeout(r, 5000));
}
}
} else if (result?.token) {
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
const tabId = findTabForEmail(msg.email);
if (tabId) {
try {
await chrome.tabs.sendMessage(tabId, { action: 'simulate_activity' });
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
const reason = msg.reason || 'version mismatch';
const targetVer = msg.target_version || 'unknown';
setTimeout(() => {
chrome.runtime.reload();
}, 1000);
break;
}
case 'assign_email': {
const email = msg.email;
if (!email) break;
let existingTabId = findTabForEmail(email);
if (existingTabId) {
wsSend({ action: 'register', email, tabId: existingTabId, version: EXT_VERSION });
break;
}
const veoTabs = await chrome.tabs.query({ url: '*://labs.google/*' });
if (veoTabs.length > 0) {
let targetTab = veoTabs.find(t => !tabState[t.id]?.email) || veoTabs[0];
const tabId = targetTab.id;
if (!tabState[tabId]) {
tabState[tabId] = { email: null, headers: {}, accessToken: null, lastHeartbeat: 0, recaptchaReady: false };
}
tabState[tabId].email = email;
wsSend({ action: 'register', email, tabId, version: EXT_VERSION });
} else {
const allTabs = await chrome.tabs.query({ currentWindow: true });
if (allTabs.length >= MAX_TABS) {
wsSend({
action: 'register',
email,
tabId: null,
version: EXT_VERSION,
error: `Tab limit reached (${MAX_TABS})`,
});
} else {
const newTab = await chrome.tabs.create({
url: VEO_URL,
active: false,
pinned: true,
});
tabState[newTab.id] = { email, headers: {}, accessToken: null, lastHeartbeat: 0, recaptchaReady: false };
wsSend({ action: 'register', email, tabId: newTab.id, version: EXT_VERSION });
try { chrome.tabs.update(newTab.id, { autoDiscardable: false }); } catch (_) { }
startZombieTimer(newTab.id);
}
}
break;
}
case 'reload_extension': {
wsSend({
action: 'extension_reloading',
requestId: msg.requestId || '',
});
setTimeout(() => {
chrome.runtime.reload();
}, 500);
break;
}
case 'check_recaptcha_ready': {
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
const scriptPromise = chrome.scripting.executeScript({
target: { tabId },
world: 'MAIN',
func: async () => {
const hasGrecaptcha = typeof grecaptcha !== 'undefined';
const hasEnterprise = hasGrecaptcha && typeof grecaptcha.enterprise !== 'undefined';
const hasExecute = hasEnterprise && typeof grecaptcha.enterprise.execute === 'function';
const pageLoaded = document.readyState === 'complete';
const hasRecaptchaScript = !!document.querySelector('script[src*="recaptcha"]');
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
trialAction,
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
const keepaliveTimer = setInterval(() => {
chrome.runtime.getPlatformInfo(() => { });
}, 25000);
try {
const ENDPOINTS = {
T2V: 'https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoText',
I2V_SINGLE: 'https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoStartImage',
I2V_DUAL: 'https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoStartAndEndImage',
R2V: 'https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoReferenceImages',
STATUS: 'https://aisandbox-pa.googleapis.com/v1/video:batchCheckAsyncVideoGenerationStatus',
UPSCALE_VIDEO: 'https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoUpsampleVideo',
UPLOAD: 'https://aisandbox-pa.googleapis.com/v1:uploadUserImage',
UPSCALE_IMAGE: 'https://aisandbox-pa.googleapis.com/v1/flow/upsampleImage',
};
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
const scriptPromise = chrome.scripting.executeScript({
target: { tabId },
world: 'MAIN',
func: async (endpointUrl, payload, needsRecaptcha, cachedAccessToken, endpointKey) => {
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
let recaptchaToken = null;
if (needsRecaptcha) {
try {
const imageEndpoints = ['T2I', 'UPSCALE_IMAGE'];
const rcAction = imageEndpoints.includes(endpointKey) ? 'IMAGE_GENERATION' : 'VIDEO_GENERATION';
const rcPromise = grecaptcha.enterprise.execute(siteKey, { action: rcAction });
const rcTimeout = new Promise((_, reject) =>
setTimeout(() => reject(new Error('reCAPTCHA execute timeout (10s)')), 10000)
);
recaptchaToken = await Promise.race([rcPromise, rcTimeout]);
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
const body = payload.body || {};
if (needsRecaptcha && recaptchaToken) {
const rcCtx = {
token: recaptchaToken,
applicationType: 'RECAPTCHA_APPLICATION_TYPE_WEB',
};
if (!body.clientContext) body.clientContext = {};
body.clientContext.recaptchaContext = rcCtx;
if (Array.isArray(body.requests)) {
for (const req of body.requests) {
if (req.clientContext) {
req.clientContext.recaptchaContext = rcCtx;
}
}
}
}
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
} catch (e) {  }
}
}
const headers = { 'Content-Type': 'text/plain;charset=UTF-8' };
if (authHeaderValue) {
headers['Authorization'] = authHeaderValue;
}
const controller = new AbortController();
const fetchTimeout = ['T2I', 'I2I', 'UPSCALE_IMAGE'].includes(endpointKey) ? 90000 : 20000;
const fetchTimer = setTimeout(() => controller.abort(), fetchTimeout);
try {
const bodyStr = JSON.stringify(body);
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
const errMsg = fetchErr.name === String.fromCharCode(0x41,0x62,0x6f,0x72,0x74,0x45,0x72,0x72,0x6f,0x72)
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
msg.needsRecaptcha !== false,
tabState[tabId]?.accessToken || null,
msg.endpoint || '',
],
});
const scriptTimeout = ['T2I', 'I2I', 'UPSCALE_IMAGE'].includes(msg.endpoint) ? 120000 : 30000;
const timeoutPromise = new Promise((_, reject) =>
setTimeout(() => reject(new Error(`submit_prompt timeout (${scriptTimeout / 1000}s)`)), scriptTimeout)
);
const results = await Promise.race([scriptPromise, timeoutPromise]);
const result = results?.[0]?.result || {};
let trimmedResult = { ...result };
if (result.data) {
const dataStr = JSON.stringify(result.data);
if (dataStr.length > 50000 && msg.endpoint !== 'UPSCALE_IMAGE') {
const strip = (obj) => {
if (!obj || typeof obj !== 'object') return obj;
if (Array.isArray(obj)) return obj.map(strip);
const out = {};
for (const [k, v] of Object.entries(obj)) {
if (k === 'encodedVideo' || k === 'encodedImage') continue;
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
case 'relay_fetch': {
const tabId = findTabForEmail(msg.email);
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
const requestUrl = msg.url || '';
if (requestUrl.includes('labs.google')) {
try {
const tab = await chrome.tabs.get(tabId);
if (tab && tab.url && !tab.url.includes('labs.google')) {
await chrome.tabs.update(tabId, { url: VEO_URL });
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
await new Promise(r => setTimeout(r, 2000));
}
} catch (navErr) {
}
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
if (credentials) fetchOpts.credentials = credentials;
if (headers && Object.keys(headers).length > 0) {
fetchOpts.headers = headers;
} else {
fetchOpts.headers = { 'Content-Type': 'application/json' };
}
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
await chrome.tabs.update(tabId, { url: targetUrl });
await new Promise(r => setTimeout(r, 1500));
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
}
await new Promise(r => setTimeout(r, 500));
}
const loadTime = ((Date.now() - startTime) / 1000).toFixed(1);
if (loadComplete) {
} else {
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
await chrome.tabs.reload(tabId);
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
wsSend({
action: 'reload_tab_result',
requestId: msg.requestId,
success: true,
});
} catch (e) {
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
wsSend({
action: 'extension_reloaded',
requestId: msg.requestId || null,
success: true,
});
setTimeout(() => {
chrome.runtime.reload();
}, 200);
break;
}
case 'ping':
wsSend({ action: 'pong' });
break;
case 'probe_browser_headers': {
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
const results = await chrome.scripting.executeScript({
target: { tabId },
world: 'MAIN',
func: async (apiKey) => {
try {
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
return { triggered: true, error: e.message };
}
},
args: [msg.apiKey || 'AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY'],
});
const result = results?.[0]?.result;
await new Promise(r => setTimeout(r, 500));
const state = tabState[tabId];
const currentHeaders = state ? { ...state.headers } : {};
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
case 'provision_gemini_key': {
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
const phase1Fn = async (RPC, KEY, sapisidValue) => {
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
return { error: "no_project", needs_navigate: true };
}
r = await fetch(RPC + "/ListCloudApiKeys", {
method: "POST", credentials: "include", headers: H,
body: JSON.stringify([100, null, 1, [projectRef]])
});
if (!r.ok) return { error: "list_keys_http_" + r.status };
let keys = await r.json();
const keysFlat = JSON.stringify(keys);
const km = keysFlat.match(/AIza[\w-]{35}/);
if (km) return { key: km[0], source: "existing" };
if (!projectId) return { error: "no_project_id" };
r = await fetch(RPC + "/GenerateCloudApiKey", {
method: "POST", credentials: "include", headers: H,
body: JSON.stringify([projectId, null, null, "GEMINI API AUTO"])
});
if (!r.ok) return { error: "gen_key_http_" + r.status };
let newKey = await r.json();
const nkm = JSON.stringify(newKey).match(/AIza[\w-]{35}/);
if (nkm) return { key: nkm[0], source: "created" };
return { error: "create_failed", needs_navigate: true };
} catch (e) {
return { error: e.message };
}
};
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
if (result?.needs_navigate) {
const origUrl = (await chrome.tabs.get(parseInt(tabId))).url;
await chrome.tabs.update(parseInt(tabId), { url: 'https://aistudio.google.com/api-keys' });
await new Promise(r => setTimeout(r, 6000));
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
chrome.tabs.update(parseInt(tabId), { url: origUrl || 'https://labs.google/fx/vi/tools/flow' });
}, 1000);
}
// ── Send result ──
if (result?.key) {
wsSend({
action: 'provision_gemini_key_result',
requestId, email, success: true,
key: result.key, source: result.source,
});
} else {
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
if (name === 'authorization' && h.value && h.value.startsWith('Bearer ')) {
authHeader = h.value;
}
}
if (headers['x-browser-validation']) {
globalBrowserValidation = headers['x-browser-validation'];
}
if (details.tabId < 0) return;
if (!tabState[details.tabId]) return;
if (Object.keys(headers).length === 0 && !authHeader) return;
const state = tabState[details.tabId];
Object.assign(state.headers, headers);
if (globalBrowserValidation && !state.headers['x-browser-validation']) {
state.headers['x-browser-validation'] = globalBrowserValidation;
}
if (authHeader) {
state.accessToken = authHeader;
}
if (state.email && Object.keys(headers).length > 0) {
const email = state.email;
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
'*://*.googleapis.com/*',
'*://*.aisandbox.com/*',
'*://labs.google/*',
],
},
['requestHeaders', 'extraHeaders']
);
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
if (msg.type === 'offscreen_ws_state') {
const wasConnected = wsConnected;
wsConnected = msg.connected;
if (msg.connected && !wasConnected) {
onWsConnected();
} else if (!msg.connected && wasConnected) {
}
sendResponse({ ok: true });
return false;
}
if (msg.type === 'offscreen_ws_incoming') {
handleAppMessage(msg.data).catch(e => {
console.error(String.fromCharCode(0x5b,0x56,0x45,0x4f,0x20,0x42,0x72,0x69,0x64,0x67,0x65,0x5d,0x20,0x41,0x73,0x79,0x6e,0x63,0x20,0x68,0x61,0x6e,0x64,0x6c,0x65,0x72,0x20,0x65,0x72,0x72,0x6f,0x72,0x3a), e.message || e);
});
sendResponse({ ok: true });
return false;
}
return undefined;
});
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
if (msg.action === 'register_tab' && sender.tab) {
const tabId = sender.tab.id;
if (!tabState[tabId]) {
tabState[tabId] = { email: null, headers: {}, accessToken: null, lastHeartbeat: 0, recaptchaReady: false };
}
tabState[tabId].email = msg.email;
tabState[tabId].lastHeartbeat = Date.now();
persistTabState();
if (tabState[tabId]._zombieTimer) {
clearTimeout(tabState[tabId]._zombieTimer);
delete tabState[tabId]._zombieTimer;
}
try {
chrome.tabs.update(tabId, { autoDiscardable: false });
} catch (e) {
}
wsSend({
action: 'register',
email: msg.email,
tabId: tabId,
version: EXT_VERSION,
});
sendResponse({ ok: true });
}
if (msg.action === 'content_heartbeat' && sender.tab) {
const tabId = sender.tab.id;
const state = tabState[tabId];
if (state) {
state.lastHeartbeat = Date.now();
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
if (msg.action === 'recaptcha_warmth' && sender.tab) {
const tabId = sender.tab.id;
const state = tabState[tabId];
if (state) {
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
return true;
}
sendResponse({ ok: true });
}
if (msg.action === String.fromCharCode(0x74,0x61,0x62,0x5f,0x6c,0x6f,0x67,0x6f,0x75,0x74) && sender.tab) {
const tabId = sender.tab.id;
const state = tabState[tabId];
const email = state?.email;
if (email) {
wsSend({
action: 'account_logged_out',
email: email,
reason: msg.reason || 'unknown',
tabId: tabId,
});
delete tabState[tabId];
}
sendResponse({ ok: true });
}
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
return false;
});
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
const state = tabState[tabId];
if (!state) return;
if (changeInfo.discarded === true && state.email) {
wsSend({ action: 'tab_discarded', email: state.email, tabId });
setTimeout(() => {
safeTabReload(tabId, 'memory-saver-discard');
}, 1000);
return;
}
if (changeInfo.discarded === false && changeInfo.status === 'complete' && state.email) {
chrome.scripting.executeScript({
target: { tabId }, files: ['content.js'],
}).catch(() => { });
return;
}
if (!changeInfo.url) return;
if (changeInfo.url.includes('accounts.google.com')) {
const email = state.email;
if (email) {
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
chrome.tabs.onRemoved.addListener(async (tabId, removeInfo) => {
const state = tabState[tabId];
if (!state || !state.email) {
delete tabState[tabId];
delete tabLastReloadTime[tabId];
return;
}
const orphanedEmail = state.email;
delete tabState[tabId];
delete tabLastReloadTime[tabId];
delete shortTokenCounts[tabId];
wsSend({
action: 'tab_closed',
email: orphanedEmail,
tabId: tabId,
});
const existingTabId = findTabForEmail(orphanedEmail);
if (existingTabId) {
wsSend({ action: 'register', email: orphanedEmail, tabId: existingTabId, version: EXT_VERSION });
return;
}
try {
const veoTabs = await chrome.tabs.query({ url: '*://labs.google/*' });
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
try {
await chrome.scripting.executeScript({
target: { tabId: newTabId },
files: ['content.js'],
});
} catch (e) {
}
wsSend({ action: 'register', email: orphanedEmail, tabId: newTabId, version: EXT_VERSION });
try { chrome.tabs.update(newTabId, { autoDiscardable: false }); } catch (_) { }
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
if (!state._frozenReloadCount) state._frozenReloadCount = 0;
if (!state._frozenWindowStart) state._frozenWindowStart = now;
if (now - state._frozenWindowStart > FROZEN_RELOAD_WINDOW) {
state._frozenReloadCount = 0;
state._frozenWindowStart = now;
}
state._frozenReloadCount++;
if (state._frozenReloadCount > FROZEN_RELOAD_MAX) {
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
continue;
}
wsSend({
action: 'tab_frozen',
email: state.email,
tabId: parseInt(tabId),
lastHeartbeat: state.lastHeartbeat,
elapsedMs: elapsed,
reloadAttempt: state._frozenReloadCount,
});
safeTabReload(parseInt(tabId), `heartbeat-frozen-attempt-${state._frozenReloadCount}`).then(didReload => {
if (didReload) {
state.lastHeartbeat = now;
}
});
}
}
}
if (!_heartbeatCheckTimer) {
_heartbeatCheckTimer = setInterval(checkHeartbeats, 20000);
}
function startZombieTimer(tabId) {
if (!tabState[tabId]) return;
tabState[tabId]._zombieTimer = setTimeout(() => {
const state = tabState[tabId];
if (state && !state.email) {
wsSend({
action: 'zombie_tab',
tabId: tabId,
message: 'Tab created but no email detected after 30 seconds',
});
}
}, 30000);
}
chrome.tabs.onRemoved.addListener((tabId) => {
if (tabState[tabId]) {
const email = tabState[tabId].email;
const wasVeoTab = !!email;
delete tabState[tabId];
if (email) {
wsSend({ action: 'tab_closed', email, tabId });
}
if (wasVeoTab) {
const otherVeoTabs = Object.entries(tabState).filter(([_, s]) => s.email);
if (otherVeoTabs.length === 0) {
setTimeout(() => ensureVeoTab(), 2000);
} else {
}
}
}
});
chrome.tabs.onCreated.addListener((tab) => {
setTimeout(() => {
closeExcessTabs().then(() => ensureVeoTab());
}, 3000);
});
function findTabForEmail(email) {
for (const [tabId, state] of Object.entries(tabState)) {
if (state.email === email) {
return parseInt(tabId);
}
}
return null;
}
async function extractAndPushToken(tabId, email) {
try {
const response = await chrome.tabs.sendMessage(tabId, {
action: 'get_access_token',
});
if (response?.token) {
wsSend({
action: 'access_token',
requestId: null,
email: email,
token: response.token,
tokenEmail: response.email || null,
});
}
} catch (e) {
}
}
const KEEPALIVE_ALARM = 'ws-keepalive';
const HEADER_REFRESH_ALARM = 'header-refresh';
const TAB_CLEANUP_ALARM = 'tab-cleanup';
chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: 0.33 });
chrome.alarms.create(HEADER_REFRESH_ALARM, { periodInMinutes: 3 });
chrome.alarms.create(TAB_CLEANUP_ALARM, { periodInMinutes: 2 });
chrome.alarms.onAlarm.addListener((alarm) => {
if (alarm.name === KEEPALIVE_ALARM) {
ensureOffscreenDocument();
}
if (alarm.name === HEADER_REFRESH_ALARM) {
lightweightRefreshAll();
}
if (alarm.name === TAB_CLEANUP_ALARM) {
closeExcessTabs().then(() => ensureVeoTab());
}
});
async function lightweightRefreshAll() {
for (const [tabId, state] of Object.entries(tabState)) {
if (!state.email) continue;
try {
await chrome.tabs.sendMessage(parseInt(tabId), { action: 'lightweight_header_refresh' });
} catch (e) {
try {
await chrome.tabs.reload(parseInt(tabId), { bypassCache: false });
} catch (re) {
}
}
}
}
async function reloadVeoTabs(email = null) {
try {
const tabs = await chrome.tabs.query({ url: '*://labs.google/*' });
let reloaded = 0;
for (const tab of tabs) {
if (email) {
const state = tabState[tab.id];
if (state && state.email !== email) continue;
}
try {
const didReload = await safeTabReload(tab.id, 'header-refresh');
if (didReload) reloaded++;
} catch (e) {
}
}
return reloaded;
} catch (e) {
console.error('[VEO Bridge] Failed to reload VEO tabs:', e);
return 0;
}
}
async function injectExistingTabs() {
try {
const tabs = await chrome.tabs.query({ url: '*://labs.google/*' });
for (const tab of tabs) {
try {
await chrome.scripting.executeScript({
target: { tabId: tab.id },
files: ['content.js'],
});
if (!tab.pinned) {
chrome.tabs.update(tab.id, { pinned: true });
}
setTimeout(() => {
chrome.tabs.reload(tab.id, { bypassCache: false });
}, 1000);
} catch (e) {
}
}
} catch (e) {
console.error('[VEO Bridge] Failed to query tabs:', e);
}
}
const VEO_URL = 'https://labs.google/fx/vi/tools/flow';
let _ensureVeoTabRunning = false;
async function ensureVeoTab() {
if (_ensureVeoTabRunning) return;
_ensureVeoTabRunning = true;
try {
const existing = await chrome.tabs.query({ url: '*://labs.google/*' });
if (existing.length > 0) {
for (const tab of existing) {
if (!tab.pinned) {
try {
await chrome.tabs.update(tab.id, { pinned: true });
} catch (e) {
}
}
}
return;
}
const trackedVeoTabs = Object.entries(tabState).filter(([_, s]) => s.email);
if (trackedVeoTabs.length > 0) {
return;
}
let allTabs = await chrome.tabs.query({ currentWindow: true });
if (allTabs.length >= MAX_TABS) {
await closeExcessTabs();
allTabs = await chrome.tabs.query({ currentWindow: true });
if (allTabs.length >= MAX_TABS) {
const nonVeo = allTabs.filter(t => !(t.url || '').includes('labs.google'));
if (nonVeo.length > 0) {
const victim = nonVeo[nonVeo.length - 1];
try {
await chrome.tabs.remove(victim.id);
if (tabState[victim.id]) delete tabState[victim.id];
} catch (e) {
}
} else {
return;
}
}
}
const tab = await chrome.tabs.create({
url: VEO_URL,
active: false,
pinned: true,
});
startZombieTimer(tab.id);
setTimeout(async () => {
try {
await chrome.scripting.executeScript({
target: { tabId: tab.id },
files: ['content.js'],
});
} catch (e) {
}
}, 5000);
} catch (e) {
console.error('[VEO Bridge] ensureVeoTab failed:', e);
} finally {
_ensureVeoTabRunning = false;
}
}
chrome.runtime.onInstalled.addListener(async () => {
chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: 0.33 });
try {
try { await chrome.scripting.unregisterContentScripts({ ids: ['stealth'] }); } catch (_) { }
await chrome.scripting.registerContentScripts([{
id: 'stealth',
matches: ['*://labs.google/*'],
js: ['stealth.js'],
runAt: 'document_start',
world: 'MAIN',
}]);
} catch (e) {
}
await ensureOffscreenDocument();
injectExistingTabs().then(() => {
closeExcessTabs();
ensureVeoTab();
});
});
restoreTabState().then(() => {
_tabStateRestored = true;
ensureOffscreenDocument();
injectExistingTabs().then(() => {
closeExcessTabs();
ensureVeoTab();
});
}).catch(() => {
_tabStateRestored = true;
ensureOffscreenDocument();
});
setInterval(async () => {
try {
const contexts = await chrome.runtime.getContexts({
contextTypes: ['OFFSCREEN_DOCUMENT'],
documentUrls: [chrome.runtime.getURL('offscreen.html')],
});
if (contexts.length === 0) {
wsConnected = false;
await ensureOffscreenDocument();
}
} catch (e) {
}
}, 15000);
const ALLOWED_URL_FRAGMENTS = [
'mail.google.com',
'youtube.com',
'labs.google',
];
async function closeExcessTabs() {
try {
const allTabs = await chrome.tabs.query({ currentWindow: true });
if (allTabs.length <= MAX_TABS) return 0;
const veoTabs = [];
const otherAllowed = [];
const blank = [];
const other = [];
for (const tab of allTabs) {
const url = tab.url || '';
if (url === 'about:blank' || url === 'chrome://newtab/' || url === '') {
blank.push(tab);
} else if (url.includes('labs.google')) {
veoTabs.push(tab);
} else if (ALLOWED_URL_FRAGMENTS.some(frag => url.includes(frag))) {
otherAllowed.push(tab);
} else {
other.push(tab);
}
}
const maxCloseable = allTabs.length - MAX_TABS;
const candidates = [...blank, ...other, ...otherAllowed];
const toClose = candidates.slice(0, maxCloseable);
while (toClose.length > 0 && allTabs.length - toClose.length < 1) {
toClose.pop();
}
let closed = 0;
for (const tab of toClose) {
try {
await chrome.tabs.remove(tab.id);
if (tabState[tab.id]) {
delete tabState[tab.id];
}
closed++;
} catch (e) {
}
}
if (closed > 0) {
}
return closed;
} catch (e) {
console.error('[VEO Bridge] closeExcessTabs failed:', e);
return 0;
}
}