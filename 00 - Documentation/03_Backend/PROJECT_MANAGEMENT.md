# 📁 Project Management

**Location**: `03_Backend/PROJECT_MANAGEMENT.md`  
**Status**: ACTIVE  
**Last Updated**: 2026-02-03

---

## 1. Overview

VEO API yêu cầu `projectId` cho mọi operation. Mỗi tài khoản có thể có nhiều projects.

### 1.1 Project trong API

```
All endpoints use: /v1/projects/{projectId}/flowMedia:...

Example:
POST /v1/projects/f5db1342-c676-437b-b763-d97ae2d7cd16/flowMedia:batchAsyncGenerateVideoText
```

### 1.2 Role Assignment với Project

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     PROJECT IN ROLE HIERARCHY                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │                    ĐẠI CHỦ (MultiAccountManager)                 │        │
│  │                                                                  │        │
│  │  ❌ KHÔNG quản lý Project                                        │        │
│  │  ✓ Chỉ quản lý N accounts và load balancing                      │        │
│  │                                                                  │        │
│  └──────────────────────────────┬───────────────────────────────────┘        │
│                                 │                                            │
│         ┌───────────────────────┼───────────────────────────────┐           │
│         ▼                       ▼                               ▼           │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐    │
│  │ CHỦ 1              │  │ CHỦ 2              │  │ CHỦ 3              │    │
│  │ (AccountManager)   │  │ (AccountManager)   │  │ (AccountManager)   │    │
│  │                    │  │                    │  │                    │    │
│  │ ✅ QUẢN LÝ PROJECT │  │ ✅ QUẢN LÝ PROJECT │  │ ✅ QUẢN LÝ PROJECT │    │
│  │ ┌────────────────┐ │  │ ┌────────────────┐ │  │ ┌────────────────┐ │    │
│  │ │ProjectManager  │ │  │ │ProjectManager  │ │  │ │ProjectManager  │ │    │
│  │ │ ID: f5db1342.. │ │  │ │ ID: a3bc5678.. │ │  │ │ ID: 78901234.. │ │    │
│  │ └────────────────┘ │  │ └────────────────┘ │  │ └────────────────┘ │    │
│  │                    │  │                    │  │                    │    │
│  └────────────────────┘  └────────────────────┘  └────────────────────┘    │
│                                                                              │
│  ═══════════════════════════════════════════════════════════════════════    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │                        THẦU (Dispatcher)                         │        │
│  │                                                                  │        │
│  │  ✓ Lấy project_id từ CHỦ khi dispatch                           │        │
│  │  ✓ Gửi project_id cho THỢ                                        │        │
│  │                                                                  │        │
│  └──────────────────────────────┬───────────────────────────────────┘        │
│                                 │                                            │
│                                 ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │                        THỢ (Worker)                              │        │
│  │                                                                  │        │
│  │  ✓ Sử dụng project_id trong API calls                           │        │
│  │  api.generate(project_id=..., prompt=..., auth=...)              │        │
│  │                                                                  │        │
│  └─────────────────────────────────────────────────────────────────┘        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Project Lifecycle

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          PROJECT LIFECYCLE                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────┐                                                           │
│   │ Account Login│                                                           │
│   └──────┬───────┘                                                           │
│          │                                                                   │
│          ▼                                                                   │
│   ┌───────────────────────────────────────────────────────────────────┐     │
│   │                    CHỦ.ProjectManager.initialize()                 │     │
│   │                                                                    │     │
│   │   1. List existing projects                                        │     │
│   │   2. If projects exist → Use first one                             │     │
│   │   3. If no projects → Auto-create with default name               │     │
│   │                                                                    │     │
│   └──────────────────────────────┬───────────────────────────────────┘     │
│                                  │                                          │
│                                  ▼                                          │
│   ┌───────────────────────────────────────────────────────────────────┐     │
│   │              PROJECT READY FOR USE                                 │     │
│   │                                                                    │     │
│   │   project_id = "f5db1342-c676-437b-b763-..."                       │     │
│   │                                                                    │     │
│   └───────────────────────────────────────────────────────────────────┘     │
│                                  │                                          │
│                                  ▼                                          │
│   ┌───────────────────────────────────────────────────────────────────┐     │
│   │                     USE IN ALL API CALLS                           │     │
│   │                                                                    │     │
│   │   • Generate Video (T2V, I2V, R2V, F2V)                           │     │
│   │   • Generate Image (T2I, I2I)                                      │     │
│   │   • Upscale Video/Image                                            │     │
│   │   • Check Status                                                   │     │
│   │   • List Media                                                     │     │
│   │                                                                    │     │
│   └───────────────────────────────────────────────────────────────────┘     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Cross-Account/Project Support

### 3.1 Tại sao hoạt động được?

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 CROSS-ACCOUNT + CROSS-PROJECT CONTINUATION                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ╔═══════════════════════════════════════════════════════════════════════╗  │
│  ║                                                                        ║  │
│  ║  KEY INSIGHT: Frame extraction là LOCAL OPERATION                      ║  │
│  ║                                                                        ║  │
│  ║  video_p1.mp4 → extract_frame() → frame_p1.png                        ║  │
│  ║                                                                        ║  │
│  ║  ❌ No account needed                                                  ║  │
│  ║  ❌ No project needed                                                  ║  │
│  ║  ❌ No API call                                                        ║  │
│  ║  ✅ Just local file I/O                                                ║  │
│  ║                                                                        ║  │
│  ╚═══════════════════════════════════════════════════════════════════════╝  │
│                                                                              │
│  Consequence:                                                                │
│  • Frame file không thuộc về account/project nào                            │
│  • Bất kỳ account nào cũng có thể upload frame local                        │
│  • Continuation chain có thể chạy cross-account/project                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Cross-Account Continuation Example

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  ACCOUNT A                           ACCOUNT B                               │
│  Project: "f5db1342..."              Project: "a3bc5678..."                  │
│  ┌─────────────────────┐            ┌─────────────────────┐                 │
│  │                     │            │                     │                 │
│  │ P1: "Girl dancing"  │            │ P2: ">> She spins"  │                 │
│  │       │             │            │       ▲             │                 │
│  │       ▼             │            │       │             │                 │
│  │ video_p1.mp4        │            │ Uses: frame_p1.png  │                 │
│  │       │             │            │       │             │                 │
│  └───────┼─────────────┘            └───────┼─────────────┘                 │
│          │                                  │                                │
│          │    ┌─────────────────────┐       │                                │
│          └───►│   LOCAL MACHINE     │───────┘                                │
│               │                     │                                        │
│               │ frame_p1.png        │   ← File local, không ownership        │
│               └─────────────────────┘                                        │
│                                                                              │
│  FLOW:                                                                       │
│  1. P1 generate → Account A, Project A                                       │
│  2. Download video_p1.mp4 → local                                            │
│  3. Extract frame → frame_p1.png (local, no account/project)                │
│  4. P2 upload frame → Account B, Project B                                   │
│  5. P2 generate → Account B, Project B                                       │
│                                                                              │
│  ✅ CROSS-ACCOUNT + CROSS-PROJECT SUCCESS!                                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Implementation

### 4.1 ProjectManager Class

```python
from dataclasses import dataclass
from typing import Optional, List
import asyncio

@dataclass
class Project:
    id: str
    display_name: str
    create_time: Optional[str] = None

class ProjectManager:
    """
    Quản lý VEO projects cho một CHỦ (AccountManager).
    
    Responsibilities:
    - Get/Create/List projects
    - Cache current project ID
    - Auto-create project nếu chưa có
    """
    
    def __init__(self, session: AccountSession, api_client):
        self.session = session
        self.api = api_client
        self._current_project: Optional[Project] = None
        self._projects_cache: List[Project] = []
    
    async def get_or_create_project(self) -> str:
        """
        Get current project or create one if none exists.
        
        Flow:
        1. Check cache
        2. List projects from API
        3. If none, create new
        4. Return project ID
        """
        # Check cache
        if self._current_project:
            return self._current_project.id
        
        # List existing projects
        projects = await self.list_projects()
        
        if projects:
            # Use first project
            self._current_project = projects[0]
            return self._current_project.id
        
        # No projects, create one
        project_id = await self.create_project("VEO Pro Max Project")
        self._current_project = Project(
            id=project_id, 
            display_name="VEO Pro Max Project"
        )
        
        return project_id
    
    async def list_projects(self) -> List[Project]:
        """List all projects for the account."""
        url = "https://aisandbox-pa.googleapis.com/v1/projects"
        
        headers = {"Authorization": f"Bearer {self.session.auth_token}"}
        
        async with aiohttp.ClientSession() as client:
            async with client.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._projects_cache = [
                        Project(
                            id=p['name'].split('/')[-1],
                            display_name=p.get('displayName', 'Unnamed'),
                            create_time=p.get('createTime')
                        )
                        for p in data.get('projects', [])
                    ]
                    return self._projects_cache
                return []
    
    async def create_project(self, name: str) -> str:
        """Create new project."""
        url = "https://aisandbox-pa.googleapis.com/v1/projects"
        
        headers = {
            "Authorization": f"Bearer {self.session.auth_token}",
            "Content-Type": "application/json"
        }
        payload = {"displayName": name}
        
        async with aiohttp.ClientSession() as client:
            async with client.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data['name'].split('/')[-1]
                raise Exception(f"Create project failed: {resp.status}")
    
    async def switch_project(self, project_id: str):
        """Switch to a different project."""
        projects = await self.list_projects()
        
        for p in projects:
            if p.id == project_id:
                self._current_project = p
                return
        
        raise ValueError(f"Project not found: {project_id}")
    
    @property
    def current_project_id(self) -> Optional[str]:
        return self._current_project.id if self._current_project else None
```

### 4.2 Integration với AccountManager (CHỦ)

```python
class AccountManager:
    """
    CHỦ: Mỗi account có 1 ProjectManager.
    """
    
    MAX_SLOTS = 4
    
    def __init__(
        self, 
        session: AccountSession, 
        browser_manager, 
        api_client
    ):
        self.session = session
        self.browser = browser_manager
        self.api = api_client
        
        # Project management - CHỦ quản lý Project
        self.projects = ProjectManager(session, api_client)
        
        # Slots
        self._slot_semaphore = asyncio.Semaphore(self.MAX_SLOTS)
        self._active_count = 0
    
    async def initialize(self) -> str:
        """
        Initialize account: ensure project exists.
        Called once when account connects.
        """
        project_id = await self.projects.get_or_create_project()
        return project_id
    
    async def get_project_id(self) -> str:
        """Get current project ID (auto-create if needed)."""
        return await self.projects.get_or_create_project()
    
    # ... rest of AccountManager methods
```

### 4.3 Integration với Dispatcher (THẦU)

```python
class Dispatcher:
    """
    THẦU: Lấy project_id từ CHỦ khi dispatch.
    """
    
    async def _execute_task(
        self, 
        task: Task, 
        account: AccountManager
    ) -> str:
        """Execute task trên specific account."""
        
        # Get project_id từ CHỦ
        project_id = await account.get_project_id()
        
        # Get reCAPTCHA token từ CHỦ
        token = await account.get_recaptcha_token()
        
        # Execute with project context
        result = await self._run_worker(task, account, project_id, token)
        
        return result
    
    async def _run_worker(
        self,
        task: Task,
        account: AccountManager,
        project_id: str,
        token: str
    ) -> str:
        """THỢ thực thi - sử dụng project_id từ CHỦ."""
        
        # Upload images
        image_ids = []
        for img_path in task.images:
            img_id = await self.api.upload_image(
                file=img_path,
                auth=account.session,
                recaptcha=token
            )
            image_ids.append(img_id)
        
        # Upload continuation frame if exists
        if task.continuation_frame:
            frame_id = await self.api.upload_image(
                file=task.continuation_frame,  # Local file!
                auth=account.session,           # Current account
                recaptcha=token
            )
            image_ids.insert(0, frame_id)
        
        # Generate using project_id
        operation_id = await self.api.generate(
            project_id=project_id,  # ← From CHỦ
            prompt=task.prompt,
            task_type=task.task_type,
            image_ids=image_ids,
            auth=account.session,
            recaptcha=token
        )
        
        # Poll and return
        # ...
```

---

## 5. Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PROJECT DATA FLOW                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. Task Submitted                                                           │
│     │                                                                        │
│     ▼                                                                        │
│  2. THẦU: "Need account for this task"                                       │
│     │                                                                        │
│     └──► ĐẠI CHỦ.get_available_account()                                    │
│           │                                                                  │
│           ▼                                                                  │
│     Return: AccountManager (CHỦ 2)                                           │
│     │                                                                        │
│     ▼                                                                        │
│  3. THẦU: "Need project_id for this account"                                 │
│     │                                                                        │
│     └──► CHỦ 2.get_project_id()                                             │
│           │                                                                  │
│           └──► CHỦ 2.projects.get_or_create_project()                       │
│                 │                                                            │
│                 ▼                                                            │
│           Return: "a3bc5678-..."                                             │
│     │                                                                        │
│     ▼                                                                        │
│  4. THẦU: "Dispatch to THỢ"                                                  │
│     │                                                                        │
│     └──► THỢ.execute(                                                       │
│               task=task,                                                     │
│               account=CHỦ 2,                                                 │
│               project_id="a3bc5678-..."                                      │
│           )                                                                  │
│     │                                                                        │
│     ▼                                                                        │
│  5. THỢ: "Call API"                                                          │
│     │                                                                        │
│     └──► api.generate(                                                      │
│               project_id="a3bc5678-...",   ← From CHỦ                       │
│               prompt="...",                                                  │
│               auth=CHỦ 2.session,          ← From CHỦ                       │
│               recaptcha=CHỦ 2.token        ← From CHỦ                       │
│           )                                                                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. UI Integration

### 6.1 Project Display in Queue Table

```
┌────────────────────────────────────────────────────────────────────────────┐
│ 📊 QUEUE MANAGER                                                            │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│ ┌───┬────────────────┬──────────────┬────────────────┬────────┬────────┐  │
│ │ # │ Prompt         │ Account      │ Project        │ Status │ Prog.  │  │
│ ├───┼────────────────┼──────────────┼────────────────┼────────┼────────┤  │
│ │ 1 │ Girl dancing   │ acc1@gmail   │ f5db1342...    │ ✅Done │ 100%   │  │
│ │ 2 │ >> Spins       │ acc2@gmail   │ a3bc5678... ◄─┼─DIFFERENT PROJECT   │
│ │ 3 │ >> Zooms out   │ -            │ -              │ 🔗Wait │ -      │  │
│ │ 4 │ Sunset view    │ acc3@gmail   │ 78901234...    │ 🔄Gen  │ 40%    │  │
│ └───┴────────────────┴──────────────┴────────────────┴────────┴────────┘  │
│                                                                             │
│ Note: Tasks 1 and 2 are continuation chain running on DIFFERENT projects!  │
│       This works because frame is extracted locally.                        │
│                                                                             │
└────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Project Settings (TAB_07)

```
┌────────────────────────────────────────────────────────────────┐
│ 📁 PROJECT SETTINGS                                            │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Per-Account Project Configuration:                              │
│                                                                 │
│ ┌───────────────────────────────────────────────────────────┐  │
│ │ Account: acc1@gmail.com                                   │  │
│ │ ┌─────────────────────────────────────────────────────┐   │  │
│ │ │ Current Project: My VEO Project           [Switch ▼] │   │  │
│ │ │ ID: f5db1342-c676-437b-b763-...                      │   │  │
│ │ └─────────────────────────────────────────────────────┘   │  │
│ └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│ ┌───────────────────────────────────────────────────────────┐  │
│ │ Account: acc2@gmail.com                                   │  │
│ │ ┌─────────────────────────────────────────────────────┐   │  │
│ │ │ Current Project: Marketing Videos        [Switch ▼] │   │  │
│ │ │ ID: a3bc5678-1234-5678-...                           │   │  │
│ │ └─────────────────────────────────────────────────────┘   │  │
│ └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│ Global Settings:                                                │
│ [✓] Auto-create project on first use                           │
│ [ ] Use same project for all accounts                          │
│                                                                 │
│ Default Project Name: [VEO Pro Max Project        ]            │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

---

## 7. Configuration

| Setting | Values | Default | Description |
|---------|--------|---------|-------------|
| `auto_create_project` | On/Off | On | Auto-create nếu chưa có |
| `default_project_name` | String | "VEO Pro Max Project" | Tên project tự động tạo |
| `use_same_project_all_accounts` | On/Off | Off | Dùng chung project (cần thêm logic) |

---

## 8. Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `Invalid projectId` | Project không tồn tại | Re-fetch projects, chọn project mới |
| `No projects found` | Account mới | Auto-create project |
| `Project quota exceeded` | Quá nhiều projects | Delete old hoặc dùng existing |
| `403 Forbidden` | Project không thuộc account | Verify account credentials |

---

## Cross-References

- [MULTITHREADING_ARCHITECTURE.md](./MULTITHREADING_ARCHITECTURE.md) - Role hierarchy & cross-chain flow
- [RECAPTCHA_BROWSER_MANAGEMENT.md](./RECAPTCHA_BROWSER_MANAGEMENT.md) - Token handling
- [TAB_07_SETTINGS.md](../01_UI_UX/TAB_07_SETTINGS.md) - Project settings UI
