# Kế hoạch: Gemini API Integration + Project Builder — CONSOLIDATED (v5)

> **Cập nhật**: 2026-03-07 — Gộp Phase 1-5 (API) + Phase 6 (Project Builder Tab)
> **Version trước**: v4 (chỉ Phase 1-5)

---

## ✅ Verification Status

| Phase | Module | File | Status |
|-------|--------|------|--------|
| 1 | GeminiKeyManager | `services/gemini_key_manager.py` | ❌ Not started |
| 2 | GeminiClient | `services/gemini_client.py` | ❌ Not started |
| 3 | PromptEnhancer | `core/prompt_enhancer.py` | ❌ Not started |
| 4 | Settings & UI | `config/settings.py` + `tab_settings.py` | ❌ Not started |
| 5 | Engine Integration | `core/engine.py` | ❌ Not started |
| **6** | **Project Builder Tab** | `core/workflow_scanner.py` + `core/project_builder.py` + `ui/tabs/tab_project.py` | ❌ **NEW** |

> Existing `settings.py` at **version 9**, field `auto_enhance_prompt: bool` exists (line 35) — not related to Gemini, just UI toggle. Zero Gemini code in codebase.

---

## Dependency Graph

```mermaid
graph TD
    P1[Phase 1: GeminiKeyManager<br/>Auto API key via browser] --> P4
    P2[Phase 2: GeminiClient<br/>REST API calls] --> P3
    P2 --> P6
    P3[Phase 3: PromptEnhancer<br/>Enhance + Fix Policy] --> P5
    P4[Phase 4: Settings UI<br/>Toggles + Key display] --> P5
    P5[Phase 5: Engine Integration<br/>Pre-submit + Error auto-fix]
    P6[Phase 6: Project Builder Tab<br/>Workflow + Context + Prompts]
    
    P1 -.-> P6
    
    style P2 fill:#4CAF50,color:white
    style P6 fill:#2196F3,color:white
    style P1 fill:#FF9800,color:white
```

**Recommended build order**: `P2 → P1 → P4 → P6 → P3 → P5`

| Priority | Phase | Reason |
|----------|-------|--------|
| 🔴 1st | **Phase 2** GeminiClient | Core dependency — both Phase 6 and Phase 3 need this |
| 🔴 2nd | **Phase 1** GeminiKeyManager | Auto API key — needed before any Gemini call works |
| 🟠 3rd | **Phase 4** Settings UI | Key display + toggles — user sees "AI" section in Settings |
| 🔵 4th | **Phase 6** Project Builder | Can start Semi-Manual immediately; Full Auto when P2 ready |
| 🟢 5th | **Phase 3** PromptEnhancer | Uses P2 client; standalone enhance/fix for existing T2V tabs |
| 🟢 6th | **Phase 5** Engine Integration | Wire enhancer into engine pre-submit + error handler |

---

## Dữ liệu đã xác minh

- **API key tạo thành công**: `AIzaSyCtgaA1MGLSg-DbPJOTAQ4AQKZdQ4oeVZw`
- **Project ID**: `gen-lang-client-0250360601`
- **Project Number**: `467838870661`
- **Display name**: `"GEMINI API FOR AUTO FLOW"`
- **Static x-goog-api-key**: `AIzaSyDdP816MREB3SkjZO04QXbjsigfcI0GWOs`

---

## gRPC-web Service

```
https://alkalimakersuite-pa.clients6.google.com/$rpc/
google.internal.alkali.applications.makersuite.v1.MakerSuiteService
```

### Headers cần thiết (tất cả RPC calls)

```javascript
const HEADERS = {
    'Content-Type': 'application/json+protobuf',
    'x-goog-api-key': 'AIzaSyDdP816MREB3SkjZO04QXbjsigfcI0GWOs',
    'x-goog-authuser': '0',
    'x-user-agent': 'grpc-web-javascript/0.1'
};
// Authorization: SAPISIDHASH tự động từ browser cookies
```

---

## Per-Account Key Isolation

Mỗi tài khoản Google có cookies riêng trong browser profile → RPC calls trả về project/key **của chính account đó**:

```
Account A (gmail_a@gmail.com) → Profile A → cookies A → RPC → Key A (AIzaSy...xxx)
Account B (gmail_b@gmail.com) → Profile B → cookies B → RPC → Key B (AIzaSy...yyy)
```

- `credentials: 'include'` → browser gửi đúng cookies cho đúng account
- `SAPISIDHASH` = `timestamp_SHA1(timestamp + SAPISID + origin)` → tự gen bởi browser mỗi request
- **Không thể lấy nhầm key cross-account**

## Thời điểm Auto-Provision: Ngay khi Add Account

```
Flow cũ:                              Flow mới:
─────────                              ─────────
1. Mở browser profile                 1. Mở browser profile
2. User login Google                  2. User login Google
3. Cài extension                      3. ✨ Navigate aistudio.google.com
4. Chạy VEO                           4. ✨ Auto-provision Gemini key
                                       5. ✨ Save key vào profile settings
                                       6. Cài extension
                                       7. Chạy VEO (key đã sẵn!)
```

### Integration Point — `tab_settings.py`

```python
async def on_account_added(self, email: str, page):
    """Gọi ngay sau khi user login Google thành công."""
    # Navigate to AI Studio để có đúng cookies context
    await page.goto("https://aistudio.google.com/apikey")
    await page.wait_for_load_state("networkidle")

    # Auto-provision
    key = await self.gemini_key_manager.auto_provision(email, page)

    if key:
        self.settings.set_gemini_key(email, key)
        self.show_status(f"✅ Gemini API key đã lưu cho {email}")
    else:
        self.show_manual_key_input(email)
        self.show_status(f"⚠️ Không tự động lấy được. Paste thủ công.")
```

---

## Luồng Auto-Provision (6 bước — đã xác minh từ HAR)

```mermaid
sequenceDiagram
    participant APP as VEO App (Python)
    participant P as page.evaluate (Browser)
    participant R as MakerSuiteService

    Note over APP: User vừa login Google xong

    APP->>P: Navigate aistudio.google.com/apikey

    rect rgb(230, 245, 230)
        Note over APP: Bước 0: Check saved key
        APP->>APP: load_key(email) → cached?
        alt Đã có key saved
            APP-->>APP: return saved_key ✅ DONE
        end
    end

    rect rgb(230, 235, 250)
        Note over P,R: Bước 1: List Projects
        P->>R: ListCloudProjects([null,null,null,1,null,null])
        R-->>P: [[project_id, number, name, ...]]
    end

    alt Chưa có project
        rect rgb(255, 240, 230)
            Note over P,R: Bước 1b: Tạo Project (cần TOKEN)
            P->>P: Extract TOKEN từ page context
            P->>R: CreateCloudProject([TOKEN, "VEO-ProMax"])
            R-->>P: project_id, project_number
        end
    end

    rect rgb(230, 235, 250)
        Note over P,R: Bước 2: List API Keys (check tồn tại)
        P->>R: ListCloudApiKeys([100,null,1,["projects/{number}"]])
        R-->>P: [[key_info]] hoặc []
    end

    alt Chưa có key
        rect rgb(255, 240, 230)
            Note over P,R: Bước 3: Tạo API Key (cần TOKEN)
            P->>P: Re-extract TOKEN (thay đổi mỗi lần!)
            P->>R: GenerateCloudApiKey([project_id, TOKEN, null, "VEO-ProMax"])
            R-->>P: AIzaSy...
        end

        rect rgb(230, 235, 250)
            Note over P,R: Bước 4: Re-check (confirm key tồn tại)
            P->>R: ListCloudApiKeys([100,null,1,["projects/{number}"]])
            R-->>P: [[key_info]] ← confirm
        end
    end

    rect rgb(230, 245, 230)
        Note over APP: Bước 5: Save encrypted per-profile
        P-->>APP: {key: "AIzaSy...", source: "existing"|"created"}
        APP->>APP: save_key(email, key) → ~/.veoauto/gemini_keys.json
    end
```

> [!WARNING]
> **TOKEN thay đổi mỗi lần gọi** — từ HAR: CreateCloudProject dùng `!jI-lj9fNAA...`, GenerateCloudApiKey dùng `!8fKl8qrNAA...`. Phải re-extract từ page context mỗi lần, KHÔNG cache.

### Bước 1: ListCloudProjects

```javascript
// Request
fetch(RPC_BASE + '/ListCloudProjects', {
    method: 'POST',
    credentials: 'include',
    headers: HEADERS,
    body: JSON.stringify([null, null, null, 1, null, null])
})
// Response: array chứa project info
// Cần parse response để lấy project_number
```

### Bước 1b: CreateCloudProject (nếu chưa có project)

```javascript
// Request — từ HAR line 146–180
fetch(RPC_BASE + '/CreateCloudProject', {
    method: 'POST',
    credentials: 'include',
    headers: HEADERS,
    body: JSON.stringify([TOKEN, "VEO-ProMax"])
})
// TOKEN là giá trị dài từ page context
// Response: project_id + project_number
```

### Bước 2: ListCloudApiKeys

```javascript
// Request — từ HAR line 216–250
fetch(RPC_BASE + '/ListCloudApiKeys', {
    method: 'POST',
    credentials: 'include',
    headers: HEADERS,
    body: JSON.stringify([100, null, 1, ["projects/467838870661"]])
    //                     ^^^             ^^^^^^^^^^^^^^^^^^^^
    //                     limit           project_number từ Step 1
})
// Response: array of key objects hoặc empty
```

### Bước 3: GenerateCloudApiKey

```javascript
// Request — từ HAR line 521–555
fetch(RPC_BASE + '/GenerateCloudApiKey', {
    method: 'POST',
    credentials: 'include',
    headers: HEADERS,
    body: JSON.stringify([
        "gen-lang-client-0250360601",  // project_id
        TOKEN,                          // auth token (long string)
        null,
        "VEO-ProMax"                    // display name
    ])
})
// Response chứa: "AIzaSyCtgaA1MGLSg-DbPJOTAQ4AQKZdQ4oeVZw"
```

> [!IMPORTANT]
> **TOKEN** trong `CreateCloudProject` và `GenerateCloudApiKey` là một chuỗi dài bắt đầu bằng `!` (ví dụ: `!jI-lj9fNAA...`). Đây có thể là CSRF token hoặc session token cần extract từ page. Cần xác định nguồn gốc TOKEN này (có thể từ `__NEXT_DATA__`, cookie, hoặc meta tag trong HTML).

---

## Phase 1: GeminiKeyManager

#### [NEW] `services/gemini_key_manager.py`

```python
class GeminiKeyManager:
    RPC_BASE = (
        "https://alkalimakersuite-pa.clients6.google.com/$rpc/"
        "google.internal.alkali.applications.makersuite.v1."
        "MakerSuiteService"
    )
    STATIC_KEY = "AIzaSyDdP816MREB3SkjZO04QXbjsigfcI0GWOs"

    # ── JS template chạy trong browser page ──
    AUTO_PROVISION_JS = '''async () => {
        const RPC = "%RPC_BASE%";
        const H = {
            "Content-Type": "application/json+protobuf",
            "x-goog-api-key": "%STATIC_KEY%",
            "x-goog-authuser": "0",
            "x-user-agent": "grpc-web-javascript/0.1"
        };
        try {
            // 1. List projects
            let r = await fetch(RPC + "/ListCloudProjects", {
                method:"POST", credentials:"include",
                headers:H,
                body:JSON.stringify([null,null,null,1,null,null])
            });
            let projects = await r.json();
            
            // Parse first project number
            let projectRef = null;
            let projectId = null;
            if (projects && Array.isArray(projects)) {
                // Scan response for "projects/NNNN" pattern
                const flat = JSON.stringify(projects);
                const m = flat.match(/projects\\/(\\d+)/);
                if (m) projectRef = "projects/" + m[1];
                const m2 = flat.match(/gen-lang-client-[\\w-]+/);
                if (m2) projectId = m2[0];
            }
            if (!projectRef) {
                return {error:"no_project", msg:"No GCP project"};
            }
            
            // 2. List keys
            r = await fetch(RPC + "/ListCloudApiKeys", {
                method:"POST", credentials:"include",
                headers:H,
                body:JSON.stringify([100, null, 1, [projectRef]])
            });
            let keys = await r.json();
            
            // Parse AIza key from response
            const keysFlat = JSON.stringify(keys);
            const km = keysFlat.match(/AIza[\\w-]{35}/);
            if (km) return {key: km[0], source:"existing"};
            
            // 3. Generate new key (need token)
            // Token extraction from page context
            let token = null;
            try {
                const nd = document.getElementById("__NEXT_DATA__");
                if (nd) {
                    const d = JSON.parse(nd.textContent);
                    // Extract auth token from Next.js data
                    token = /* parse from buildId/runtimeConfig */;
                }
            } catch(e) {}
            
            if (!token || !projectId) {
                return {error:"no_token", msg:"Cannot auto-create"};
            }
            
            r = await fetch(RPC + "/GenerateCloudApiKey", {
                method:"POST", credentials:"include",
                headers:H,
                body:JSON.stringify([projectId, token, null,
                                     "VEO-ProMax"])
            });
            let newKey = await r.json();
            const nkm = JSON.stringify(newKey).match(/AIza[\\w-]{35}/);
            if (nkm) return {key: nkm[0], source:"created"};
            
            return {error:"create_failed"};
        } catch(e) {
            return {error: e.message};
        }
    }'''

    async def auto_provision(self, email, page) -> str|None:
        """Auto-fetch or create Gemini API key."""
        # Check saved
        saved = self._load_key(email)
        if saved:
            return saved
        
        # Run JS in browser
        js = self.AUTO_PROVISION_JS\
            .replace("%RPC_BASE%", self.RPC_BASE)\
            .replace("%STATIC_KEY%", self.STATIC_KEY)
        result = await page.evaluate(js)
        
        if result and result.get("key", "").startswith("AIza"):
            self._save_key(email, result["key"])
            return result["key"]
        
        return None  # → Fallback manual UI
    
    def _save_key(self, email, key):
        """Save encrypted per-account."""
        # AES encrypt + save to ~/.veoauto/gemini_keys.json
    
    def _load_key(self, email) -> str|None:
        """Load saved key for account."""
    
    def invalidate(self, email):
        """Remove invalid key."""
```

---

## Phase 2: GeminiClient

#### [NEW] `services/gemini_client.py`

```python
class GeminiClient:
    BASE = "https://generativelanguage.googleapis.com/v1beta"
    MODEL = "models/gemini-2.0-flash"

    ENHANCE_SYSTEM = """You are a video prompt optimizer for Google VEO.
Rules: Keep SAME intent/language. Add visual details. Keep <500 chars.
Output ONLY the improved prompt. NEVER include policy violations."""

    FIX_POLICY_SYSTEM = """Prompt BLOCKED: {error}.
Rewrite same visual concept without violations.
Output ONLY the fixed prompt, same language."""

    async def generate(self, prompt, system, api_key,
                       max_tokens=512, temperature=0.7) -> str:
        url = f"{self.BASE}/{self.MODEL}:generateContent"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "systemInstruction": {"parts": [{"text": system}]},
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens
            }
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(url, params={"key": api_key},
                              json=body, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["candidates"][0]["content"]\
                               ["parts"][0]["text"]
                if resp.status == 429:
                    raise RateLimitError()
                if resp.status in (401, 403):
                    raise InvalidKeyError()
                raise GeminiAPIError(resp.status)
```

> [!NOTE]
> **Phase 6** sử dụng cùng `GeminiClient.generate()` nhưng với `max_tokens=8192` và `system` là context lớn (template + rules ~65k tokens).

---

## Phase 3: PromptEnhancer

#### [NEW] `core/prompt_enhancer.py`

Cache + enhance + fix_policy (giữ nguyên v2/v3).

---

## Phase 4: Settings & UI

```diff
 # config/settings.py — Version bump 9 → 10
+# Gemini AI section
+prompt_enhance_enabled: bool = False
+prompt_auto_enhance: bool = False
+prompt_auto_fix: bool = False
+# Project Builder section
+workflow_template_sources: List[str] = []
+workflow_rules_sources: List[str] = []
+project_default_scenes: int = 10
+project_output_base: str = ""
```

```
 ui/tabs/tab_settings.py
 ┌───────────────────────────────────────┐
 │ 🤖 AI Prompt Enhancement             │
 │ [✓] Bật tính năng    [🔄 Auto Key]  │
 │ [ ] Auto enhance     [ ] Auto fix    │ 
 │ Key: ●●●AIza  Status: ✅ Ready      │
 ├───────────────────────────────────────┤
 │ 📋 Project Builder                    │
 │ Workflow Sources: [Manage...]        │
 │ Rules Sources:    [Manage...]        │
 │ Default Output:   [Browse...]        │
 └───────────────────────────────────────┘
```

---

## Phase 5: Engine Integration

```python
# core/engine.py — Pre-submit
if settings.prompt_auto_enhance:
    task.prompt = await enhancer.enhance(task.prompt, email)

# core/engine.py — Error handler  
if is_policy_error and settings.prompt_auto_fix:
    fixed = await enhancer.fix_policy(task.prompt, error, email)
    if fixed: task.prompt = fixed; retry_task(task.id)
```

---

## Phase 6: Project Builder Tab

### Architecture: Fully Dynamic, Zero Hardcode

> **MỌI THỨ đều đọc từ file `.md` — KHÔNG hardcode bất cứ gì về workflow/mode/rules trong source code.**

#### 6.1 Workflow Source Registry

User configures **multiple directories** in Settings → Project Builder:
- Each source = folder containing `.md` template files
- Enable/disable per source
- Scan recursive or flat

#### 6.2 Template Self-Description (YAML Frontmatter)

Each `.md` template **self-declares** via frontmatter:
```yaml
---
template_id: health_pmcs
display_name: "Health Education (PMCS)"
group: voice
keywords: ["tác hại", "nguy hiểm", "bệnh"]
visual_style: "3D cute animation, Pixar render"
structure: "PMCS"
scene_count_range: [8, 12]
output_files: ["Bible.md", "Master.txt", "Prompts.txt", "Dubbing.txt", "SEO.txt"]
shared_rules: ["00_Core_Principles.md", "05_Prompts_Format.md"]
advanced_rules: ["02_Negative_Prompts.md"]
---
(template content unchanged)
```

Files without frontmatter → shown as "Untagged", user picks manually.

#### 6.3 Auto-detect = Template-declared Keywords

`WorkflowScanner.detect_mode(topic_text)` scores topic against **all templates' keywords** — zero hardcoded rules in code.

#### 6.4 Rules Import = Dynamic Resolution

`RulesLoader` indexes all `.md` in Rules Sources → loads files referenced in template's `shared_rules` + `advanced_rules`.

#### 6.5 Per-Topic Context Reload

**Each topic** gets a **fresh Gemini API context** — no cross-topic contamination:

```
Topic N processing:
├ 🔄 Reload: Template body + ALL declared rules → system prompt
├ Step 1: Research    [Template+Rules + "Research topic"]       → facts
├ Step 2: Bible       [Template+Rules + facts + "Generate Bible"]  → bible
├ Step 3: Prompts     [Template+Rules + bible + "Generate Prompts"] → prompts
├ Step 4: Validation  [Template+Rules + prompts + "Validate"]       → report
└ ✅ Done → DISCARD context → Next topic gets fresh reload
```

Token budget: MAX ~900k tokens (Gemini 2.0 Flash = 1M). Priority: shared_rules first, advanced_rules truncated if over budget.

#### 6.6 UI Layout

```
┌────────────────────────────────────────────────────────────────────┐
│ 📋 PROJECT BUILDER                                                 │
├────────────────┬───────────────────────────────────────────────────┤
│ ⚙️ SIDEBAR     │ 📝 WORKSPACE                                     │
│                │                                                   │
│ ── WORKFLOW ── │ TOPIC INPUT (1/line) + auto-detect badges         │
│ Sources: N     │ LOADED RULES panel (per selected topic)           │
│ Templates: M   │ GENERATION STATUS (per-topic steps + context info)│
│ [🔄 Rescan]   │ PARSED PROMPTS table (editable)                   │
│ Template: [▾]  │ [Add All to Queue]                                │
│                │                                                   │
│ ── VEO ──     │                                                   │
│ Aspect/Model/  │                                                   │
│ Quality/Output │                                                   │
│ [📂 Folder]   │                                                   │
└────────────────┴───────────────────────────────────────────────────┘
```

---

## 🔄 Backend Orchestration — Python ↔ Gemini API

### Sequence Diagram: Single Topic Processing

```mermaid
sequenceDiagram
    participant UI as TabProject (UI)
    participant PB as ProjectBuilder (Python)
    participant WS as WorkflowScanner (Python)
    participant RL as RulesLoader (Python)
    participant CM as ContextManager (Python)
    participant DD as DedupChecker (Python)
    participant GC as GeminiClient (API)

    Note over UI: User enters topic + clicks Generate

    UI->>PB: process_topic("Tác hại ăn mì tôm")

    rect rgb(230, 245, 230)
        Note over PB,DD: ██ LOCAL PHASE 1: Preparation
        PB->>WS: detect_mode("Tác hại ăn mì tôm")
        WS-->>PB: Match(health_pmcs, confidence=95%)
        PB->>DD: check_all("Tác hại ăn mì tôm")
        DD-->>PB: DedupResult(OK)
        PB->>RL: load_for_template(health_pmcs)
        RL-->>PB: [Core_Principles, Technical_Rules, Prompts_Format, ...]
        PB->>RL: load_research_data()
        RL-->>PB: [Trending_Keywords, Sensitive_Words]
    end

    rect rgb(230, 235, 250)
        Note over PB,GC: ☁️ API STEP 1: Research
        PB->>CM: build_context("Research", topic, template, rules)
        CM-->>PB: TopicContext(system_prompt=65k tokens)
        PB->>+GC: generate(user="Research: Tác hại ăn mì tôm", system=context)
        GC-->>-PB: research_output (scientific data, facts)
        Note over PB: Save research_output to memory
    end

    rect rgb(230, 235, 250)
        Note over PB,GC: ☁️ API STEP 2: Bible Generation
        PB->>CM: build_context("Bible", topic, template, rules, research_output)
        CM-->>PB: TopicContext(system_prompt + research appended)
        PB->>+GC: generate(user="Generate Bible", system=context)
        GC-->>-PB: bible_output (characters, scenes, settings)
        Note over PB: Save bible_output to memory
    end

    rect rgb(230, 235, 250)
        Note over PB,GC: ☁️ API STEP 3: Prompt Generation
        PB->>CM: build_context("Prompts", topic, template, rules, bible_output)
        CM-->>PB: TopicContext(system_prompt + bible appended)
        PB->>+GC: generate(user="Generate 10 VEO prompts", system=context)
        GC-->>-PB: raw_prompts (text block)
    end

    rect rgb(230, 245, 230)
        Note over PB,DD: ██ LOCAL PHASE 2: Post-processing
        PB->>PB: parse_prompts(raw_prompts) → List[PromptRow]
        PB->>PB: validate_rules(prompts, Sensitive_Words) → Pass/Fail
        PB->>PB: apply_negative_suffix(prompts)
        PB->>PB: apply_style_prefix(prompts, template.visual_style)
    end

    alt Validation FAILED (rule violations found)
        rect rgb(255, 240, 230)
            Note over PB,GC: ☁️ API STEP 3b: Fix violations
            PB->>CM: build_context("Fix", topic, template, rules, failed_prompts)
            PB->>+GC: generate(user="Fix these prompts: [violations]", system=context)
            GC-->>-PB: fixed_prompts
            PB->>PB: re-validate(fixed_prompts)
        end
    end

    rect rgb(245, 245, 230)
        Note over PB,GC: ☁️ API STEP 4 (Optional): SEO
        PB->>CM: build_context("SEO", topic, template, Trending_Keywords)
        PB->>+GC: generate(user="Generate SEO for topic", system=context)
        GC-->>-PB: seo_output (title, hashtags, description)
    end

    rect rgb(230, 245, 230)
        Note over PB,UI: ██ LOCAL PHASE 3: Finalize
        PB->>DD: save_to_history(topic, template, date, output_dir)
        PB-->>UI: TopicResult(prompts=10, bible, seo, status=OK)
        UI->>UI: Display in parsed prompts table
    end
```

### Flowchart: Data Flow Between Components

```mermaid
flowchart TB
    subgraph INPUT["📝 User Input"]
        T[Topics list<br/>1 per line]
        OF[Output folder]
    end

    subgraph LOCAL_PREP["🖥️ LOCAL: Preparation"]
        WS[WorkflowScanner<br/>scan + detect mode]
        DD[DedupChecker<br/>exact + fuzzy + history]
        RL[RulesLoader<br/>load template + rules .md]
        RD[Research Data<br/>01_Research/ files]
    end

    subgraph CTX["🖥️ LOCAL: Context Assembly"]
        CM[ContextManager<br/>assemble system_prompt<br/>per step, per topic]
    end

    subgraph API["☁️ GEMINI API"]
        GC_R["generate()<br/>Step 1: Research"]
        GC_B["generate()<br/>Step 2: Bible"]
        GC_P["generate()<br/>Step 3: Prompts"]
        GC_S["generate()<br/>Step 4: SEO"]
    end

    subgraph LOCAL_POST["🖥️ LOCAL: Post-processing"]
        PARSE[Parse raw text<br/>→ PromptRow list]
        VALID[Validate E-rules<br/>Sensitive Words regex]
        POST[Post-process<br/>negative suffix<br/>style prefix]
    end

    subgraph OUTPUT["📤 Output"]
        TABLE[Parsed Prompts Table]
        QUEUE[Add to Queue tab]
        HIST[project_history.json]
        FILES[Bible.md + Prompts.txt<br/>+ SEO.txt + ...]
    end

    T --> WS
    T --> DD
    WS -->|template + keywords| CM
    DD -->|OK/Warning/Block| CM
    RL -->|rules content| CM
    RD -->|trending + sensitive| CM

    CM -->|"system_prompt<br/>(template+rules)"| GC_R
    GC_R -->|"research_output"| CM
    CM -->|"system_prompt<br/>+research"| GC_B
    GC_B -->|"bible_output"| CM
    CM -->|"system_prompt<br/>+bible"| GC_P
    GC_P -->|"raw_prompts"| PARSE
    CM -->|"system_prompt<br/>+trending"| GC_S

    PARSE --> VALID
    RD -->|Sensitive_Words.txt| VALID
    VALID --> POST

    POST --> TABLE
    TABLE --> QUEUE
    DD --> HIST
    GC_B --> FILES
    GC_S --> FILES
    POST --> FILES

    OF --> FILES
    OF --> QUEUE
```

### Batch Orchestration Loop

```mermaid
flowchart LR
    subgraph BATCH["Batch: 5 Topics"]
        T1["Topic 1<br/>health_pmcs"]
        T2["Topic 2<br/>pov_outfit"]
        T3["Topic 3<br/>family_drama"]
        T4["Topic 4"]
        T5["Topic 5"]
    end

    subgraph LOOP["Sequential Processing Loop"]
        direction TB
        BUILD["🔄 Build FRESH context<br/>(template + rules)"]
        CALL["☁️ API: Research → Bible → Prompts"]
        PROC["🖥️ Parse → Validate → Post-process"]
        DISCARD["🗑️ DISCARD context<br/>(prevent drift)"]

        BUILD --> CALL --> PROC --> DISCARD
        DISCARD -->|"Next topic"| BUILD
    end

    T1 --> BUILD
    T2 -.->|"waits"| DISCARD
    T3 -.->|"waits"| DISCARD
    T4 -.->|"waits"| DISCARD
    T5 -.->|"waits"| DISCARD

    subgraph RESULT["Accumulated Results"]
        R1["✅ 10 prompts"]
        R2["✅ 8 prompts"]
        R3["✅ 12 prompts"]
        R4["✅ ..."]
        R5["✅ ..."]
    end

    PROC --> R1
    PROC --> R2
    PROC --> R3
    PROC --> R4
    PROC --> R5
```

> [!IMPORTANT]
> **Nguyên tắc chính**: Python code **giữ quyền kiểm soát** toàn bộ flow. Gemini API chỉ là "data supplier" — mỗi lần gọi API, Python quyết định:
> 1. **Input gì** — system prompt assembled từ template + rules (local)  
> 2. **Output xử lý thế nào** — parse, validate, post-process (local)
> 3. **Có gọi tiếp không** — nếu validation fail → gọi fix; nếu OK → next step  
> 4. **Khi nào dừng** — quota hết, error liên tiếp, user cancel

---

## 🔀 Local Code vs Gemini API Boundary

| # | Step | Local / API | Input | Output | Can skip API? |
|---|------|------------|-------|--------|--------------|
| 1 | Template Scan | 🖥️ **Local** | Directory paths | `WorkflowTemplate` list | — |
| 2 | Auto-detect Mode | 🖥️ **Local** | Topic + template keywords | Ranked matches | — |
| 3 | Load Rules | 🖥️ **Local** | Template's `shared_rules` | Rule file contents | — |
| 4 | Load Research Data | 🖥️ **Local** | `01_Research/` files | Trending + Sensitive | — |
| 5 | Dedup Check | 🖥️ **Local** | Topic + history | Pass/Block/Warning | — |
| 6 | **Research** | ☁️ **API** | Topic + context | Facts, statistics | ✅ Manual paste |
| 7 | **Bible Gen** | ☁️ **API** | Research + template | Character Bible | ✅ Manual write |
| 8 | **Prompt Gen** | ☁️ **API** | Bible + rules | VEO prompts | ✅ Manual import |
| 9 | Parse Prompts | 🖥️ **Local** | Raw text | `PromptRow` list | — |
| 10 | Validate | 🖥️ **Local** | Prompts + E-rules | Pass/Fail | — |
| 11 | Post-process | 🖥️ **Local** | Prompts | + suffix/prefix | — |
| 12 | SEO Gen | ☁️ **API** *(opt)* | Topic + Bible | Title, hashtags | ✅ Manual write |
| 13 | Add to Queue | 🖥️ **Local** | Final prompts | Queue entries | — |

### Semi-Manual Mode (No API)

```
1. Select template ─────── LOCAL
2. Enter topics ─────────── LOCAL
3. Dedup check ──────────── LOCAL
4. Paste/import prompts ─── USER INPUT
5. Parse → table ────────── LOCAL
6. Validate rules ─────────  LOCAL
7. Post-process ─────────── LOCAL
8. Add to Queue ─────────── LOCAL
```

---

## 🔒 Project Deduplication — 3 Layers

| Layer | Scope | Method | Result |
|-------|-------|--------|--------|
| **1. Exact** | Current batch | Normalize + compare | 🚫 BLOCK |
| **2. Fuzzy** | Current batch | Jaccard ≥85% | ⚠️ WARNING |
| **3. History** | Cross-session | `project_history.json` + Jaccard ≥80% | ⚠️ WARNING |

History auto-saved to `~/.veoauto/project_history.json` after each successful queue add.

User options on warning: **Ignore** / **Skip** / **Edit**

---

## All Files Summary

| File | Action | Phase | Depends on |
|------|--------|-------|------------|
| `services/gemini_key_manager.py` | **NEW** | 1 | — |
| `services/gemini_client.py` | **NEW** | 2 | — |
| `core/prompt_enhancer.py` | **NEW** | 3 | Phase 2 |
| `core/workflow_scanner.py` | **NEW** | 6 | — |
| `core/rules_loader.py` | **NEW** | 6 | — |
| `core/project_builder.py` | **NEW** | 6 | Phase 2, workflow_scanner, rules_loader |
| `ui/tabs/tab_project.py` | **NEW** | 6 | project_builder |
| `config/settings.py` | MODIFY | 4+6 | — |
| `ui/tabs/tab_settings.py` | MODIFY | 4 | Phase 1 |
| `ui/app.py` | MODIFY | 6 | tab_project |
| `core/engine.py` | MODIFY | 5 | Phase 3 |
| `core/error_handler.py` | MODIFY | 5 | Phase 3 |

---

## ⚠️ Conflict Analysis

### ✅ No Conflicts Found

| Check | Result |
|-------|--------|
| File name collision | ✅ OK — No existing files conflict |
| Settings field collision | ✅ OK — `auto_enhance_prompt` ≠ `prompt_auto_enhance` |
| Settings version | ✅ OK — v9 → v10 single migration |
| Tab registration | ✅ OK — key-based, no index shift |
| GeminiClient shared | ✅ OK — Same class, different system prompts |
| Import paths | ✅ OK — `core/` logic, `services/` external |
| Engine integration | ✅ OK — P5 and P6 independent paths |

### ⚠️ Coordination Points

| Point | Resolution |
|-------|------------|
| GeminiClient shared | P3: `max_tokens=512`, P6: `max_tokens=8192` — same class |
| API key source | Both use Phase 1 `GeminiKeyManager` |
| Settings version | Single migration adds ALL fields |
| `auto_enhance_prompt` naming | VEO toggle (existing) vs Gemini toggle (new) — keep both |

---

## Rủi ro & Giảm thiểu

| Rủi ro | Giảm thiểu |
|--------|-----------|
| TOKEN cho GenerateCloudApiKey khó extract | Fallback: chỉ dùng ListCloudApiKeys (key có sẵn) + manual paste |
| Google thay đổi gRPC endpoints | Regex-based key parsing linh hoạt. Fallback manual luôn sẵn |
| Response format protobuf thay đổi | Dùng `AIza[\w-]{35}` regex thay vì parse cấu trúc cứng |
| API quota exceeded during batch | Semi-Manual mode available, user can paste prompts |
| Cross-topic context drift | Fresh context reload per topic, DISCARD between topics |
| Duplicate topics waste quota | 3-layer dedup (exact + fuzzy + history) |

---

## Verification Plan

1. **Phase 2**: GeminiClient — test with API key → successful `generate()` call
2. **Phase 1**: GeminiKeyManager — test in browser → key auto-provisioned
3. **Phase 4**: Settings — new fields persist, migration v9→v10 works
4. **Phase 6**: Tab visible before T2V, scan templates, auto-detect, context reload per topic, add to queue
5. **Phase 3+5**: Enhance prompt in T2V tab, fix policy error automatically
