/**
 * VEO Pro Max Bridge — Popup Script
 * Shows WebSocket connection status, active tabs, and bridge debug flags.
 */

function formatAgo(ts) {
  if (!ts) return 'never';
  const delta = Math.max(0, Date.now() - ts);
  if (delta < 1000) return 'just now';
  const sec = Math.floor(delta / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hrs = Math.floor(min / 60);
  return `${hrs}h ago`;
}

function addDebugItem(debugList, key, value) {
  const li = document.createElement('li');
  li.innerHTML = `
    <span class="key">${key}</span>
    <span class="value">${value}</span>
  `;
  debugList.appendChild(li);
}

function buildDiagnosis(response) {
  const debug = response.debug || {};
  const bg = debug.background || {};
  const off = debug.offscreen || {};

  if (response.connected) {
    const port = response.port || off.currentPort || 8765;
    return `Bridge healthy. WebSocket is open on ws://127.0.0.1:${port}.`;
  }
  if (!debug.offscreenExists) {
    return 'Offscreen document is missing. Background worker created no persistent WS client.';
  }
  if (off.readyStateName === 'CONNECTING') {
    return `Offscreen is dialing ${off.lastConnectUrl || 'the app'} now.`;
  }
  if (off.fastScanActive) {
    return 'Offscreen is fast-scanning ports 8765/8766/8767 after a socket drop.';
  }
  if (off.reconnectScheduled) {
    return `Reconnect already scheduled. Next retry in ~${Math.max(1, Math.round((off.reconnectDelayMs || 0) / 1000))}s.`;
  }
  if (bg.lastOffscreenSyncError) {
    return `Background sync failed: ${bg.lastOffscreenSyncError}`;
  }
  if (off.lastErrorMessage) {
    return `Last WS error: ${off.lastErrorMessage}`;
  }
  if (!off.lastOpenAt && off.lastConnectAttemptAt) {
    return 'No successful WebSocket open yet. App socket may be closed or blocked.';
  }
  return 'Bridge is disconnected. See debug flags below for the failing stage.';
}

function renderTabs(tabsList, response) {
  tabsList.innerHTML = '';
  if (response.tabs && response.tabs.length > 0) {
    for (const tab of response.tabs) {
      const li = document.createElement('li');
      li.innerHTML = `
        <span class="email">${tab.email}</span>
        <span class="info">${tab.headerCount} headers</span>
      `;
      tabsList.appendChild(li);
    }
    return;
  }
  const li = document.createElement('li');
  li.className = 'empty';
  li.textContent = 'No VEO tabs detected';
  tabsList.appendChild(li);
}

function renderDebug(debugList, response) {
  debugList.innerHTML = '';
  const debug = response.debug || {};
  const bg = debug.background || {};
  const off = debug.offscreen || {};

  addDebugItem(debugList, 'BG WS Flag', bg.wsConnected ? 'true' : 'false');
  addDebugItem(debugList, 'Offscreen Exists', debug.offscreenExists ? `yes (${debug.offscreenCount})` : 'no');
  addDebugItem(debugList, 'Offscreen WS', off.connected ? 'true' : 'false');
  addDebugItem(debugList, 'ReadyState', off.readyStateName || 'unknown');
  addDebugItem(debugList, 'Current Port', off.currentPort ?? 'n/a');
  addDebugItem(debugList, 'Last Attempt', `${off.lastConnectPort ?? 'n/a'} • ${formatAgo(off.lastConnectAttemptAt)}`);
  addDebugItem(debugList, 'Last Open', `${off.lastOpenPort ?? 'n/a'} • ${formatAgo(off.lastOpenAt)}`);
  addDebugItem(debugList, 'Last Close', off.lastCloseAt ? `code=${off.lastCloseCode} clean=${off.lastCloseWasClean} • ${formatAgo(off.lastCloseAt)}` : 'never');
  addDebugItem(debugList, 'Last Error', off.lastErrorMessage || 'none');
  addDebugItem(debugList, 'Reconnect', off.reconnectScheduled ? `${Math.round((off.reconnectDelayMs || 0) / 1000)}s pending` : 'idle');
  addDebugItem(debugList, 'Fast Scan', off.fastScanActive ? 'active' : 'idle');
  addDebugItem(debugList, 'Queue Depth', bg.wsQueueDepth ?? 0);
  addDebugItem(debugList, 'Last Tab Register', bg.lastTabRegisterEmail ? `${bg.lastTabRegisterEmail} • ${formatAgo(bg.lastTabRegisterAt)}` : 'none');
  addDebugItem(debugList, 'Last Sent Action', bg.lastSentAction ? `${bg.lastSentAction} • ${formatAgo(bg.lastSentAt)}` : 'none');
  addDebugItem(debugList, 'Last Queued Action', bg.lastQueuedAction ? `${bg.lastQueuedAction} • ${formatAgo(bg.lastQueuedAt)}` : 'none');
  addDebugItem(debugList, 'Last Sync', bg.lastOffscreenSyncAt ? `${bg.lastOffscreenSyncOk ? 'ok' : 'fail'} • ${formatAgo(bg.lastOffscreenSyncAt)}` : 'never');
}

document.addEventListener('DOMContentLoaded', () => {
  const wsDot = document.getElementById('wsDot');
  const wsLabel = document.getElementById('wsLabel');
  const tabsList = document.getElementById('tabsList');
  const diagBox = document.getElementById('diagBox');
  const debugList = document.getElementById('debugList');
  const refreshBtn = document.getElementById('refreshBtn');

  function loadStatus() {
    chrome.runtime.sendMessage({ action: 'getStatus' }, (response) => {
      if (chrome.runtime.lastError) {
        wsDot.className = 'dot disconnected';
        wsLabel.textContent = 'Extension not responding';
        diagBox.textContent = chrome.runtime.lastError.message || 'Runtime error';
        debugList.innerHTML = '';
        addDebugItem(debugList, 'Runtime Error', chrome.runtime.lastError.message || 'unknown');
        return;
      }

      if (!response) {
        wsDot.className = 'dot disconnected';
        wsLabel.textContent = 'Extension not responding';
        diagBox.textContent = 'No status payload returned from background worker.';
        return;
      }

      const off = (response.debug && response.debug.offscreen) || {};
      const port = response.port || off.currentPort || 8765;

      if (response.connected) {
        wsDot.className = 'dot connected';
        wsLabel.textContent = `Connected to App (ws://127.0.0.1:${port})`;
      } else if (off.readyStateName === 'CONNECTING') {
        wsDot.className = 'dot disconnected';
        wsLabel.textContent = `Connecting to App (ws://127.0.0.1:${port})...`;
      } else {
        wsDot.className = 'dot disconnected';
        wsLabel.textContent = 'Disconnected — see debug flags';
      }

      diagBox.textContent = buildDiagnosis(response);
      renderTabs(tabsList, response);
      renderDebug(debugList, response);
    });
  }

  refreshBtn.addEventListener('click', loadStatus);
  loadStatus();
  setInterval(loadStatus, 2000);
});
