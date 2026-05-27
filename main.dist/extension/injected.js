/**
 * Injected into MAIN world on labs.google — has access to window.grecaptcha
 * and intercepts TRPC fetch responses to capture fresh signed media URLs.
 *
 * This script must be idempotent because the extension can re-inject it after
 * Flow tab wake/reload or content-script recovery.
 */
(function () {
  if (window.__FLOW_AGENT_MAIN_BRIDGE_INSTALLED__) {
    return;
  }
  window.__FLOW_AGENT_MAIN_BRIDGE_INSTALLED__ = true;

  const SITE_KEY = '6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV';

  function _dispatchCapturedFlowAuthToken(token, url = '') {
    const clean = String(token || '').trim();
    if (!/^ya29\./.test(clean)) return;
    window.dispatchEvent(new CustomEvent('FLOW_AUTH_TOKEN_CAPTURED', {
      detail: { token: clean, url },
    }));
  }

  function _extractBearerToken(headersLike) {
    if (!headersLike) return '';

    try {
      if (headersLike instanceof Headers) {
        const value = headersLike.get('authorization') || headersLike.get('Authorization') || '';
        const token = String(value).replace(/^Bearer\s+/i, '').trim();
        return /^ya29\./.test(token) ? token : '';
      }
    } catch {}

    if (Array.isArray(headersLike)) {
      for (const entry of headersLike) {
        if (!Array.isArray(entry) || entry.length < 2) continue;
        if (String(entry[0] || '').toLowerCase() !== 'authorization') continue;
        const token = String(entry[1] || '').replace(/^Bearer\s+/i, '').trim();
        if (/^ya29\./.test(token)) return token;
      }
      return '';
    }

    if (typeof headersLike === 'object') {
      for (const [key, value] of Object.entries(headersLike)) {
        if (String(key || '').toLowerCase() !== 'authorization') continue;
        const token = String(value || '').replace(/^Bearer\s+/i, '').trim();
        if (/^ya29\./.test(token)) return token;
      }
    }

    return '';
  }

  function _captureAuthFromFetchArgs(args) {
    const input = args?.[0];
    const init = args?.[1];
    const url = typeof input === 'string' ? input : input?.url || '';
    const token =
      _extractBearerToken(init?.headers) ||
      _extractBearerToken(input?.headers);
    if (token) _dispatchCapturedFlowAuthToken(token, url);
  }

  const _originalFetch = window.fetch;
  window.fetch = async function (...args) {
    try {
      _captureAuthFromFetchArgs(args);
    } catch {}
    const response = await _originalFetch.apply(this, args);
    try {
      const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
      if (url.includes('/fx/api/trpc/') && response.ok) {
        const clone = response.clone();
        clone.text().then((text) => {
          if (text.includes('storage.googleapis.com/ai-sandbox-videofx/')) {
            window.dispatchEvent(new CustomEvent('TRPC_MEDIA_URLS', {
              detail: { url, body: text },
            }));
          }
        }).catch(() => {});
      }
    } catch {}
    return response;
  };

  const _xhrOpen = XMLHttpRequest.prototype.open;
  const _xhrSetRequestHeader = XMLHttpRequest.prototype.setRequestHeader;

  XMLHttpRequest.prototype.open = function (...args) {
    try {
      this.__flowExtRequestUrl = String(args?.[1] || '');
    } catch {}
    return _xhrOpen.apply(this, args);
  };

  XMLHttpRequest.prototype.setRequestHeader = function (name, value) {
    try {
      if (String(name || '').toLowerCase() === 'authorization') {
        const token = String(value || '').replace(/^Bearer\s+/i, '').trim();
        if (/^ya29\./.test(token)) {
          _dispatchCapturedFlowAuthToken(token, this.__flowExtRequestUrl || '');
        }
      }
    } catch {}
    return _xhrSetRequestHeader.apply(this, arguments);
  };

  window.addEventListener('GET_CAPTCHA', async ({ detail }) => {
    const { requestId, pageAction } = detail;
    try {
      await waitForGrecaptcha();
      const token = await window.grecaptcha.enterprise.execute(SITE_KEY, {
        action: pageAction,
      });
      window.dispatchEvent(new CustomEvent('CAPTCHA_RESULT', {
        detail: { requestId, token },
      }));
    } catch (e) {
      window.dispatchEvent(new CustomEvent('CAPTCHA_RESULT', {
        detail: { requestId, error: e.message },
      }));
    }
  });

  function waitForGrecaptcha(timeout = 10000) {
    return new Promise((resolve, reject) => {
      const start = Date.now();
      const check = () => {
        if (window.grecaptcha?.enterprise?.execute) return resolve();
        if (Date.now() - start > timeout) return reject(new Error('grecaptcha not available'));
        setTimeout(check, 200);
      };
      check();
    });
  }
})();
