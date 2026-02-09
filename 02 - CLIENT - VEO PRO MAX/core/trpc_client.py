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
"""

from typing import Optional, Dict, Any
import json
import logging

log = logging.getLogger(__name__)

# TRPC base URL (labs.google, NOT aisandbox-pa)
TRPC_BASE = "https://labs.google/fx/api/trpc"

# Tool names per Protocol Analysis
TOOL_FLOW = "PINHOLE"       # Flow = Image generation
TOOL_WHISK = "BACKBONE"     # Whisk = References


class TRPCClient:
    """Execute TRPC calls via persistent browser page.
    
    Uses page.evaluate(fetch(...)) to send requests from
    the browser context where session cookies are available.
    
    Usage:
        client = TRPCClient(page)
        project_id = await client.create_project("My Project")
    """
    
    def __init__(self, page):
        """Initialize with a Playwright Page from RecaptchaBrowserSession.
        
        Args:
            page: Playwright page object with active session cookies.
                  Obtained from RecaptchaBrowserSession._page.
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
        """Execute a TRPC POST via browser's fetch() API.
        
        Cookies are auto-attached by the browser context.
        This is the key difference from aisandbox-pa REST calls
        which use x-browser-* headers but no cookies.
        
        Args:
            url: Full TRPC endpoint URL
            payload: Request body dict
            
        Returns:
            Parsed JSON response, or None if failed
        """
        if not self._page:
            log.error("TRPC: No page available")
            return None
        
        # Execute fetch inside browser context — cookies auto-attached
        js_code = """
            async ([url, body]) => {
                const response = await fetch(url, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(body),
                    credentials: 'include',
                });
                if (!response.ok) {
                    return {error: `HTTP ${response.status}: ${await response.text()}`};
                }
                return await response.json();
            }
        """
        
        try:
            result = await self._page.evaluate(js_code, [url, payload])
            
            if isinstance(result, dict) and "error" in result:
                log.error(f"TRPC fetch error: {result['error']}")
                return None
            
            return result
            
        except Exception as e:
            log.error(f"TRPC page.evaluate failed: {e}")
            return None
