"""
VEO Pro Max - Gemini API Key Manager

Auto-provision Gemini API keys via Google AI Studio's internal gRPC-web service.
Keys are AES-encrypted and stored per-account in ~/.veoauto/gemini_keys.json.

Flow:
1. Check saved key → return if exists
2. Navigate browser to AI Studio (cookies context)
3. Run JS: ListCloudProjects → ListCloudApiKeys → GenerateCloudApiKey
4. Save encrypted key per-profile
"""

import json
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("veo.gemini")


class GeminiKeyManager:
    """Auto-fetch or create Gemini API keys via AI Studio's gRPC-web service."""

    RPC_BASE = (
        "https://alkalimakersuite-pa.clients6.google.com/$rpc/"
        "google.internal.alkali.applications.makersuite.v1."
        "MakerSuiteService"
    )
    STATIC_KEY = "AIzaSyDdP816MREB3SkjZO04QXbjsigfcI0GWOs"

    KEYS_FILE = Path.home() / ".veoauto" / "gemini_keys.json"

    # ── JS template runs inside browser page ───────────────────────
    # Replaces %RPC_BASE% and %STATIC_KEY% at runtime.
    AUTO_PROVISION_JS = r'''async () => {
        const RPC = "%RPC_BASE%";
        const ORIGIN = "https://aistudio.google.com";

        // ── Build SAPISIDHASH auth header ──
        // Formula: SAPISIDHASH timestamp_SHA1(timestamp + " " + SAPISID + " " + origin)
        async function buildSapisidHash() {
            try {
                const cookies = document.cookie;
                const m = cookies.match(/SAPISID=([^;]+)/);
                if (!m) return null;
                const sapisid = m[1];
                const ts = Math.floor(Date.now() / 1000);
                const input = `${ts} ${sapisid} ${ORIGIN}`;
                const buf = await crypto.subtle.digest("SHA-1",
                    new TextEncoder().encode(input));
                const hex = [...new Uint8Array(buf)]
                    .map(b => b.toString(16).padStart(2, '0')).join('');
                const hash = `${ts}_${hex}`;
                return `SAPISIDHASH ${hash} SAPISID1PHASH ${hash} SAPISID3PHASH ${hash}`;
            } catch(e) { return null; }
        }

        const authHeader = await buildSapisidHash();
        const H = {
            "Content-Type": "application/json+protobuf",
            "x-goog-api-key": "%STATIC_KEY%",
            "x-goog-authuser": "0",
            "x-user-agent": "grpc-web-javascript/0.1",
            "x-goog-ext-519733851-bin": "CAESAUwwATgEQAA="
        };
        if (authHeader) {
            H["authorization"] = authHeader;
        }

        // ── Token extraction helper ──
        // AI Studio uses Google WIZ/Lit framework — CSRF token (SNlM0e) is
        // generated at runtime, NOT embedded as static text in <script> tags.
        function extractToken() {
            // Strategy 1: WIZ_global_data.SNlM0e (standard Google WIZ apps)
            try {
                if (typeof WIZ_global_data !== 'undefined' && WIZ_global_data.SNlM0e) {
                    return WIZ_global_data.SNlM0e;
                }
            } catch(e) {}
            // Strategy 2: window.__WIZ_global_data__
            try {
                if (window.__WIZ_global_data__ && window.__WIZ_global_data__.SNlM0e) {
                    return window.__WIZ_global_data__.SNlM0e;
                }
            } catch(e) {}
            // Strategy 3: Scan script tags for SNlM0e or !-token patterns
            try {
                const scripts = document.querySelectorAll('script');
                for (const s of scripts) {
                    const txt = s.textContent || '';
                    if (txt.length < 50) continue;
                    // SNlM0e assignment pattern
                    let tm = txt.match(/SNlM0e['"]\s*[:,=]\s*['"](![^'"]{20,})['"]/);
                    if (tm) return tm[1];
                    // Direct !-token in quoted string
                    tm = txt.match(/"(![A-Za-z0-9_\-]{20,})"/);
                    if (tm) return tm[1];
                }
            } catch(e) {}
            // Strategy 4: Check AF_initDataCallback / AF_dataServiceRequests
            try {
                for (const c of ['AF_initDataCallback', 'AF_dataServiceRequests']) {
                    const flat = JSON.stringify(window[c]);
                    if (flat) {
                        const tm = flat.match(/"(![A-Za-z0-9_\-]{20,})"/);
                        if (tm) return tm[1];
                    }
                }
            } catch(e) {}
            return null;
        }

        try {
            // ── Step 1: List Cloud Projects ──
            let r = await fetch(RPC + "/ListCloudProjects", {
                method: "POST", credentials: "include",
                headers: H,
                body: JSON.stringify([null, null, null, 1, null, null])
            });
            if (!r.ok) {
                return {error: "list_projects_http_" + r.status, msg: "ListCloudProjects HTTP " + r.status};
            }
            let projects = await r.json();

            // Parse first project number + id
            let projectRef = null;
            let projectId = null;
            if (projects && Array.isArray(projects)) {
                const flat = JSON.stringify(projects);
                const m = flat.match(/projects\/(\d+)/);
                if (m) projectRef = "projects/" + m[1];
                const m2 = flat.match(/gen-lang-client-[\w-]+/);
                if (m2) projectId = m2[0];
            }

            if (!projectRef) {
                // No project — try to create one
                const token = extractToken();
                if (!token) {
                    return {error: "no_project", msg: "No GCP project and cannot extract token to create one"};
                }

                r = await fetch(RPC + "/CreateCloudProject", {
                    method: "POST", credentials: "include",
                    headers: H,
                    body: JSON.stringify([token, "GEMINI API FOR AUTO FLOW"])
                });
                if (!r.ok) {
                    return {error: "create_project_http_" + r.status, msg: "CreateCloudProject HTTP " + r.status};
                }
                let newProj = await r.json();
                const npFlat = JSON.stringify(newProj);
                const npm = npFlat.match(/projects\/(\d+)/);
                if (npm) projectRef = "projects/" + npm[1];
                const npm2 = npFlat.match(/gen-lang-client-[\w-]+/);
                if (npm2) projectId = npm2[0];

                if (!projectRef) {
                    return {error: "create_project_failed", msg: "Failed to create GCP project"};
                }
            }

            // ── Step 2: List existing API Keys ──
            r = await fetch(RPC + "/ListCloudApiKeys", {
                method: "POST", credentials: "include",
                headers: H,
                body: JSON.stringify([100, null, 1, [projectRef]])
            });
            if (!r.ok) {
                return {error: "list_keys_http_" + r.status, msg: "ListCloudApiKeys HTTP " + r.status};
            }
            let keys = await r.json();

            // Parse AIza key from response
            const keysFlat = JSON.stringify(keys);
            const km = keysFlat.match(/AIza[\w-]{35}/);
            if (km) return {key: km[0], source: "existing"};

            // ── Step 3: Generate new API Key ──
            // Re-extract token (changes each call!)
            const token = extractToken();
            if (!token || !projectId) {
                return {error: "no_token", msg: "Cannot extract token to create API key. Use manual paste."};
            }

            r = await fetch(RPC + "/GenerateCloudApiKey", {
                method: "POST", credentials: "include",
                headers: H,
                body: JSON.stringify([projectId, token, null, "GEMINI API FOR AUTO FLOW"])
            });
            if (!r.ok) {
                return {error: "gen_key_http_" + r.status, msg: "GenerateCloudApiKey HTTP " + r.status};
            }
            let newKey = await r.json();
            const nkm = JSON.stringify(newKey).match(/AIza[\w-]{35}/);
            if (nkm) return {key: nkm[0], source: "created"};

            return {error: "create_failed", msg: "GenerateCloudApiKey returned no key"};

        } catch(e) {
            return {error: e.message};
        }
    }'''

    # ── Public API ─────────────────────────────────────────────────

    async def auto_provision(self, email: str, page) -> Optional[str]:
        """Auto-fetch or create Gemini API key for an account.

        Args:
            email: Google account email.
            page: Playwright browser page (already navigated to AI Studio).

        Returns:
            API key string (AIza...) or None if auto-provision failed.
        """
        # Step 0: Check saved key
        saved = self._load_key(email)
        if saved:
            log.info(f"[GeminiKey] Using saved key for {email}")
            return saved

        # Run JS in browser context
        js = (
            self.AUTO_PROVISION_JS
            .replace("%RPC_BASE%", self.RPC_BASE)
            .replace("%STATIC_KEY%", self.STATIC_KEY)
        )

        try:
            result = await page.evaluate(js)
        except Exception as e:
            log.error(f"[GeminiKey] JS execution failed for {email}: {e}")
            return None

        if not result or not isinstance(result, dict):
            log.warning(f"[GeminiKey] No result from JS for {email}")
            return None

        key = result.get("key", "")
        if key.startswith("AIza"):
            source = result.get("source", "unknown")
            log.info(f"[GeminiKey] Key {source} for {email}: {key[:10]}...")
            self._save_key(email, key)
            return key

        # Error case
        error = result.get("error", "unknown")
        msg = result.get("msg", "")
        log.warning(f"[GeminiKey] Auto-provision failed for {email}: {error} — {msg}")
        return None

    async def auto_provision_via_extension(self, email: str, bridge) -> Optional[str]:
        """Auto-fetch or create Gemini API key via Extension Bridge.

        Uses the Extension to run gRPC-web JS inside a browser tab
        (with Google session cookies). More reliable than Playwright because:
        - No dependency on Playwright connection stability
        - Extension has direct chrome.tabs/scripting access
        - Session cookies are always available

        Args:
            email: Google account email.
            bridge: ExtensionBridge instance (must be connected for this email).

        Returns:
            API key string (AIza...) or None if failed.
        """
        # Step 0: Check saved key
        saved = self._load_key(email)
        if saved:
            log.info(f"[GeminiKey] Using saved key for {email}")
            return saved

        # Check extension connection
        if not bridge or not bridge.is_connected(email):
            log.warning(f"[GeminiKey] Extension not connected for {email} — cannot provision via extension")
            return None

        try:
            key = await bridge.request_gemini_key(email, timeout=30.0)
        except Exception as e:
            log.error(f"[GeminiKey] Extension provision failed for {email}: {e}")
            return None

        if key and key.startswith("AIza"):
            log.info(f"[GeminiKey] Key provisioned via Extension for {email}: {key[:10]}...")
            self._save_key(email, key)
            return key

        log.warning(f"[GeminiKey] Extension provision returned no valid key for {email}")
        return None

    def get_key(self, email: str) -> Optional[str]:
        """Get saved key for account (no auto-provision)."""
        return self._load_key(email)

    def set_key(self, email: str, key: str) -> None:
        """Manually set key for account (from paste UI)."""
        self._save_key(email, key)
        log.info(f"[GeminiKey] Manual key saved for {email}: {key[:10]}...")

    def invalidate(self, email: str) -> None:
        """Remove invalid key for account."""
        keys = self._load_all()
        if email in keys:
            del keys[email]
            self._save_all(keys)
            log.info(f"[GeminiKey] Invalidated key for {email}")

    def has_key(self, email: str) -> bool:
        """Check if account has a saved key."""
        return self._load_key(email) is not None

    def remove_key(self, email: str) -> None:
        """Remove key for account (alias for invalidate)."""
        self.invalidate(email)

    def get_rotation_key(self, failed_email: str = "") -> Optional[str]:
        """Get next available key, skipping the failed profile.

        Used when a profile's key hits rate limit or is invalidated.
        Cycles through all profiles to find a working key.

        Args:
            failed_email: Email whose key just failed (skip this one).

        Returns:
            API key from another profile, or None if no keys available.
        """
        keys = self._load_all()
        for email, data in keys.items():
            if email == failed_email:
                continue
            key = None
            if isinstance(data, dict):
                key = self._decrypt(data.get("encrypted", ""))
            elif isinstance(data, str):
                key = data
            if key and key.startswith("AIza"):
                log.info(f"[GeminiKey] Rotation → using key from {email}")
                return key
        log.warning("[GeminiKey] No rotation keys available")
        return None

    def _load_key(self, email: str) -> Optional[str]:
        """Load saved key for account."""
        keys = self._load_all()
        data = keys.get(email)
        if data and isinstance(data, dict):
            return self._decrypt(data.get("encrypted", ""))
        if data and isinstance(data, str):
            return data  # Legacy: plain text
        return None

    def _save_key(self, email: str, key: str) -> None:
        """Save encrypted key for account."""
        keys = self._load_all()
        keys[email] = {"encrypted": self._encrypt(key)}
        self._save_all(keys)

    def _load_all(self) -> dict:
        """Load all keys from file."""
        if self.KEYS_FILE.exists():
            try:
                with open(self.KEYS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_all(self, keys: dict) -> None:
        """Save all keys to file."""
        self.KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(self.KEYS_FILE, "w", encoding="utf-8") as f:
            json.dump(keys, f, indent=2)

    # ── Encryption Helpers ─────────────────────────────────────────
    # Using Fernet (AES-128-CBC from cryptography package)
    # Key derived from machine-specific data for basic protection.

    _fernet = None

    @classmethod
    def _get_fernet(cls):
        """Get or create Fernet instance with machine-derived key."""
        if cls._fernet is None:
            try:
                import base64
                import hashlib
                from cryptography.fernet import Fernet

                # Machine-specific seed (not secure against determined attacker,
                # but prevents casual key theft via file copy)
                import platform
                seed = f"veo-gemini-{platform.node()}-{Path.home()}"
                key = base64.urlsafe_b64encode(
                    hashlib.sha256(seed.encode()).digest()
                )
                cls._fernet = Fernet(key)
            except ImportError:
                log.warning("[GeminiKey] cryptography not installed, using plain storage")
                cls._fernet = None
        return cls._fernet

    @classmethod
    def _encrypt(cls, value: str) -> str:
        """Encrypt a string value."""
        fernet = cls._get_fernet()
        if fernet:
            return fernet.encrypt(value.encode()).decode()
        return value  # Fallback: plain text

    @classmethod
    def _decrypt(cls, value: str) -> Optional[str]:
        """Decrypt a string value."""
        if not value:
            return None
        fernet = cls._get_fernet()
        if fernet:
            try:
                return fernet.decrypt(value.encode()).decode()
            except Exception:
                # May be legacy plain text
                if value.startswith("AIza"):
                    return value
                return None
        return value  # Fallback: plain text
