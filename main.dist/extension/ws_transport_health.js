(function (globalScope) {
  const RECONNECT_BASE_MS = 5000;
  const RECONNECT_MAX_MS = 30000;
  const SOCKET_STALE_MS = 55000;
  const PING_TIMEOUT_MS = 25000;
  const PING_INTERVAL_MS = 20000;
  const WS_OPEN = 1;

  function _num(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function computeReconnectDelayMs(attempt) {
    const normalizedAttempt = Math.max(1, Math.floor(_num(attempt, 1)));
    const multiplier = Math.pow(2, Math.max(0, normalizedAttempt - 1));
    return Math.min(RECONNECT_MAX_MS, RECONNECT_BASE_MS * multiplier);
  }

  function shouldForceReconnect(state) {
    const info = state && typeof state === "object" ? state : {};
    const now = _num(info.now, Date.now());
    const readyState = _num(info.readyState, -1);
    const wsOpenValue = _num(info.wsOpenValue, WS_OPEN);
    if (readyState !== wsOpenValue) return false;

    const pingSentAt = _num(info.pingSentAt, 0);
    const pingTimeoutMs = Math.max(1000, _num(info.pingTimeoutMs, PING_TIMEOUT_MS));
    if (pingSentAt > 0 && (now - pingSentAt) >= pingTimeoutMs) {
      return true;
    }

    const lastObservedAt = Math.max(
      _num(info.lastInboundAt, 0),
      _num(info.lastPongAt, 0),
      _num(info.lastOpenAt, 0),
    );
    if (lastObservedAt <= 0) return false;
    const staleMs = Math.max(1000, _num(info.staleMs, SOCKET_STALE_MS));
    return (now - lastObservedAt) >= staleMs;
  }

  function shouldSendPing(state) {
    const info = state && typeof state === "object" ? state : {};
    const now = _num(info.now, Date.now());
    const pingSentAt = _num(info.pingSentAt, 0);
    const lastPingAt = _num(info.lastPingAt, 0);
    const minPingIntervalMs = Math.max(1000, _num(info.minPingIntervalMs, PING_INTERVAL_MS));
    if (pingSentAt > 0 && (now - pingSentAt) < minPingIntervalMs) {
      return false;
    }
    if (lastPingAt > 0 && (now - lastPingAt) < minPingIntervalMs) {
      return false;
    }
    return true;
  }

  const api = {
    RECONNECT_BASE_MS,
    RECONNECT_MAX_MS,
    SOCKET_STALE_MS,
    PING_TIMEOUT_MS,
    PING_INTERVAL_MS,
    WS_OPEN,
    computeReconnectDelayMs,
    shouldForceReconnect,
    shouldSendPing,
  };

  globalScope.FlowWsHealth = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof self !== "undefined" ? self : globalThis);
