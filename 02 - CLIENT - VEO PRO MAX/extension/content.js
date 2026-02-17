/**
 * VEO Pro Max Bridge — Content Script
 *
 * Injected into labs.google.com pages.
 *
 * Responsibilities:
 * 1. Detect logged-in email and register tab with background.js
 * 2. Execute grecaptcha.enterprise.execute() on demand
 * 3. Extract access_token from __NEXT_DATA__
 */

// Guard against double injection (manifest content_scripts + background.js injectExistingTabs)
if (window.__veoContentLoaded) {
    // Already loaded — just re-register in case service worker restarted
    try { detectAndRegister(); } catch (e) { }
} else {
    window.__veoContentLoaded = true;

    // ── Constants ──────────────────────────────────────────────────────────
    // (reCAPTCHA execution moved to background.js via chrome.scripting.executeScript)


    // ── Tab Registration ───────────────────────────────────────────────────

    function detectAndRegister() {
        // Extract email from page
        const email = extractEmail();
        if (email) {
            chrome.runtime.sendMessage({ action: 'register_tab', email });
            console.log(`[VEO Bridge Content] Registered tab with email: ${email}`);
        } else {
            // Retry after page finishes loading
            setTimeout(() => {
                const retryEmail = extractEmail();
                if (retryEmail) {
                    chrome.runtime.sendMessage({ action: 'register_tab', email: retryEmail });
                    console.log(`[VEO Bridge Content] Registered tab (retry): ${retryEmail}`);
                }
            }, 3000);
        }
    }

    function extractEmail() {
        // Method 1: From __NEXT_DATA__
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

        // Method 3: From aria-label on avatar
        const avatarEl = document.querySelector('a[aria-label*="@"]');
        if (avatarEl) {
            const match = avatarEl.getAttribute('aria-label').match(/[\w.+-]+@[\w-]+\.[\w.]+/);
            if (match) return match[0];
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


    // ── Message Handler ────────────────────────────────────────────────────

    chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
        if (msg.action === 'get_access_token') {
            const result = extractAccessToken();
            sendResponse(result);
            return false; // sync
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


    // ── Init ────────────────────────────────────────────────────────────────

    // Wait for page to be fully loaded before registering
    if (document.readyState === 'complete') {
        detectAndRegister();
    } else {
        window.addEventListener('load', detectAndRegister);
    }

    console.log('[VEO Bridge Content] Content script loaded on', window.location.hostname);

} // end of double-injection guard
