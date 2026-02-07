# 🔄 Multi-threading Architecture (ĐẠI CHỦ - CHỦ - THẦU - THỢ Pattern)

**Location**: `03_Backend/MULTITHREADING_ARCHITECTURE.md`  
**Status**: ACTIVE  
**Last Updated**: 2026-02-03

---

## 1. Tổng quan Kiến trúc

### 1.1 Role Hierarchy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ROLE HIERARCHY                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    ĐẠI CHỦ (MultiAccountManager)                     │    │
│  │                                                                      │    │
│  │  • Manages N accounts                                                │    │
│  │  • Load balancing across accounts                                    │    │
│  │  • Total capacity: N × 4 slots                                       │    │
│  │  • ❌ KHÔNG quản lý Projects (delegate cho CHỦ)                      │    │
│  │                                                                      │    │
│  └──────────────────────────────┬───────────────────────────────────────┘    │
│                                 │                                            │
│         ┌───────────────────────┼───────────────────────────────┐           │
│         ▼                       ▼                               ▼           │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐    │
│  │ CHỦ 1              │  │ CHỦ 2              │  │ CHỦ 3              │    │
│  │ (AccountManager)   │  │ (AccountManager)   │  │ (AccountManager)   │    │
│  │                    │  │                    │  │                    │    │
│  │ • Session/Token    │  │ • Session/Token    │  │ • Session/Token    │    │
│  │ • 4 slot limit     │  │ • 4 slot limit     │  │ • 4 slot limit     │    │
│  │ • reCAPTCHA        │  │ • reCAPTCHA        │  │ • reCAPTCHA        │    │
│  │ • ProjectManager ◄─┼──┼─── ✅ QUẢN LÝ PROJECT                      │    │
│  │                    │  │                    │  │                    │    │
│  └────────────────────┘  └────────────────────┘  └────────────────────┘    │
│                                                                              │
│  ═══════════════════════════════════════════════════════════════════════    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        THẦU (Dispatcher)                             │    │
│  │                                                                      │    │
│  │  • Ready/Waiting Queues                                              │    │
│  │  • Dependency tracking                                               │    │
│  │  • Cross-account routing                                             │    │
│  │  • Frame extraction (LOCAL)                                          │    │
│  │  • Get project_id từ CHỦ                                             │    │
│  │                                                                      │    │
│  └──────────────────────────────┬───────────────────────────────────────┘    │
│                                 │                                            │
│    ┌────────┬────────┬────────┬─┴──────┬────────┬────────┬────────┐        │
│    ▼        ▼        ▼        ▼        ▼        ▼        ▼        ▼        │
│  ┌────┐  ┌────┐  ┌────┐  ┌────┐  ┌────┐  ┌────┐  ┌────┐  ┌────┐  ...     │
│  │THỢ1│  │THỢ2│  │THỢ3│  │THỢ4│  │THỢ5│  │THỢ6│  │THỢ7│  │THỢ8│         │
│  │Acc1│  │Acc1│  │Acc1│  │Acc1│  │Acc2│  │Acc2│  │Acc2│  │Acc2│         │
│  └────┘  └────┘  └────┘  └────┘  └────┘  └────┘  └────┘  └────┘         │
│                                                                              │
│  THỢ receives: task + account + project_id → Executes API call             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Role Assignment Table

| Role | Class | Count | Trách nhiệm | Quản lý |
|------|-------|-------|-------------|---------|
| **ĐẠI CHỦ** | `MultiAccountManager` | 1 | Load balancing N accounts | Accounts only |
| **CHỦ** | `AccountManager` | N | Session, 4 slots, reCAPTCHA | **+ ProjectManager** |
| **THẦU** | `Dispatcher` | 1 | Queue, dependency, dispatch | Routing + Frame extraction |
| **THỢ** | Worker task | N×4 | Execute API calls | Uses project_id from CHỦ |

---

## 2. Complete Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              VEO PRO MAX ENGINE                               │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                    ĐẠI CHỦ (MULTI-ACCOUNT MANAGER)                       │ │
│  │                                                                          │ │
│  │  Accounts: 3    Total Slots: [■■■■■■■□□□□□] 7/12 active                 │ │
│  │                                                                          │ │
│  └──────────────────────────────┬───────────────────────────────────────────┘ │
│                                 │                                             │
│         ┌───────────────────────┼───────────────────────────────┐            │
│         ▼                       ▼                               ▼            │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐     │
│  │ CHỦ 1              │  │ CHỦ 2              │  │ CHỦ 3              │     │
│  │ acc1@gmail.com     │  │ acc2@gmail.com     │  │ acc3@gmail.com     │     │
│  │                    │  │                    │  │                    │     │
│  │ ┌────────────────┐ │  │ ┌────────────────┐ │  │ ┌────────────────┐ │     │
│  │ │ProjectManager  │ │  │ │ProjectManager  │ │  │ │ProjectManager  │ │     │
│  │ │                │ │  │ │                │ │  │ │                │ │     │
│  │ │ Project:       │ │  │ │ Project:       │ │  │ │ Project:       │ │     │
│  │ │ "f5db1342..."  │ │  │ │ "a3bc5678..."  │ │  │ │ "78901234..."  │ │     │
│  │ └────────────────┘ │  │ └────────────────┘ │  │ └────────────────┘ │     │
│  │                    │  │                    │  │                    │     │
│  │ Slots: [■■□□] 2/4  │  │ Slots: [■■■■] 4/4  │  │ Slots: [■□□□] 1/4  │     │
│  │ Token: ✅ Valid    │  │ Token: ✅ Valid    │  │ Token: ⚠️ Expired  │     │
│  └────────────────────┘  └────────────────────┘  └────────────────────┘     │
│                                                                               │
│  ══════════════════════════════════════════════════════════════════════════  │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                         THẦU (DISPATCHER)                                │ │
│  │                                                                          │ │
│  │  Ready Queue:   [P4, P6, P9, P10, P11...]    ← No dependency             │ │
│  │  Waiting Queue: [P5←P4, P7←P6, P8←P7]        ← Has dependency            │ │
│  │                                                                          │ │
│  │  Dependency Map:                                                         │ │
│  │  ┌────────────────────────────────────────────────────────────────────┐ │ │
│  │  │  P4 ──► P5                                                         │ │ │
│  │  │  P6 ──► P7 ──► P8                                                  │ │ │
│  │  └────────────────────────────────────────────────────────────────────┘ │ │
│  │                                                                          │ │
│  │  Frame Cache (LOCAL):                                                    │ │
│  │  ┌────────────────────────────────────────────────────────────────────┐ │ │
│  │  │  temp/frame_P1.png ← Extracted from video_P1.mp4                   │ │ │
│  │  │  temp/frame_P2.png ← Extracted from video_P2.mp4                   │ │ │
│  │  └────────────────────────────────────────────────────────────────────┘ │ │
│  │                                                                          │ │
│  └──────────────────────────────┬───────────────────────────────────────────┘ │
│                                 │                                             │
│         Dispatch to workers     │                                             │
│                                 ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                            THỢ (WORKERS)                                 │ │
│  │                                                                          │ │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐       │ │
│  │  │ THỢ 1   │  │ THỢ 2   │  │ THỢ 3   │  │ THỢ 4   │  │ THỢ 5   │ ...   │ │
│  │  │ Acc1    │  │ Acc1    │  │ Acc2    │  │ Acc2    │  │ Acc2    │       │ │
│  │  │ Proj:A  │  │ Proj:A  │  │ Proj:B  │  │ Proj:B  │  │ Proj:B  │       │ │
│  │  │ P1:60%  │  │ P4:40%  │  │ P6:80%  │  │ P9:20%  │  │ P10:10% │       │ │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘  └─────────┘       │ │
│  │                                                                          │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Cross-Account + Cross-Project Continuation

### 3.1 Tại sao hoạt động được?

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CROSS-ACCOUNT/PROJECT SUPPORT                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  KEY INSIGHT: Frame extraction là LOCAL OPERATION                           │
│               Không cần Account, Project, hoặc API Token                     │
│                                                                              │
│  ╔═══════════════════════════════════════════════════════════════════════╗  │
│  ║                                                                        ║  │
│  ║  video_p1.mp4 (local) ──► moviepy.extract() ──► frame_p1.png (local)  ║  │
│  ║                                                                        ║  │
│  ║  No API call needed. No account needed. Just local file processing.   ║  │
│  ║                                                                        ║  │
│  ╚═══════════════════════════════════════════════════════════════════════╝  │
│                                                                              │
│  Consequence: Bất kỳ account/project nào cũng có thể upload frame local    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Step-by-Step Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CROSS-CHAIN CONTINUATION FLOW                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─── STEP 1: P1 runs on Account A ───────────────────────────────────────┐ │
│  │                                                                         │ │
│  │  THẦU: "P1 không dependency, CHỦ 1 có slot"                             │ │
│  │      │                                                                  │ │
│  │      ▼                                                                  │ │
│  │  THỢ 1 (Account A, Project A):                                         │ │
│  │      │                                                                  │ │
│  │      └──► api.generate(                                                │ │
│  │               project_id="f5db1342...",   ← Project A                  │ │
│  │               prompt="Girl dancing",                                    │ │
│  │               auth=account_a.session                                   │ │
│  │           )                                                             │ │
│  │      │                                                                  │ │
│  │      ▼                                                                  │ │
│  │  Result: video_p1.mp4 (downloaded to local)                            │ │
│  │                                                                         │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                 │                                            │
│                                 ▼                                            │
│  ┌─── STEP 2: Frame extraction (LOCAL) ───────────────────────────────────┐ │
│  │                                                                         │ │
│  │  THẦU: "P1 done, extract frame"                                         │ │
│  │      │                                                                  │ │
│  │      └──► frame_extractor.extract(                                     │ │
│  │               video="video_p1.mp4",      ← Local file                  │ │
│  │               output="temp/frame_p1.png"                               │ │
│  │           )                                                             │ │
│  │      │                                                                  │ │
│  │      │   ╔═════════════════════════════════════════════════════════╗   │ │
│  │      │   ║  ❌ No account needed                                    ║   │ │
│  │      │   ║  ❌ No project needed                                    ║   │ │
│  │      │   ║  ❌ No API call                                          ║   │ │
│  │      │   ║  ✅ Just local file I/O                                  ║   │ │
│  │      │   ╚═════════════════════════════════════════════════════════╝   │ │
│  │      │                                                                  │ │
│  │      ▼                                                                  │ │
│  │  Result: temp/frame_p1.png (local file, no ownership)                  │ │
│  │                                                                         │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                 │                                            │
│                                 ▼                                            │
│  ┌─── STEP 3: Move P2 to Ready Queue ─────────────────────────────────────┐ │
│  │                                                                         │ │
│  │  THẦU: "P2 depends on P1, P1 done → Move P2 to Ready"                   │ │
│  │      │                                                                  │ │
│  │      └──► P2.continuation_frame = "temp/frame_p1.png"                  │ │
│  │      └──► waiting_queue.remove(P2)                                     │ │
│  │      └──► ready_queue.add(P2)                                          │ │
│  │                                                                         │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                 │                                            │
│                                 ▼                                            │
│  ┌─── STEP 4: P2 runs on Account B ───────────────────────────────────────┐ │
│  │                                                                         │ │
│  │  THẦU: "P2 ready, ai có slot?"                                          │ │
│  │      │                                                                  │ │
│  │      ├──► CHỦ 1: 1/4 slots                                             │ │
│  │      ├──► CHỦ 2: 2/4 slots ← MOST AVAILABLE                            │ │
│  │      └──► CHỦ 3: 3/4 slots                                             │ │
│  │      │                                                                  │ │
│  │      ▼                                                                  │ │
│  │  THẦU: "Dispatch P2 to CHỦ 2"                                           │ │
│  │      │                                                                  │ │
│  │      ▼                                                                  │ │
│  │  THỢ 5 (Account B, Project B):                                         │ │
│  │      │                                                                  │ │
│  │      ├──► 1. Upload frame_p1.png                                       │ │
│  │      │       api.upload(                                               │ │
│  │      │           file="temp/frame_p1.png",  ← Local file               │ │
│  │      │           auth=account_b.session,     ← Account B credentials   │ │
│  │      │           recaptcha=account_b.token   ← Account B token         │ │
│  │      │       )                                                          │ │
│  │      │                                                                  │ │
│  │      └──► 2. Generate P2                                               │ │
│  │              api.generate(                                              │ │
│  │                  project_id="a3bc5678...",   ← Project B (not A!)      │ │
│  │                  prompt="She spins around",                             │ │
│  │                  image_ids=[uploaded_frame],                            │ │
│  │                  auth=account_b.session                                 │ │
│  │              )                                                          │ │
│  │      │                                                                  │ │
│  │      ▼                                                                  │ │
│  │  Result: video_p2.mp4 ✅                                                │ │
│  │                                                                         │ │
│  │  ╔═════════════════════════════════════════════════════════════════╗   │ │
│  │  ║  P1: Account A, Project A                                        ║   │ │
│  │  ║  P2: Account B, Project B                                        ║   │ │
│  │  ║  Frame: Local file, uploaded to Project B                        ║   │ │
│  │  ║  ✅ CROSS-ACCOUNT + CROSS-PROJECT SUCCESS!                       ║   │ │
│  │  ╚═════════════════════════════════════════════════════════════════╝   │ │
│  │                                                                         │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA FLOW DIAGRAM                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  USER                                                                        │
│    │                                                                         │
│    │ Add prompts to queue                                                    │
│    ▼                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                              UI                                      │    │
│  │                                                                      │    │
│  │  Queue Manager Table                                                 │    │
│  │  ┌─────┬────────────────┬──────────┬─────────┬────────┬────────┐   │    │
│  │  │ #   │ Prompt         │ Account  │ Project │ Status │ Prog.  │   │    │
│  │  ├─────┼────────────────┼──────────┼─────────┼────────┼────────┤   │    │
│  │  │ 1   │ Girl dancing   │ acc1@    │ ProjA   │ ✅Done │ 100%   │   │    │
│  │  │ 2   │ >> Spins       │ acc2@    │ ProjB   │ 🔄Gen  │ 60%    │   │    │
│  │  │ 3   │ >> Zooms out   │ -        │ -       │ 🔗Wait │ -      │   │    │
│  │  │ 4   │ Sunset view    │ acc3@    │ ProjC   │ 🔄Gen  │ 40%    │   │    │
│  │  └─────┴────────────────┴──────────┴─────────┴────────┴────────┘   │    │
│  │                                                                      │    │
│  └──────────────────────────────┬───────────────────────────────────────┘    │
│                                 │                                            │
│                                 ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         THẦU (Dispatcher)                            │    │
│  │                                                                      │    │
│  │  ┌────────────────────────────────────────────────────────────┐     │    │
│  │  │ 1. Receive task                                            │     │    │
│  │  │ 2. Check dependency → Ready or Waiting queue               │     │    │
│  │  │ 3. If Ready: Request account from ĐẠI CHỦ                  │     │    │
│  │  │ 4. Get project_id from CHỦ.ProjectManager                  │     │    │
│  │  │ 5. Dispatch to THỢ with (task, account, project_id)        │     │    │
│  │  └────────────────────────────────────────────────────────────┘     │    │
│  │                                                                      │    │
│  └──────────────────────────────┬───────────────────────────────────────┘    │
│                                 │                                            │
│         ┌───────────────────────┼───────────────────────┐                   │
│         ▼                       ▼                       ▼                   │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐       │
│  │ ĐẠI CHỦ         │     │ CHỦ             │     │ THỢ             │       │
│  │                 │     │                 │     │                 │       │
│  │ get_available   │     │ get_project_id  │     │ execute(        │       │
│  │ _account()      │────►│ ()              │────►│   task,         │       │
│  │                 │     │                 │     │   account,      │       │
│  │ Returns:        │     │ Returns:        │     │   project_id    │       │
│  │ AccountManager  │     │ "f5db1342..."   │     │ )               │       │
│  │                 │     │                 │     │                 │       │
│  └─────────────────┘     └─────────────────┘     └────────┬────────┘       │
│                                                           │                 │
│                                                           ▼                 │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                            VEO API                                    │  │
│  │                                                                       │  │
│  │  POST /v1/projects/{project_id}/flowMedia:generate                   │  │
│  │       + Authorization: Bearer {account.token}                        │  │
│  │       + reCAPTCHA: {account.recaptcha_token}                         │  │
│  │       + Body: { prompt, images, ... }                                │  │
│  │                                                                       │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. State Machine

### 5.1 Task State Machine

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TASK STATE MACHINE                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                    ┌───────────┐                                             │
│                    │  PENDING  │ ← Task created                              │
│                    └─────┬─────┘                                             │
│                          │                                                   │
│                          ▼                                                   │
│                    ┌───────────────┐                                         │
│                    │ Has dependency?│                                         │
│                    └───────┬───────┘                                         │
│                       │    │                                                 │
│                  NO   │    │ YES                                             │
│                       ▼    ▼                                                 │
│               ┌───────────┐  ┌───────────┐                                  │
│               │   READY   │  │  WAITING  │                                  │
│               │           │  │           │                                  │
│               │ In Ready  │  │ In Waiting│                                  │
│               │ Queue     │  │ Queue     │                                  │
│               └─────┬─────┘  └─────┬─────┘                                  │
│                     │              │                                         │
│                     │              │ [Parent DONE + Frame extracted]         │
│                     │              │                                         │
│                     │              ▼                                         │
│                     │        ┌───────────┐                                   │
│                     │        │   READY   │ ← Move to Ready Queue             │
│                     │        └─────┬─────┘                                   │
│                     │              │                                         │
│                     ▼              ▼                                         │
│               ┌─────────────────────────────┐                               │
│               │ [Slot available]            │                               │
│               │ THẦU dispatches to THỢ      │                               │
│               └──────────────┬──────────────┘                               │
│                              │                                               │
│                              ▼                                               │
│                        ┌───────────┐                                         │
│                        │  RUNNING  │ ← THỢ executing                         │
│                        └─────┬─────┘                                         │
│                              │                                               │
│             ┌────────────────┼────────────────┐                             │
│             ▼                ▼                ▼                             │
│       ┌───────────┐    ┌───────────┐    ┌───────────┐                       │
│       │ COMPLETED │    │   ERROR   │    │ CANCELLED │                       │
│       └─────┬─────┘    └───────────┘    └───────────┘                       │
│             │                                                                │
│             ▼                                                                │
│       ┌─────────────────────────────────────────────┐                       │
│       │ Has children in Waiting Queue?               │                       │
│       └─────────────────────┬───────────────────────┘                       │
│                             │ YES                                            │
│                             ▼                                                │
│       ┌─────────────────────────────────────────────┐                       │
│       │ 1. Extract frame (LOCAL)                    │                       │
│       │ 2. Assign frame to children                 │                       │
│       │ 3. Move children to Ready Queue             │                       │
│       └─────────────────────────────────────────────┘                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Account State Machine

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ACCOUNT STATE MACHINE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│       ┌───────────────┐                                                      │
│       │ DISCONNECTED  │ ← No session                                         │
│       └───────┬───────┘                                                      │
│               │                                                              │
│               │ [Login / Load Profile]                                       │
│               ▼                                                              │
│       ┌───────────────┐                                                      │
│       │  CONNECTING   │ ← Loading browser context                            │
│       └───────┬───────┘                                                      │
│               │                                                              │
│               │ [Session loaded]                                             │
│               ▼                                                              │
│       ┌───────────────┐                                                      │
│       │   CONNECTED   │ ← Has session, no project yet                        │
│       └───────┬───────┘                                                      │
│               │                                                              │
│               │ [Get or Create Project]                                      │
│               ▼                                                              │
│       ┌───────────────┐                                                      │
│       │     READY     │ ← Has session + project                              │
│       │               │                                                      │
│       │ Slots: [□□□□] │ ← Can accept tasks                                   │
│       └───────┬───────┘                                                      │
│               │                                                              │
│               │ [Tasks dispatched]                                           │
│               ▼                                                              │
│       ┌───────────────┐                                                      │
│       │    ACTIVE     │ ← Processing tasks                                   │
│       │               │                                                      │
│       │ Slots: [■■□□] │ ← 2/4 active                                         │
│       └───────┬───────┘                                                      │
│               │                                                              │
│               │ [All tasks done / Pause]                                     │
│               ▼                                                              │
│       ┌───────────────┐                                                      │
│       │     READY     │ ← Back to ready                                      │
│       └───────────────┘                                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Implementation Classes

### 6.1 Class Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CLASS DIAGRAM                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     MultiAccountManager                              │    │
│  ├─────────────────────────────────────────────────────────────────────┤    │
│  │ - accounts: List[AccountManager]                                     │    │
│  │ - _lock: asyncio.Lock                                                │    │
│  ├─────────────────────────────────────────────────────────────────────┤    │
│  │ + total_capacity: int                                                │    │
│  │ + total_available: int                                               │    │
│  │ + get_available_account(): AccountManager                            │    │
│  │ + acquire_any_slot(): AccountManager                                 │    │
│  │ + get_status(): dict                                                 │    │
│  └──────────────────────────────────┬───────────────────────────────────┘    │
│                                     │ 1                                      │
│                                     │                                        │
│                                     │ *                                      │
│                                     ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                       AccountManager                                 │    │
│  ├─────────────────────────────────────────────────────────────────────┤    │
│  │ - session: AccountSession                                            │    │
│  │ - browser: BrowserManager                                            │    │
│  │ - projects: ProjectManager ◄───────────────────────────────────────┐│    │
│  │ - _slot_semaphore: asyncio.Semaphore(4)                             ││    │
│  │ - _active_count: int                                                 ││    │
│  ├─────────────────────────────────────────────────────────────────────┤│    │
│  │ + acquire_slot(): bool                                               ││    │
│  │ + release_slot(): void                                               ││    │
│  │ + get_recaptcha_token(): str                                         ││    │
│  │ + get_project_id(): str ◄──────────────────────────────────────────┘│    │
│  │ + available_slots: int                                               │    │
│  │ + get_status(): dict                                                 │    │
│  └──────────────────────────────────┬───────────────────────────────────┘    │
│                                     │ 1                                      │
│                                     │                                        │
│                                     │ 1                                      │
│                                     ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                       ProjectManager                                 │    │
│  ├─────────────────────────────────────────────────────────────────────┤    │
│  │ - session: AccountSession                                            │    │
│  │ - api: APIClient                                                     │    │
│  │ - _current_project: Project                                          │    │
│  │ - _projects_cache: List[Project]                                     │    │
│  ├─────────────────────────────────────────────────────────────────────┤    │
│  │ + get_or_create_project(): str                                       │    │
│  │ + list_projects(): List[Project]                                     │    │
│  │ + create_project(name): str                                          │    │
│  │ + switch_project(id): void                                           │    │
│  │ + current_project_id: str                                            │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ══════════════════════════════════════════════════════════════════════════ │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         Dispatcher                                   │    │
│  ├─────────────────────────────────────────────────────────────────────┤    │
│  │ - multi_account: MultiAccountManager                                 │    │
│  │ - frame_extractor: FrameExtractor                                    │    │
│  │ - api: APIClient                                                     │    │
│  │ - _ready_queue: PriorityQueue                                        │    │
│  │ - _waiting_queue: Dict[str, Task]                                    │    │
│  │ - _parent_to_children: Dict[str, Set[str]]                           │    │
│  ├─────────────────────────────────────────────────────────────────────┤    │
│  │ + submit_task(task): void                                            │    │
│  │ - _dispatch(): void                                                  │    │
│  │ - _execute_task(task, account): str                                  │    │
│  │ - _resolve_dependencies(parent_id, video_path): void                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Summary: Role Responsibilities

| Role | Quản lý | Nhận từ | Gửi cho | Không làm |
|------|---------|---------|---------|-----------|
| **ĐẠI CHỦ** | N accounts, load balance | UI (start) | CHỦ selection | Project, Task |
| **CHỦ** | Session, 4 slots, **Project** | ĐẠI CHỦ | project_id, token | Task execution |
| **THẦU** | Queues, dependency, frame | UI (tasks) | THỢ dispatch | API calls |
| **THỢ** | Single task execution | THẦU | API calls | Dependency, Queue |

---

## Cross-References

- [PROJECT_MANAGEMENT.md](./PROJECT_MANAGEMENT.md) - Project CRUD operations
- [RECAPTCHA_BROWSER_MANAGEMENT.md](./RECAPTCHA_BROWSER_MANAGEMENT.md) - Token handling
- [ERROR_HANDLING_STRATEGY.md](./ERROR_HANDLING_STRATEGY.md) - Error handling
- [TAB_06_QUEUE_MANAGER.md](../01_UI_UX/TAB_06_QUEUE_MANAGER.md) - Queue UI
