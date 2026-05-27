/**
 * Content script — bridge between background.js and injected.js
 * Injects injected.js into MAIN world to access window.grecaptcha.
 *
 * This file is intentionally idempotent because the background worker may
 * re-inject it when waking/reloading the Flow tab.
 */
(function () {
  if (globalThis.__FLOW_AGENT_CONTENT_BRIDGE_INSTALLED__) {
    return;
  }
  globalThis.__FLOW_AGENT_CONTENT_BRIDGE_INSTALLED__ = true;

  const INJECT_ATTR = 'data-flow-agent-main-bridge';
  let runtimeInvalidated = false;

  const runtimeAlive = () => {
    try {
      return !runtimeInvalidated && !!(globalThis.chrome && chrome.runtime && chrome.runtime.id);
    } catch (_) {
      runtimeInvalidated = true;
      return false;
    }
  };

  const safeSendMessage = (payload) => {
    if (!runtimeAlive()) return;
    try {
      const maybePromise = chrome.runtime.sendMessage(payload);
      if (maybePromise && typeof maybePromise.catch === 'function') {
        maybePromise.catch((error) => {
          const message = String(error?.message || error || '');
          if (message.toLowerCase().includes('extension context invalidated')) {
            runtimeInvalidated = true;
            return;
          }
          console.warn('[FlowAgent] content sendMessage failed:', message);
        });
      }
    } catch (error) {
      const message = String(error?.message || error || '');
      if (message.toLowerCase().includes('extension context invalidated')) {
        runtimeInvalidated = true;
        return;
      }
      console.warn('[FlowAgent] content sendMessage failed:', message);
    }
  };

  const injectMainBridge = () => {
    try {
      if (!runtimeAlive()) return;
      const root = document.head || document.documentElement;
      if (!root) return;
      const existing = document.querySelector(`script[${INJECT_ATTR}="1"]`);
      if (existing) return;
      const s = document.createElement('script');
      s.setAttribute(INJECT_ATTR, '1');
      s.src = chrome.runtime.getURL('injected.js');
      s.onload = () => s.remove();
      root.appendChild(s);
    } catch (error) {
      console.warn('[FlowAgent] Failed to inject main-world bridge:', error);
    }
  };

  injectMainBridge();

  chrome.runtime.onMessage.addListener((msg, _, reply) => {
    if (msg.type !== 'GET_CAPTCHA') return;

    const { requestId, pageAction } = msg;

    const handler = (e) => {
      if (e.detail?.requestId === requestId) {
        window.removeEventListener('CAPTCHA_RESULT', handler);
        clearTimeout(timer);
        reply({ token: e.detail.token, error: e.detail.error });
      }
    };

    const timer = setTimeout(() => {
      window.removeEventListener('CAPTCHA_RESULT', handler);
      reply({ error: 'CONTENT_TIMEOUT' });
    }, 25000);

    window.addEventListener('CAPTCHA_RESULT', handler);

    window.dispatchEvent(new CustomEvent('GET_CAPTCHA', {
      detail: { requestId, pageAction },
    }));

    return true; // keep channel open for async reply
  });

  // ─── TRPC Media URL Monitor ─────────────────────────────────
  // Forward intercepted TRPC responses with media URLs to background.js
  window.addEventListener('TRPC_MEDIA_URLS', (e) => {
    const { url, body } = e.detail || {};
    if (!body) return;
    safeSendMessage({
      type: 'TRPC_MEDIA_URLS',
      trpcUrl: url,
      body,
    });
  });

  window.addEventListener('FLOW_AUTH_TOKEN_CAPTURED', (e) => {
    const token = String(e.detail?.token || '').trim();
    if (!token) return;
    safeSendMessage({
      type: 'FLOW_AUTH_TOKEN_CAPTURED',
      token,
    });
  });
})();
