/**
 * VEO Pro Max Bridge — Content Script
 *
 * Injected into labs.google.com pages.
 *
 * Responsibilities:
 * 1. Detect logged-in email and register tab with background.js
 * 2. Execute grecaptcha.enterprise.execute() on demand
 * 3. Extract access_token from __NEXT_DATA__
 * 4. Anti-idle simulation (mouse, scroll) to prevent tab discard
 * 5. Heartbeat to background.js for health monitoring
 * 6. reCAPTCHA readiness pre-warm checks
 */

// Guard against double injection (manifest content_scripts + background.js injectExistingTabs)
if (window.__veoContentLoaded) {
    // Already loaded — just re-register in case service worker restarted
    try { detectAndRegister(); } catch (e) { }
} else {
    window.__veoContentLoaded = true;

    // ── Constants ──────────────────────────────────────────────────────────
    // (reCAPTCHA execution moved to background.js via chrome.scripting.executeScript)

    // Maximum retries for email detection (SPA may render late)
    const MAX_EMAIL_RETRIES = 5;
    const EMAIL_RETRY_INTERVAL = 3000; // 3s between retries

    // Anti-idle intervals
    const HEARTBEAT_INTERVAL = 20000;         // 20s — report alive to background
    const MOUSE_SIM_MIN = 30000;              // 30s min between mouse events
    const MOUSE_SIM_MAX = 90000;              // 90s max between mouse events
    const MICRO_SCROLL_MIN = 120000;          // 2 min min between scrolls
    const MICRO_SCROLL_MAX = 300000;          // 5 min max between scrolls
    const RECAPTCHA_WARM_INTERVAL = 60000;    // 60s between reCAPTCHA warmth checks

    // Track registered email for heartbeats
    let _registeredEmail = null;
    let _heartbeatTimer = null;
    let _mouseSimTimer = null;
    let _scrollTimer = null;
    let _recaptchaWarmTimer = null;


    // ── Tab Registration ───────────────────────────────────────────────────

    function detectAndRegister(retryCount = 0) {
        // Quick logout check: if page redirected to Google login, user is logged out
        if (window.location.hostname === 'accounts.google.com' ||
            window.location.href.includes('accounts.google.com/ServiceLogin') ||
            window.location.href.includes('accounts.google.com/signin')) {
            console.warn('[VEO Bridge Content] 🔴 Detected Google login page — user is LOGGED OUT');
            chrome.runtime.sendMessage({ action: 'tab_logout', reason: 'login_redirect' });
            return;
        }

        const email = extractEmail();
        if (email) {
            _registeredEmail = email;
            chrome.runtime.sendMessage({ action: 'register_tab', email });
            console.log(`[VEO Bridge Content] ✅ Registered tab with email: ${email}`);
            // Start anti-idle systems after successful registration
            startAntiIdle();
            return;
        }

        // Log why detection failed (for debugging)
        if (retryCount === 0) {
            console.log('[VEO Bridge Content] ⏳ Email not found yet, retrying...');
            console.log('[VEO Bridge Content]   URL:', window.location.href);
            console.log('[VEO Bridge Content]   __NEXT_DATA__:', !!document.getElementById('__NEXT_DATA__'));
            console.log('[VEO Bridge Content]   [data-email]:', !!document.querySelector('[data-email]'));
            console.log('[VEO Bridge Content]   avatar [aria-label]:', !!document.querySelector('a[aria-label*="@"], [aria-label*="@"]'));
            console.log('[VEO Bridge Content]   img[data-src] (Google profile):', !!document.querySelector('img[data-src*="googleusercontent"]'));
        }

        // Retry with increasing delay (SPA takes time to render)
        if (retryCount < MAX_EMAIL_RETRIES) {
            setTimeout(() => detectAndRegister(retryCount + 1), EMAIL_RETRY_INTERVAL);
        } else {
            console.warn(`[VEO Bridge Content] ❌ Could not detect email after ${MAX_EMAIL_RETRIES} retries on ${window.location.href}`);
            // NOTIFY background.js that this tab appears logged out
            chrome.runtime.sendMessage({
                action: 'tab_logout',
                reason: 'email_not_found',
                url: window.location.href,
            });
            // Still start anti-idle — tab is still a VEO tab
            startAntiIdle();
        }
    }

    function extractEmail() {
        // Method 1: From __NEXT_DATA__ (Next.js pages)
        const nextDataEl = document.getElementById('__NEXT_DATA__');
        if (nextDataEl) {
            try {
                const data = JSON.parse(nextDataEl.textContent);
                const session = data?.props?.pageProps?.session;
                if (session?.user?.email) return session.user.email;
                const user = data?.props?.pageProps?.user;
                if (user?.email) return user.email;
            } catch (e) {
                // ignore parse errors
            }
        }

        // Method 2: From profile avatar/menu (generic Google page pattern)
        const profileEl = document.querySelector('[data-email]');
        if (profileEl) return profileEl.getAttribute('data-email');

        // Method 3: From aria-label on avatar/account button
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

        // Method 4: From Google account switcher / profile image tooltip
        const googleImgs = document.querySelectorAll('img[alt*="@"]');
        for (const img of googleImgs) {
            const alt = img.getAttribute('alt');
            const match = alt.match(/[\w.+-]+@[\w-]+\.[\w.]+/);
            if (match) return match[0];
        }

        // Method 5: Search visible text for email pattern near account elements
        const accountBtns = document.querySelectorAll(
            '[data-ogsr-up], [data-authuser], .gb_Fc, .gb_Oc'
        );
        for (const btn of accountBtns) {
            const text = btn.textContent || btn.innerText || '';
            const match = text.match(/[\w.+-]+@[\w-]+\.[\w.]+/);
            if (match) return match[0];
        }

        // Method 6: Deep scan — look for email in any element with specific classes
        // common in Google apps (account menu, profile)
        const deepSelectors = [
            '.gb_lb',           // Google bar email text
            '[data-identifier]', // Google sign-in identifier
            '.yDmH0d',          // Google account chip
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


    // ── Extract Site Key ───────────────────────────────────────────────────

    function extractSiteKey() {
        // Method 1: From reCAPTCHA script src URL (most reliable)
        for (const s of document.querySelectorAll('script[src*="recaptcha"]')) {
            const m = s.src.match(/render=([^&]+)/);
            if (m && m[1] !== 'explicit') return m[1];
        }

        // Method 2: From ___grecaptcha_cfg internal config
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

        // Method 3: From data-sitekey attribute
        const el = document.querySelector('[data-sitekey]');
        if (el) return el.getAttribute('data-sitekey');

        return null;
    }


    // ── Anti-Idle Simulation ───────────────────────────────────────────────

    function randomBetween(min, max) {
        return Math.floor(Math.random() * (max - min + 1)) + min;
    }

    function startAntiIdle() {
        // 1. Heartbeat to background.js
        if (!_heartbeatTimer) {
            _heartbeatTimer = setInterval(sendHeartbeat, HEARTBEAT_INTERVAL);
            sendHeartbeat(); // First heartbeat immediately
        }

        // 2. Random mouse simulation
        if (!_mouseSimTimer) {
            scheduleMouseSim();
        }

        // 3. Micro-scroll simulation
        if (!_scrollTimer) {
            scheduleMicroScroll();
        }

        // 4. reCAPTCHA warmth check
        if (!_recaptchaWarmTimer) {
            _recaptchaWarmTimer = setInterval(checkRecaptchaWarmth, RECAPTCHA_WARM_INTERVAL);
            // First check after 10s (give page time to load reCAPTCHA)
            setTimeout(checkRecaptchaWarmth, 10000);
        }

        console.log('[VEO Bridge Content] 🏃 Anti-idle systems started');
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
            // Extension context invalidated (reload/update)
            console.debug('[VEO Bridge Content] Heartbeat failed:', e.message);
            stopAntiIdle();
        }
    }

    function scheduleMouseSim() {
        const delay = randomBetween(MOUSE_SIM_MIN, MOUSE_SIM_MAX);
        _mouseSimTimer = setTimeout(() => {
            simulateMouseMove();
            scheduleMouseSim(); // Reschedule with new random delay
        }, delay);
    }

    function simulateMouseMove() {
        // Only simulate when tab is hidden (background) — don't interfere with real user
        if (document.visibilityState === 'visible') return;

        try {
            const x = randomBetween(100, Math.max(window.innerWidth - 100, 200));
            const y = randomBetween(100, Math.max(window.innerHeight - 100, 200));

            const event = new MouseEvent('mousemove', {
                clientX: x,
                clientY: y,
                bubbles: true,
                cancelable: true,
            });
            document.body.dispatchEvent(event);

            // Occasionally also fire a pointermove for modern frameworks
            if (Math.random() < 0.3) {
                const pointerEvent = new PointerEvent('pointermove', {
                    clientX: x + randomBetween(-10, 10),
                    clientY: y + randomBetween(-10, 10),
                    bubbles: true,
                    cancelable: true,
                });
                document.body.dispatchEvent(pointerEvent);
            }
        } catch (e) {
            // Silently ignore — page might have restricted body
        }
    }

    function scheduleMicroScroll() {
        const delay = randomBetween(MICRO_SCROLL_MIN, MICRO_SCROLL_MAX);
        _scrollTimer = setTimeout(() => {
            performMicroScroll();
            scheduleMicroScroll(); // Reschedule
        }, delay);
    }

    function performMicroScroll() {
        // Only when hidden
        if (document.visibilityState === 'visible') return;

        try {
            window.scrollBy({ top: 1, behavior: 'instant' });
            // Scroll back after a tiny delay — invisible to user
            setTimeout(() => {
                try { window.scrollBy({ top: -1, behavior: 'instant' }); } catch (e) { }
            }, 50);
        } catch (e) { }
    }

    function checkRecaptchaWarmth() {
        try {
            const hasGrecaptcha = typeof grecaptcha !== 'undefined';
            const hasEnterprise = hasGrecaptcha && typeof grecaptcha.enterprise !== 'undefined';
            const hasExecute = hasEnterprise && typeof grecaptcha.enterprise.execute === 'function';
            const hasSiteKey = !!extractSiteKey();

            const ready = hasExecute && hasSiteKey;

            // Report to background
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
            // Extension context invalidated
        }
    }

    function stopAntiIdle() {
        if (_heartbeatTimer) { clearInterval(_heartbeatTimer); _heartbeatTimer = null; }
        if (_mouseSimTimer) { clearTimeout(_mouseSimTimer); _mouseSimTimer = null; }
        if (_scrollTimer) { clearTimeout(_scrollTimer); _scrollTimer = null; }
        if (_recaptchaWarmTimer) { clearInterval(_recaptchaWarmTimer); _recaptchaWarmTimer = null; }
    }


    // ── Message Handler ────────────────────────────────────────────────────

    chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
        if (msg.action === 'get_access_token') {
            const result = extractAccessToken();
            sendResponse(result);
            return false; // sync
        }

        // Server can tell us which email this tab belongs to
        if (msg.action === 'assign_email') {
            const email = msg.email;
            if (email) {
                _registeredEmail = email;
                chrome.runtime.sendMessage({ action: 'register_tab', email });
                console.log(`[VEO Bridge Content] ✅ Assigned email from server: ${email}`);
            }
            sendResponse({ ok: true });
            return false;
        }

        // Simulate activity on demand (from Python app via background.js)
        if (msg.action === 'simulate_activity') {
            simulateMouseMove();
            performMicroScroll();
            console.log('[VEO Bridge Content] 🖱️ Activity simulated on demand');
            sendResponse({ ok: true });
            return false;
        }

        // Lightweight header refresh — trigger a small fetch to VEO API
        if (msg.action === 'lightweight_header_refresh') {
            performLightweightRefresh();
            sendResponse({ ok: true });
            return false;
        }

        // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        // submit_prompt — Content script relay for page-context API calls
        //
        // Why relay via content script instead of chrome.scripting.executeScript?
        // MV3 service workers can terminate after 30s, killing pending
        // executeScript promises. Content scripts live as long as the page,
        // making them reliable for long-running async operations.
        //
        // Flow: background.js → content.js → <script> (MAIN world)
        //       → window.postMessage → content.js → background.js
        // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if (msg.action === 'submit_prompt') {
            const requestId = msg.requestId;
            const endpointUrl = msg.endpointUrl;
            const payload = msg.payload || {};
            const needsRecaptcha = msg.needsRecaptcha !== false;

            console.log(
                `[VEO Bridge Content] 🚀 submit_prompt relay: ` +
                `endpoint=${msg.endpoint} needsRecaptcha=${needsRecaptcha}`
            );

            // One-time listener for result from MAIN world script
            const resultHandler = (event) => {
                if (event.source !== window) return;
                if (!event.data || event.data.type !== '__VEO_SUBMIT_RESULT__') return;
                if (event.data.requestId !== requestId) return;

                window.removeEventListener('message', resultHandler);
                console.log(
                    `[VEO Bridge Content] ${event.data.result?.success ? '✅' : '❌'} ` +
                    `submit_prompt result: status=${event.data.result?.status || 'N/A'}`
                );

                // Send result back to background.js
                chrome.runtime.sendMessage({
                    action: 'submit_prompt_relay_result',
                    requestId: requestId,
                    ...event.data.result,
                });
            };
            window.addEventListener('message', resultHandler);

            // Safety timeout: clean up listener after 45s if no result
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

            // Override cleanup on result
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

            // Inject <script> tag into MAIN world
            const script = document.createElement('script');
            script.textContent = `
(async function() {
    const requestId = ${JSON.stringify(requestId)};
    const endpointUrl = ${JSON.stringify(endpointUrl)};
    const payload = ${JSON.stringify(payload)};
    const needsRecaptcha = ${JSON.stringify(needsRecaptcha)};

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
                const recaptchaPromise = grecaptcha.enterprise.execute(siteKey, { action: 'VIDEO_GENERATION' });
                const recaptchaTimeout = new Promise((_, reject) =>
                    setTimeout(() => reject(new Error('reCAPTCHA execute timeout (10s)')), 10000)
                );
                recaptchaToken = await Promise.race([recaptchaPromise, recaptchaTimeout]);
                if (!recaptchaToken || recaptchaToken.length < 500) {
                    window.postMessage({ type: '__VEO_SUBMIT_RESULT__', requestId, result: {
                        success: false,
                        error: 'reCAPTCHA token too short (' + (recaptchaToken ? recaptchaToken.length : 0) + ' chars)',
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
            const errMsg = fetchErr.name === 'AbortError'
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
            success: false, error: 'Page script error: ' + err.message
        }}, '*');
    }
})();
`;
            document.documentElement.appendChild(script);
            script.remove(); // Clean up — script has already executed

            sendResponse({ ok: true }); // Ack to background.js
            return false; // sync response
        }

        return false;
    });

    // reCAPTCHA execution is now handled by background.js via chrome.scripting.executeScript
    // with world: 'MAIN', bypassing CSP and isolated world restrictions.

    function extractAccessToken() {
        const el = document.getElementById('__NEXT_DATA__');
        if (!el) return { token: null, email: null };

        try {
            const data = JSON.parse(el.textContent);
            const props = data?.props?.pageProps || {};

            // Try session.access_token
            const session = props.session || {};
            let token = session.access_token || session.accessToken;
            let email = session.user?.email;

            // Fallback: props.user.accessToken
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


    // ── Lightweight Header Refresh ──────────────────────────────────────────
    // Trigger a small fetch to VEO API which causes onBeforeSendHeaders to fire
    // and capture fresh headers WITHOUT reloading the entire page.

    function performLightweightRefresh() {
        try {
            // Fetch a lightweight VEO API endpoint that triggers header attachment
            // The fetch itself will fail or succeed — doesn't matter, we just need
            // onBeforeSendHeaders to fire in background.js
            fetch('https://labs.google/fx/api/trpc/t2v.generateComposite?batch=1', {
                method: 'HEAD',
                credentials: 'include',  // Include cookies → triggers auth headers
                cache: 'no-store',
            }).catch(() => { /* Expected — we don't care about the response */ });

            // Also try aisandbox API
            fetch('https://aisandbox-pa.googleapis.com/$discovery/rest?version=v1&key=AIzaSyDqz9yFaVcD3GreJfBUv2qnTN0Qw0jcXfA', {
                method: 'HEAD',
                credentials: 'include',
                cache: 'no-store',
            }).catch(() => { });

            console.log('[VEO Bridge Content] 🔄 Lightweight header refresh triggered');
        } catch (e) {
            console.debug('[VEO Bridge Content] Lightweight refresh failed:', e.message);
        }
    }


    // ── Init ────────────────────────────────────────────────────────────────

    // Wait for page to be fully loaded before registering
    if (document.readyState === 'complete') {
        detectAndRegister();
    } else {
        window.addEventListener('load', detectAndRegister);
    }

    console.log('[VEO Bridge Content] Content script loaded on', window.location.hostname);

} // end of double-injection guard
