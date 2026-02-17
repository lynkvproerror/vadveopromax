#!/usr/bin/env node
/**
 * VEO Pro Max — Extension Installer via CDP Pipe
 * 
 * Chrome 137+ removed --load-extension flag.
 * This script uses CDP over --remote-debugging-pipe to install the extension.
 * Node.js handles pipe file descriptors correctly on Windows.
 * 
 * Usage: node install_extension.js <chrome_exe> <profile_path> <extension_path>
 */

const { spawn } = require('child_process');

const args = process.argv.slice(2);
if (args.length < 3) {
    console.error('Usage: node install_extension.js <chrome_exe> <profile_path> <extension_path>');
    process.exit(1);
}

const [chromeExe, profilePath, extensionPath] = args;

// Normalize extension path to forward slashes
const extPathNormalized = extensionPath.replace(/\\/g, '/');

console.log(`[ExtInstaller] Chrome: ${chromeExe}`);
console.log(`[ExtInstaller] Profile: ${profilePath}`);
console.log(`[ExtInstaller] Extension: ${extPathNormalized}`);

let exiting = false;

function cleanup(exitCode) {
    if (exiting) return;
    exiting = true;
    try { chrome.kill(); } catch (e) { }
    setTimeout(() => process.exit(exitCode), 500);
}

// Create pipes for CDP communication
// Chrome reads from pipe 3, writes to pipe 4
const chrome = spawn(chromeExe, [
    `--user-data-dir=${profilePath}`,
    '--remote-debugging-pipe',
    '--enable-unsafe-extension-debugging',
    '--enable-extensions',
    '--remote-allow-origins=*',
    '--no-first-run',
    '--no-default-browser-check',
    '--headless=new',
], {
    stdio: ['ignore', 'pipe', 'pipe', 'pipe', 'pipe'],
    // FD 0 = stdin (ignore)
    // FD 1 = stdout (pipe - for Chrome's regular output)
    // FD 2 = stderr (pipe - for Chrome's regular errors)
    // FD 3 = pipe (CDP input - we write commands here)
    // FD 4 = pipe (CDP output - we read responses here)
});

let responseBuffer = '';
const cdpIn = chrome.stdio[3];
const cdpOut = chrome.stdio[4];

// Handle EPIPE errors on the CDP input pipe gracefully
cdpIn.on('error', (err) => {
    if (err.code === 'EPIPE') {
        console.error('[ExtInstaller] ❌ Chrome closed the CDP pipe (profile may be locked by another Chrome)');
    } else {
        console.error(`[ExtInstaller] ❌ CDP pipe error: ${err.message}`);
    }
    cleanup(1);
});

// Handle CDP output pipe close
cdpOut.on('error', (err) => {
    // Ignore errors on output pipe if we're already exiting
    if (!exiting) {
        console.error(`[ExtInstaller] ❌ CDP output error: ${err.message}`);
    }
});

// Read from Chrome stderr (startup messages)
chrome.stderr.on('data', (data) => {
    const msg = data.toString();
    // Only log actual errors, skip noise
    if (msg.includes('ERROR') && !msg.includes('crashpad')) {
        console.error(`[Chrome stderr] ${msg.trim()}`);
    }
});

// Read CDP responses from FD 4
cdpOut.on('data', (data) => {
    responseBuffer += data.toString();

    // CDP pipe messages are null-byte delimited
    const messages = responseBuffer.split('\0');
    responseBuffer = messages.pop(); // Keep incomplete last part

    for (const msg of messages) {
        if (!msg) continue;
        try {
            const parsed = JSON.parse(msg);
            handleCDPResponse(parsed);
        } catch (e) {
            console.error(`[ExtInstaller] Failed to parse CDP response: ${e.message}`);
        }
    }
});

function handleCDPResponse(response) {
    console.log(`[ExtInstaller] CDP Response: ${JSON.stringify(response)}`);

    if (response.id === 1) {
        if (response.result && response.result.id) {
            console.log(`[ExtInstaller] ✅ Extension installed! ID: ${response.result.id}`);
            // Output the extension ID for the Python caller
            console.log(`EXT_ID=${response.result.id}`);
            cleanup(0);
        } else if (response.error) {
            console.error(`[ExtInstaller] ❌ Failed: ${response.error.message}`);
            cleanup(1);
        } else {
            console.error(`[ExtInstaller] ⚠️ Unexpected response`);
            cleanup(1);
        }
    }
}

function sendCDP(method, params) {
    if (exiting) return;
    const msg = JSON.stringify({ id: 1, method, params });
    try {
        cdpIn.write(msg + '\0');
        console.log(`[ExtInstaller] Sent: ${method}`);
    } catch (e) {
        console.error(`[ExtInstaller] ❌ Failed to send CDP command: ${e.message}`);
        cleanup(1);
    }
}

// Wait for Chrome to start, then send the install command
setTimeout(() => {
    if (exiting) return;
    if (chrome.exitCode !== null) {
        console.error('[ExtInstaller] ❌ Chrome exited before we could install');
        process.exit(1);
    }

    console.log('[ExtInstaller] Sending Extensions.loadUnpacked...');
    sendCDP('Extensions.loadUnpacked', { path: extPathNormalized });
}, 3000);

// Timeout after 20 seconds
setTimeout(() => {
    if (!exiting) {
        console.error('[ExtInstaller] ⏰ Timeout - no response after 20s');
        cleanup(1);
    }
}, 20000);

// Handle Chrome process exit
chrome.on('exit', (code, signal) => {
    if (!exiting) {
        if (code !== null && code !== 0) {
            console.error(`[ExtInstaller] ❌ Chrome exited with code ${code}`);
        } else if (signal) {
            console.error(`[ExtInstaller] Chrome killed by signal ${signal}`);
        }
        // If Chrome exits before we got a response, that's an error
        cleanup(1);
    }
});

// Handle uncaught errors to prevent ugly stack traces
process.on('uncaughtException', (err) => {
    if (err.code === 'EPIPE') {
        console.error('[ExtInstaller] ❌ Pipe broken (Chrome may have crashed or profile is locked)');
    } else {
        console.error(`[ExtInstaller] ❌ Unexpected error: ${err.message}`);
    }
    cleanup(1);
});
