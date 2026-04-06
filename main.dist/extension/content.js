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
    // VEO SPA on labs.google/fx/ can take 20-40s to render __NEXT_DATA__
    const MAX_EMAIL_RETRIES = 12;
    const EMAIL_RETRY_INTERVAL = 3000; // 3s between retries → 36s total

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
    let _emailObserver = null;  // MutationObserver for __NEXT_DATA__ fallback


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
            // Clean up observer if it was started
            if (_emailObserver) { _emailObserver.disconnect(); _emailObserver = null; }
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
            console.warn(`[VEO Bridge Content] ⏳ Could not detect email after ${MAX_EMAIL_RETRIES} retries — starting MutationObserver fallback`);
            // DO NOT send tab_logout here — the SPA may still render the email.
            // False tab_logout poisons Gemini key provision for hot-added accounts.
            // Instead, start a MutationObserver that watches for __NEXT_DATA__ to appear.
            startEmailObserver();
            // Still start anti-idle — tab is still a VEO tab
            startAntiIdle();
        }
    }

    /**
     * MutationObserver fallback: watches for __NEXT_DATA__ script tag or
     * any [data-email] / aria-label changes that indicate email is available.
     * Auto-disconnects after 120s or on success.
     */
    function startEmailObserver() {
        if (_emailObserver) return; // Already watching

        const startTime = Date.now();
        const MAX_OBSERVE_MS = 120000; // 2 minutes max

        _emailObserver = new MutationObserver(() => {
            // Check timeout
            if (Date.now() - startTime > MAX_OBSERVE_MS) {
                console.warn('[VEO Bridge Content] ⏰ MutationObserver timeout (2min) — giving up email detection');
                _emailObserver.disconnect();
                _emailObserver = null;
                return;
            }

            const email = extractEmail();
            if (email) {
                _registeredEmail = email;
                chrome.runtime.sendMessage({ action: 'register_tab', email });
                console.log(`[VEO Bridge Content] ✅ Registered tab via MutationObserver: ${email}`);
                _emailObserver.disconnect();
                _emailObserver = null;
            }
        });

        _emailObserver.observe(document.documentElement, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['data-email', 'aria-label'],
        });
        console.log('[VEO Bridge Content] 👁️ MutationObserver watching for email...');
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


    // ── Anti-Idle Core ─────────────────────────────────────────────────────

    function randomBetween(min, max) {
        return Math.floor(Math.random() * (max - min + 1)) + min;
    }

    function startAntiIdle() {
        // 1. Heartbeat to background.js
        if (!_heartbeatTimer) {
            _heartbeatTimer = setInterval(sendHeartbeat, HEARTBEAT_INTERVAL);
            sendHeartbeat(); // First heartbeat immediately
        }

        // 2. Human-like mouse simulation
        if (!_mouseSimTimer) {
            scheduleMouseSim();
        }

        // 3. Human-like micro-scroll simulation
        if (!_scrollTimer) {
            scheduleMicroScroll();
        }

        // 4. reCAPTCHA warmth check
        if (!_recaptchaWarmTimer) {
            _recaptchaWarmTimer = setInterval(checkRecaptchaWarmth, RECAPTCHA_WARM_INTERVAL);
            // First check after 10s (give page time to load reCAPTCHA)
            setTimeout(checkRecaptchaWarmth, 10000);
        }

        console.log('[VEO Bridge Content] 🏃 Anti-idle systems started (human-like mode)');
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

    function scheduleMicroScroll() {
        const delay = randomBetween(MICRO_SCROLL_MIN, MICRO_SCROLL_MAX);
        _scrollTimer = setTimeout(() => {
            performMicroScroll();
            scheduleMicroScroll(); // Reschedule
        }, delay);
    }


    // ── Human-Like Activity Simulation ──────────────────────────────────────
    // Bezier curve mouse paths, acceleration/deceleration, micro-interactions

    // Persistent cursor position (remembered between simulations)
    let _lastMouseX = null;
    let _lastMouseY = null;

    /**
     * Cubic Bezier interpolation for smooth mouse paths.
     * P0 = start, P1/P2 = control points, P3 = end.
     */
    function cubicBezier(t, p0, p1, p2, p3) {
        const u = 1 - t;
        return u * u * u * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t * p3;
    }

    /**
     * Ease-in-out-cubic: mimics human acceleration → deceleration.
     * Fast in the middle, slow at start/end (like real hand movements).
     */
    function easeInOutCubic(t) {
        return t < 0.5
            ? 4 * t * t * t
            : 1 - Math.pow(-2 * t + 2, 3) / 2;
    }

    /**
     * Generate a human-like Bezier path between two points.
     * Returns array of {x, y} positions with natural curvature.
     */
    function generateBezierPath(x0, y0, x1, y1) {
        const dist = Math.hypot(x1 - x0, y1 - y0);
        // More steps for longer distances (8-25 steps)
        const steps = Math.max(8, Math.min(25, Math.floor(dist / 15)));

        // Random control points — offset from straight line for natural curve
        // Humans rarely move in straight lines; there's always a slight arc
        const curvature = 0.2 + Math.random() * 0.3; // 20-50% deviation
        const midX = (x0 + x1) / 2;
        const midY = (y0 + y1) / 2;
        const perpX = -(y1 - y0); // Perpendicular direction
        const perpY = x1 - x0;
        const perpLen = Math.hypot(perpX, perpY) || 1;

        // Randomly curve left or right
        const sign = Math.random() < 0.5 ? 1 : -1;
        const offset = dist * curvature * sign;

        const cp1x = midX + (perpX / perpLen) * offset * 0.6 + (Math.random() - 0.5) * 20;
        const cp1y = midY + (perpY / perpLen) * offset * 0.6 + (Math.random() - 0.5) * 20;
        const cp2x = midX + (perpX / perpLen) * offset * 0.4 + (Math.random() - 0.5) * 20;
        const cp2y = midY + (perpY / perpLen) * offset * 0.4 + (Math.random() - 0.5) * 20;

        const path = [];
        for (let i = 0; i <= steps; i++) {
            const rawT = i / steps;
            const t = easeInOutCubic(rawT); // Apply human-like easing
            path.push({
                x: cubicBezier(t, x0, cp1x, cp2x, x1),
                y: cubicBezier(t, y0, cp1y, cp2y, y1),
            });
        }
        return path;
    }

    /**
     * Dispatch mouse events along a Bezier path with human-like timing.
     * Includes acceleration/deceleration, micro-jitter, and occasional pauses.
     */
    async function humanMouseMove(targetX, targetY) {
        const startX = _lastMouseX ?? randomBetween(200, 600);
        const startY = _lastMouseY ?? randomBetween(200, 400);

        const path = generateBezierPath(startX, startY, targetX, targetY);

        for (let i = 0; i < path.length; i++) {
            const pt = path[i];

            // Add micro-jitter (±1px — hand tremor)
            const jitterX = (Math.random() - 0.5) * 2;
            const jitterY = (Math.random() - 0.5) * 2;
            const finalX = Math.round(pt.x + jitterX);
            const finalY = Math.round(pt.y + jitterY);

            // Dispatch mousemove
            document.body.dispatchEvent(new MouseEvent('mousemove', {
                clientX: finalX, clientY: finalY,
                bubbles: true, cancelable: true,
            }));

            // 30% chance: also fire pointermove (modern frameworks)
            if (Math.random() < 0.3) {
                document.body.dispatchEvent(new PointerEvent('pointermove', {
                    clientX: finalX + (Math.random() - 0.5) * 2,
                    clientY: finalY + (Math.random() - 0.5) * 2,
                    bubbles: true, cancelable: true,
                }));
            }

            _lastMouseX = finalX;
            _lastMouseY = finalY;

            // Human timing: 10-40ms between steps + occasional micro-pause
            let delay = randomBetween(10, 40);
            if (Math.random() < 0.08) {
                // 8% chance of micro-pause (50-150ms) — hesitation / thinking
                delay += randomBetween(50, 150);
            }
            await sleep(delay);
        }
    }

    /**
     * Simulate a complete human mouse interaction session.
     * Includes: move → optional hover → optional small drift.
     */
    async function simulateMouseMove() {
        // Only simulate when tab is hidden — don't interfere with real user
        if (document.visibilityState === 'visible') return;

        try {
            const w = Math.max(window.innerWidth || 800, 400);
            const h = Math.max(window.innerHeight || 600, 300);

            // Pick a natural target area (avoid edges — humans don't go to corners)
            const targetX = randomBetween(w * 0.1, w * 0.9);
            const targetY = randomBetween(h * 0.1, h * 0.8);

            // Phase 1: Move to target via Bezier curve
            await humanMouseMove(targetX, targetY);

            // Phase 2: 40% chance — hover pause (reading/looking at something)
            if (Math.random() < 0.4) {
                await sleep(randomBetween(200, 800));

                // Fire mouseover/mouseenter on nearest element
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

            // Phase 3: 25% chance — small drift after stopping (hand micro-movement)
            if (Math.random() < 0.25) {
                await sleep(randomBetween(100, 300));
                const driftX = targetX + randomBetween(-15, 15);
                const driftY = targetY + randomBetween(-10, 10);
                await humanMouseMove(driftX, driftY);
            }
        } catch (e) {
            // Silently ignore — page might have restricted body
        }
    }

    /**
     * Human-like scroll: momentum-based with slight overshoot and bounce-back.
     */
    async function performMicroScroll() {
        if (document.visibilityState === 'visible') return;

        try {
            // Decide scroll direction (mostly down, sometimes up)
            const direction = Math.random() < 0.7 ? 1 : -1;

            // Human scroll: 2-5 small increments with momentum decay
            const totalScroll = randomBetween(20, 80) * direction;
            const steps = randomBetween(2, 5);
            let remaining = totalScroll;

            for (let i = 0; i < steps; i++) {
                // Momentum: first scroll is biggest, then decays
                const fraction = (steps - i) / steps;
                const scrollAmount = Math.round(remaining * fraction * 0.5);
                remaining -= scrollAmount;

                window.scrollBy({ top: scrollAmount, behavior: 'instant' });

                // Fire wheel event (reCAPTCHA listens for these)
                document.dispatchEvent(new WheelEvent('wheel', {
                    deltaY: scrollAmount,
                    bubbles: true, cancelable: true,
                }));

                await sleep(randomBetween(30, 80));
            }

            // 50% chance: slight bounce-back (overshoot correction)
            if (Math.random() < 0.5) {
                await sleep(randomBetween(100, 250));
                const bounce = Math.round(totalScroll * -0.15);
                window.scrollBy({ top: bounce, behavior: 'instant' });
            }
        } catch (e) { }
    }

    /** Promise-based sleep for async timing */
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

            // ★ Piggyback: also refresh x-client-data by triggering a small fetch
            // to Google domains. Chrome adds x-client-data to these requests,
            // which onBeforeSendHeaders in background.js captures.
            // This ensures xcd doesn't stay at 8 chars — refreshes every 60s.
            performLightweightRefresh();

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
            // Fire-and-forget: async Bezier simulation runs in background
            (async () => {
                await simulateMouseMove();
                await performMicroScroll();
            })().catch(() => { });
            console.log('[VEO Bridge Content] 🖱️ Human-like activity simulation triggered');
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
            const endpointKey = msg.endpoint || '';
            // ★ Progressive timeout: use dynamic values from Python tier
            const rcTimeout = msg.rcTimeout || 15000;
            const fetchTimeout = msg.fetchTimeout || 20000;

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

            // Safety timeout — scales with fetchTimeout (2x for reCAPTCHA + fetch + margin)
            const relayTimeout = Math.max((rcTimeout + fetchTimeout) * 2, 60000);
            const timeout = setTimeout(() => {
                window.removeEventListener('message', resultHandler);
                console.error(`[VEO Bridge Content] ❌ submit_prompt timed out (${relayTimeout / 1000}s)`);
                chrome.runtime.sendMessage({
                    action: 'submit_prompt_relay_result',
                    requestId: requestId,
                    success: false,
                    error: `Content script relay timeout (${relayTimeout / 1000}s)`,
                });
            }, relayTimeout);

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
    const endpointKey = ${JSON.stringify(endpointKey)};
    const rcTimeoutMs = ${rcTimeout};
    const fetchTimeoutMs = ${fetchTimeout};

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
                    setTimeout(() => reject(new Error('reCAPTCHA execute timeout (' + (rcTimeoutMs / 1000) + 's)')), rcTimeoutMs)
                );
                recaptchaToken = await Promise.race([recaptchaPromise, recaptchaTimeout]);
                // HAR verified: valid tokens are 1742-2169 chars
                if (!recaptchaToken || recaptchaToken.length < 1500) {
                    window.postMessage({ type: '__VEO_SUBMIT_RESULT__', requestId, result: {
                        success: false,
                        error: 'reCAPTCHA token too short (' + (recaptchaToken ? recaptchaToken.length : 0) + ' chars, need ≥1500)',
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
            // ★ T2I/I2I: also inject into nested requests[].clientContext
            // F12 verified 2026-03-15: T2I format has clientContext inside
            // EACH request item, and ALL must include recaptchaContext
            if (Array.isArray(body.requests)) {
                for (const req of body.requests) {
                    if (req.clientContext) {
                        req.clientContext.recaptchaContext = {
                            token: recaptchaToken,
                            applicationType: 'RECAPTCHA_APPLICATION_TYPE_WEB',
                        };
                    }
                }
            }
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
        const fetchTimer = setTimeout(() => controller.abort(), fetchTimeoutMs);
        try {
            const resp = await fetch(endpointUrl, {
                method: 'POST',
                headers,
                credentials: 'include',
                body: JSON.stringify(body),
                signal: controller.signal,
            });
            clearTimeout(fetchTimer);
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
            clearTimeout(fetchTimer);
            const errMsg = fetchErr.name === 'AbortError'
                ? 'fetch timeout (' + (fetchTimeoutMs / 1000) + 's) — API did not respond'
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
