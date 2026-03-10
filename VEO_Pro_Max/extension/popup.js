/* VEO Pro Max Extension v2.2.2 - Protected */
document.addEventListener('DOMContentLoaded', () => {
const wsDot = document.getElementById('wsDot');
const wsLabel = document.getElementById('wsLabel');
const tabsList = document.getElementById('tabsList');
chrome.runtime.sendMessage({ action: 'getStatus' }, (response) => {
if (!response) {
wsLabel.textContent = 'Extension not responding';
return;
}
if (response.connected) {
wsDot.className = 'dot connected';
wsLabel.textContent = 'Connected to App (ws://127.0.0.1:8765)';
} else {
wsDot.className = 'dot disconnected';
wsLabel.textContent = 'Disconnected — App not running?';
}
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
} else {
const li = document.createElement('li');
li.className = 'empty';
li.textContent = 'No VEO tabs detected';
tabsList.appendChild(li);
}
});
});