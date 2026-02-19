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
- project.getProjects: POST /fx/api/trpc/project.getProjects

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
        title: str = "VEO Pro Max",
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
    
    async def get_projects(
        self,
        tool_name: str = TOOL_FLOW,
    ) -> list:
        """List all projects via TRPC.
        
        Per Protocol Analysis §3.2.1:
          POST /fx/api/trpc/project.getProjects
          Body: {"json": {"toolName": "PINHOLE"}}
        
        Args:
            tool_name: "PINHOLE" or "BACKBONE"
            
        Returns:
            List of project dicts, or empty list if failed
        """
        endpoint = f"{TRPC_BASE}/project.getProjects"
        payload = {
            "json": {
                "toolName": tool_name,
            }
        }
        
        try:
            result = await self._trpc_fetch(endpoint, payload)
            if not result:
                return []
            
            projects = (
                result
                .get("result", {})
                .get("data", {})
                .get("json", {})
                .get("result", {})
                .get("projects", [])
            )
            
            log.info(f"TRPC: Found {len(projects)} projects")
            return projects
            
        except Exception as e:
            log.error(f"TRPC getProjects failed: {e}")
            return []
    
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
