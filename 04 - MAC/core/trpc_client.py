"""
VEO Pro Max - TRPC Client

Reference: VEO_Web_Client_Protocol_Analysis.md §3.2.1
Role: Execute TRPC calls via persistent browser session (cookie-based auth)

TRPC endpoints run on labs.google, NOT aisandbox-pa.
They require browser cookies (not Bearer token), so we use
the RecaptchaBrowserSession's page to execute fetch() calls
inside the browser context where cookies are auto-attached.

Endpoints:
- project.createProject: POST /fx/api/trpc/project.createProject
- project.getProjects: GET /fx/api/trpc/project.getProjects?input=<encoded>

Architecture: This is owned by CHỦ (AccountManager), one per account.

Thread safety:
- The page object may be _SyncPageAsyncWrapper which routes evaluate()
  through a command queue to the browser thread (avoids greenlet crash).
- All fetch() calls in JS are wrapped in try/catch to prevent exceptions
  from propagating through Playwright's greenlet system.
"""

from typing import Optional, Dict, Any
import json
import asyncio
import logging

log = logging.getLogger(__name__)

# TRPC base URL (labs.google, NOT aisandbox-pa)
TRPC_BASE = "https://labs.google/fx/api/trpc"

# Tool names per Protocol Analysis
TOOL_FLOW = "PINHOLE"       # Flow = Image generation
TOOL_WHISK = "BACKBONE"     # Whisk = References

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAYS = [1.0, 2.0, 4.0]  # Exponential backoff


class TRPCClient:
    """Execute TRPC calls via persistent browser page.
    
    Uses page.evaluate(fetch(...)) to send requests from
    the browser context where session cookies are available.
    
    Thread safety: All JS fetch calls are wrapped in try/catch
    to prevent exceptions from crashing Playwright's greenlet system.
    
    Usage:
        client = TRPCClient(page)
        project_id = await client.create_project("My Project")
    """
    
    def __init__(self, page):
        """Initialize with a Playwright Page from RecaptchaBrowserSession.
        
        Args:
            page: Playwright page object with active session cookies.
                  May be _SyncPageAsyncWrapper (command queue routed)
                  or a real Playwright async page.
        """
        self._page = page
    
    async def create_project(
        self,
        title: str = "My Video Project",
        tool_name: str = TOOL_FLOW,
    ) -> Optional[str]:
        """Create a new project via TRPC.
        
        Per Protocol Analysis §3.2.1:
          POST /fx/api/trpc/project.createProject
          Content-Type: application/json
          Body: {"json": {"projectTitle": "...", "toolName": "PINHOLE"}}
          Auth: Cookies (auto-attached by browser)
        
        Response: {"result":{"data":{"json":{"result":{"projectId":"uuid"}}}}}
        
        Args:
            title: Project title
            tool_name: "PINHOLE" (Flow/Image) or "BACKBONE" (Whisk)
            
        Returns:
            project_id string, or None if failed
        """
        endpoint = f"{TRPC_BASE}/project.createProject"
        payload = {
            "json": {
                "projectTitle": title,
                "toolName": tool_name,
            }
        }
        
        try:
            result = await self._trpc_fetch(endpoint, payload)
            if not result:
                return None
            
            # Navigate nested TRPC response structure
            project_id = (
                result
                .get("result", {})
                .get("data", {})
                .get("json", {})
                .get("result", {})
                .get("projectId")
            )
            
            if project_id:
                log.info(f"TRPC: Created project '{title}' → {project_id}")
            else:
                log.warning(f"TRPC: createProject responded but no projectId in: {result}")
            
            return project_id
            
        except Exception as e:
            log.error(f"TRPC createProject failed: {e}")
            return None
    
    async def get_project(
        self,
        project_id: str,
        tool_name: str = TOOL_FLOW,
    ) -> dict | None:
        """Get a single project by ID via TRPC.
        
        Per HAR reference (0. Tao Project.har):
          GET /fx/api/trpc/project.getProject?input=<url-encoded JSON>
          Input: {"json": {"projectId": "...", "toolName": "PINHOLE"}}
        
        Note: project.getProjects (plural) was REMOVED from the API.
        Only single-project lookup exists now.
        
        Args:
            project_id: UUID of the project to fetch
            tool_name: "PINHOLE" or "BACKBONE"
            
        Returns:
            Project dict with projectId etc, or None if not found
        """
        import urllib.parse
        input_data = json.dumps({"json": {"projectId": project_id, "toolName": tool_name}})
        endpoint = f"{TRPC_BASE}/project.getProject?input={urllib.parse.quote(input_data)}"
        
        try:
            result = await self._trpc_query(endpoint)
            if not result:
                return None
            
            project = (
                result
                .get("result", {})
                .get("data", {})
                .get("json", {})
                .get("result", {})
            )
            
            pid = project.get("projectId")
            if pid:
                log.info(f"TRPC: Found project {pid}")
                return project
            return None
            
        except Exception as e:
            log.error(f"TRPC getProject failed: {e}")
            return None

    async def get_projects(
        self,
        tool_name: str = TOOL_FLOW,
    ) -> list:
        """DEPRECATED: project.getProjects endpoint was removed.
        
        Always returns empty list. Callers should use create_project() directly.
        Kept for backward compatibility — will not produce 404 errors.
        """
        log.debug("TRPC: get_projects() skipped (endpoint removed — use create_project)")
        return []
    
    async def get_media_download_url(
        self,
        op_name: str,
    ) -> Optional[str]:
        """Get GCS signed URL for downloading upscaled video.
        
        Per F12 capture, this is NOT a standard TRPC query. Actual format:
          GET /fx/api/trpc/media.getMediaUrlRedirect?name=<op_name>
        
        The server responds with HTTP 302 redirect to a GCS signed URL:
          https://storage.googleapis.com/ai-sandbox-videofx/video/<op_name>
            ?GoogleAccessId=...&Expires=...&Signature=...
        
        Args:
            op_name: Operation name from upscale poll result
                     (e.g. "6e278f5f-6fde-4dec-a9cc-9a4098bab579_upsampled")
            
        Returns:
            GCS signed URL string, or None if failed
        """
        import urllib.parse
        endpoint = f"{TRPC_BASE}/media.getMediaUrlRedirect?name={urllib.parse.quote(op_name)}"
        
        log.debug(f"[TRPC-DL] get_media_download_url: op_name={op_name[:60]}")
        log.debug(f"[TRPC-DL] endpoint={endpoint[:150]}")
        
        if not self._page:
            log.error("TRPC: No page available for getMediaUrlRedirect")
            return None
        
        try:
            is_ready = await self._is_page_ready()
            if not is_ready:
                log.warning("TRPC: Page not on labs.google domain for getMediaUrlRedirect")
                return None
            
            # Use redirect: 'manual' to capture the 302 Location header
            # instead of following the redirect (we need the URL, not the file)
            result = await self._page.evaluate(
                _REDIRECT_FETCH_JS,
                endpoint,
            )
            
            if result is None:
                log.debug("[TRPC-DL] evaluate returned None")
                return None
            
            if isinstance(result, dict) and "__fetch_error__" in result:
                log.warning(f"[TRPC-DL] fetch error: {result['__fetch_error__']}")
                return None
            
            if isinstance(result, dict) and "error" in result:
                log.error(f"[TRPC-DL] HTTP error: {result['error']}")
                return None
            
            if isinstance(result, dict):
                url = result.get("url")
                status = result.get("status", 0)
                log.debug(f"[TRPC-DL] status={status}, url={url[:100] if url else 'None'}...")
                
                if url and ("storage.googleapis.com" in url or "googleapis.com" in url):
                    log.info(f"[TRPC-DL] ✅ Got GCS download URL for {op_name[:40]}... ({len(url)} chars)")
                    return url
                elif url:
                    # Redirect to unknown domain — still try it
                    log.info(f"[TRPC-DL] ✅ Got redirect URL for {op_name[:40]}... → {url[:80]}...")
                    return url
                else:
                    log.warning(f"[TRPC-DL] No redirect URL in response (status={status})")
                    return None
            
            log.warning(f"[TRPC-DL] Unexpected response type: {type(result).__name__}")
            return None
            
        except Exception as e:
            log.error(f"TRPC getMediaUrlRedirect failed: {e}")
            return None
    
    async def _trpc_query(
        self,
        url: str,
    ) -> Optional[Dict]:
        """Execute a TRPC GET query via browser's fetch() API with retry.
        
        TRPC queries use GET with URL-encoded input params (unlike mutations which use POST).
        Cookies are auto-attached by the browser context.
        
        Args:
            url: Full TRPC endpoint URL with ?input= query parameter
            
        Returns:
            Parsed JSON response, or None if failed
        """
        if not self._page:
            log.error("TRPC: No page available")
            return None
        
        for attempt in range(MAX_RETRIES):
            try:
                is_ready = await self._is_page_ready()
                if not is_ready:
                    log.warning(f"TRPC: Page not on labs.google domain (attempt {attempt + 1}/{MAX_RETRIES})")
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                        continue
                    return None
                
                result = await self._page.evaluate(
                    _SAFE_QUERY_JS,
                    url
                )
                
                if result is None:
                    log.warning(f"TRPC query: evaluate returned None (attempt {attempt + 1}/{MAX_RETRIES})")
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                        continue
                    return None
                
                if isinstance(result, dict) and "__fetch_error__" in result:
                    error = result["__fetch_error__"]
                    log.warning(f"TRPC query: fetch error (attempt {attempt + 1}/{MAX_RETRIES}): {error}")
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                        continue
                    return None
                
                if isinstance(result, dict) and "error" in result:
                    log.error(f"TRPC: HTTP error: {result['error']}")
                    return None
                
                return result
                
            except Exception as e:
                error_str = str(e).lower()
                if ("greenlet" in error_str or 
                    "cannot switch" in error_str or
                    "context" in error_str or
                    "failed to fetch" in error_str):
                    log.warning(f"TRPC query: Thread/context error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                else:
                    log.error(f"TRPC query page.evaluate failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAYS[attempt])
                    continue
                return None
        
        return None
    
    async def _trpc_fetch(
        self,
        url: str,
        payload: Dict[str, Any],
    ) -> Optional[Dict]:
        """Execute a TRPC POST via browser's fetch() API with retry.
        
        Cookies are auto-attached by the browser context.
        All JS errors are caught inside the evaluate to prevent
        Playwright greenlet crashes.
        
        Args:
            url: Full TRPC endpoint URL
            payload: Request body dict
            
        Returns:
            Parsed JSON response, or None if failed
        """
        if not self._page:
            log.error("TRPC: No page available")
            return None
        
        for attempt in range(MAX_RETRIES):
            try:
                # Step 1: Verify page is on labs.google domain (cookies need same origin)
                is_ready = await self._is_page_ready()
                if not is_ready:
                    log.warning(f"TRPC: Page not on labs.google domain (attempt {attempt + 1}/{MAX_RETRIES})")
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                        continue
                    return None
                
                # Step 2: Execute fetch inside browser context
                # CRITICAL: All errors caught in JS — never throw through Playwright
                result = await self._page.evaluate(
                    _SAFE_FETCH_JS,
                    [url, payload]
                )
                
                # Step 3: Check result
                if result is None:
                    log.warning(f"TRPC: evaluate returned None (attempt {attempt + 1}/{MAX_RETRIES})")
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                        continue
                    return None
                
                if isinstance(result, dict) and "__fetch_error__" in result:
                    error = result["__fetch_error__"]
                    log.warning(
                        f"TRPC: fetch error (attempt {attempt + 1}/{MAX_RETRIES}): {error}"
                    )
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                        continue
                    return None
                
                if isinstance(result, dict) and "error" in result:
                    log.error(f"TRPC: HTTP error: {result['error']}")
                    return None
                
                # Success
                return result
                
            except Exception as e:
                error_str = str(e).lower()
                # Greenlet / context errors — log and retry
                if ("greenlet" in error_str or 
                    "cannot switch" in error_str or
                    "context" in error_str or
                    "failed to fetch" in error_str):
                    log.warning(
                        f"TRPC: Thread/context error (attempt {attempt + 1}/{MAX_RETRIES}): {e}"
                    )
                else:
                    log.error(f"TRPC page.evaluate failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAYS[attempt])
                    continue
                return None
        
        return None
    
    async def _is_page_ready(self) -> bool:
        """Check if page is on labs.google domain (required for cookie auth).
        
        Returns True if the page is on the correct domain, False otherwise.
        """
        try:
            origin = await self._page.evaluate(
                "() => { try { return window.location.origin; } catch(e) { return ''; } }"
            )
            if origin and "labs.google" in str(origin):
                return True
            log.debug(f"TRPC: Page origin is '{origin}', expected labs.google")
            return False
        except Exception:
            return False


# JavaScript for safe fetch — ALL errors caught inside JS, never thrown
# This prevents Playwright greenlet crashes from async JS exceptions.
_SAFE_FETCH_JS = """
    async ([url, body]) => {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 15000);
            
            const response = await fetch(url, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body),
                credentials: 'include',
                signal: controller.signal,
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                const text = await response.text().catch(() => '');
                return {error: `HTTP ${response.status}: ${text}`};
            }
            return await response.json();
        } catch (e) {
            // Return error as data — NEVER throw from async evaluate
            return {"__fetch_error__": e.message || String(e)};
        }
    }
"""

# JavaScript for safe GET query — ALL errors caught inside JS, never thrown
_SAFE_QUERY_JS = """
    async (url) => {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 15000);
            
            const response = await fetch(url, {
                method: 'GET',
                credentials: 'include',
                signal: controller.signal,
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                const text = await response.text().catch(() => '');
                return {error: `HTTP ${response.status}: ${text}`};
            }
            return await response.json();
        } catch (e) {
            return {"__fetch_error__": e.message || String(e)};
        }
    }
"""

# JavaScript for redirect-based download URL fetch
# media.getMediaUrlRedirect returns HTTP 302 → GCS signed URL
# Strategy: try redirect:'manual' for Location header; fallback to follow + abort
_REDIRECT_FETCH_JS = """
    async (url) => {
        try {
            // F12 Analysis: media.getMediaUrlRedirect is a DOCUMENT navigation,
            // NOT a CORS fetch. Browser sends minimal headers (no cookies, no credentials).
            // The server responds with 302 → GCS signed URL.
            
            // Pass 1: fetch WITHOUT credentials (matching F12 behavior)
            // F12 shows: no cookies, no content-type, just sec-ch-ua headers
            try {
                const controller1 = new AbortController();
                const t1 = setTimeout(() => controller1.abort(), 15000);
                const resp1 = await fetch(url, {
                    method: 'GET',
                    credentials: 'omit',
                    redirect: 'follow',
                    signal: controller1.signal,
                });
                const finalUrl = resp1.url;
                controller1.abort();
                
                if (finalUrl && finalUrl !== url) {
                    return {status: resp1.status || 302, url: finalUrl, method: 'no-cred-follow'};
                }
                
                // If it didn't redirect, check if response is JSON with URL
                if (resp1.ok) {
                    try {
                        const data = await resp1.json();
                        if (data && data.url) return {status: resp1.status, url: data.url, method: 'json'};
                    } catch(e) {}
                }
            } catch(e1) {
                // May fail with CORS — try next
            }
            
            // Pass 2: fetch with redirect:'manual' + no credentials
            try {
                const controller2 = new AbortController();
                const t2 = setTimeout(() => controller2.abort(), 10000);
                const resp2 = await fetch(url, {
                    method: 'GET',
                    credentials: 'omit',
                    redirect: 'manual',
                    signal: controller2.signal,
                });
                clearTimeout(t2);
                
                if (resp2.status >= 300 && resp2.status < 400) {
                    const loc = resp2.headers.get('Location');
                    if (loc) return {status: resp2.status, url: loc, method: 'manual-no-cred'};
                }
            } catch(e2) {}
            
            // Pass 3: Create a hidden <a> link and extract href after click
            // This triggers a real browser navigation request (document-level, not XHR)
            try {
                const result = await new Promise((resolve) => {
                    const iframe = document.createElement('iframe');
                    iframe.style.display = 'none';
                    iframe.sandbox = 'allow-same-origin';
                    document.body.appendChild(iframe);
                    
                    // Listen for iframe load — the final URL should be the GCS URL
                    const timeout = setTimeout(() => {
                        document.body.removeChild(iframe);
                        resolve(null);
                    }, 10000);
                    
                    iframe.onload = function() {
                        clearTimeout(timeout);
                        try {
                            const finalUrl = iframe.contentWindow.location.href;
                            document.body.removeChild(iframe);
                            if (finalUrl && finalUrl !== url && finalUrl !== 'about:blank') {
                                resolve({status: 302, url: finalUrl, method: 'iframe'});
                            } else {
                                resolve(null);
                            }
                        } catch(e) {
                            // Cross-origin — can't read location
                            document.body.removeChild(iframe);
                            resolve(null);
                        }
                    };
                    
                    iframe.src = url;
                });
                
                if (result && result.url) return result;
            } catch(e3) {}
            
            // Pass 4: XMLHttpRequest without credentials
            try {
                const xhrResult = await new Promise((resolve) => {
                    const xhr = new XMLHttpRequest();
                    xhr.open('GET', url, true);
                    // NO withCredentials — matching F12 behavior
                    
                    xhr.onreadystatechange = function() {
                        if (xhr.readyState >= 2) {
                            const finalUrl = xhr.responseURL;
                            xhr.abort();
                            if (finalUrl && finalUrl !== url) {
                                resolve({status: xhr.status || 302, url: finalUrl, method: 'xhr'});
                            } else {
                                resolve(null);
                            }
                        }
                    };
                    xhr.onerror = function() { resolve(null); };
                    xhr.ontimeout = function() { resolve(null); };
                    xhr.timeout = 10000;
                    xhr.send();
                });
                
                if (xhrResult && xhrResult.url) return xhrResult;
            } catch(e4) {}
            
            return {error: 'No redirect URL found (tried no-cred-follow + manual + iframe + xhr)'};
        } catch (e) {
            return {"__fetch_error__": e.message || String(e)};
        }
    }
"""

