"""
VEO Pro Max - Project Manager

Reference: PROJECT_MANAGEMENT.md, ARCHITECTURE_OVERVIEW.md
Role: Manages VEO project lifecycle (create/get/cache project IDs)
"""

from typing import Optional, Dict
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class ProjectManager:
    """Manages VEO project creation and caching.
    
    Each account (CHỦ) needs a project_id for certain API calls (T2I, etc).
    This class handles:
    - Creating new projects via API
    - Caching project IDs per email
    - Reusing existing project IDs
    """
    
    def __init__(self):
        self._project_cache: Dict[str, str] = {}  # email → project_id
        self._lock = asyncio.Lock()
    
    async def get_or_create_project(
        self,
        email: str,
        access_token: str = "",
        api_client=None,
        trpc_client=None,
    ) -> Optional[str]:
        """Get cached project ID or create a new one.
        
        Args:
            email: Account email (cache key)
            access_token: Kept for signature compat (not used by TRPC)
            api_client: Legacy param (unused — TRPC doesn't go through REST)
            trpc_client: TRPCClient instance from AccountManager's browser session
        
        Returns:
            project_id string, or None if creation failed
        """
        # Check cache first
        if email in self._project_cache:
            return self._project_cache[email]
        
        # Create new project via TRPC
        async with self._lock:
            # Double-check after acquiring lock
            if email in self._project_cache:
                return self._project_cache[email]
            
            project_id = await self._create_project(trpc_client)
            
            if project_id:
                self._project_cache[email] = project_id
            
            return project_id
    
    async def _create_project(
        self,
        trpc_client=None,
    ) -> Optional[str]:
        """Create a new VEO project via TRPC.
        
        Per VEO_Web_Client_Protocol_Analysis.md §3.2.1:
          POST /fx/api/trpc/project.createProject
          Host: labs.google
          Content-Type: application/json
          Auth: Cookies (browser session, NOT Bearer token)
          Body: {"json":{"projectTitle":"...","toolName":"PINHOLE"}}
        
        Response: {"result":{"data":{"json":{"result":{"projectId":"uuid"}}}}}
        
        Uses TRPCClient which executes fetch() inside the browser context
        where session cookies are auto-attached.
        """
        if not trpc_client:
            return None
        
        try:
            return await trpc_client.create_project(title="VEO Pro Max")
        except Exception:
            return None
    
    def set_project_id(self, email: str, project_id: str):
        """Manually set a project ID for an account."""
        self._project_cache[email] = project_id
    
    def get_cached_project_id(self, email: str) -> Optional[str]:
        """Get cached project ID without creating."""
        return self._project_cache.get(email)
    
    def clear_cache(self, email: Optional[str] = None):
        """Clear project cache.
        
        Args:
            email: Clear specific account, or all if None
        """
        if email:
            self._project_cache.pop(email, None)
        else:
            self._project_cache.clear()
