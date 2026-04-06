/**
 * VEO Pro Max — Stealth Script
 *
 * Runs at document_start in MAIN world (before ANY page JS or reCAPTCHA).
 * Overrides browser properties that reCAPTCHA Enterprise uses to detect
 * automated browsers (CDP sets navigator.webdriver = true).
 *
 * Without this: reCAPTCHA scores are extremely low → API returns 403
 * "reCAPTCHA evaluation failed" on every request.
 */

// ── Override navigator.webdriver ───────────────────────────────────────
// CDP (Chrome DevTools Protocol) sets this to true when attached.
// reCAPTCHA Enterprise checks it and assigns near-zero scores.
Object.defineProperty(navigator, 'webdriver', {
    get: () => false,
    configurable: true,
});

// ── Remove CDP runtime artifacts ──────────────────────────────────────
// Some detection scripts check for these CDP-injected properties
if (window.cdc_adoQpoasnfa76pfcZLmcfl_Array) {
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
}
if (window.cdc_adoQpoasnfa76pfcZLmcfl_Promise) {
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
}
if (window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol) {
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
}

// ── Consistent Chrome feature masks ───────────────────────────────────
// Ensure navigator.plugins and languages look like a real browser
if (navigator.plugins.length === 0) {
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
        configurable: true,
    });
}

// ── Prevent detection via Permission API ──────────────────────────────
// Automated browsers sometimes have inconsistent permission states
const originalQuery = window.navigator.permissions?.query;
if (originalQuery) {
    window.navigator.permissions.query = (parameters) => {
        if (parameters.name === 'notifications') {
            return Promise.resolve({ state: Notification.permission });
        }
        return originalQuery.call(window.navigator.permissions, parameters);
    };
}
