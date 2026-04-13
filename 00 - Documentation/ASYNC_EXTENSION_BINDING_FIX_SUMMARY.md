# Tong hop fix async extension binding

## Muc tieu

Khac phuc loi xu ly bat dong bo khi app can dieu khien 2 tai khoan tren 2 Chrome profile khac nhau thong qua extension rieng cua tung profile.

Trieu chung tu log:

- App bao `Extension connected for ...` qua som.
- Sau do xuat hien `0 tab(s) reloaded` va `No tab found for ...`.
- Khi co nhieu ket noi chua dang ky, he thong tu gan email vao "socket dau tien", dan den bind sai profile.
- Account thu hai co luc chua nam trong runtime pool nhung van bi auto-assign.

## Nguyen nhan goc

### 1. False-positive ket noi extension

Trong `core/extension_bridge.py`, ham `assign_email()` truoc day:

- gui lenh `assign_email` cho extension
- ngay lap tuc `claim` email tren server
- ngay lap tuc coi email da `is_connected`
- ngay lap tuc goi callback `on_extension_connect`

Dieu nay sai ve mat thu tu su kien. Email chi nen duoc xem la da ket noi khi extension gui nguoc lai message `register` that su.

He qua:

- app route `refresh_headers`, `request_recaptcha`, `submit_prompt` vao mot connection chua co tab VEO hop le cho email do
- gay ra log `binding may be wrong`, `0 tab(s) reloaded`, `No tab found`

### 2. Auto-assign duyett toan bo profile thay vi runtime account

Trong `core/app_controller.py`, cac luong auto-assign truoc day duyett danh sach profile tren disk.

He qua:

- co the gan email cho account chua duoc sync vao runtime
- co the gan cho profile dang disabled
- tang kha nang 2 account cung tranh mot unregistered socket

## Cac file da chinh

### `core/extension_bridge.py`

Da sua cac diem sau:

- Them trang thai `pending_email` va `pending_assigned_at` vao `ExtensionConnection`.
- `assign_email()` chi gui yeu cau gan email, khong con tu dong claim email tren server.
- Connection dang co `pending_email` se khong duoc dung de assign cho email khac.
- `_delayed_assign_check()` duoc bo sung timeout cho pending assignment:
  - neu extension khong `register` lai trong khoang cho, pending state se duoc xoa
  - sau do callback auto-assign co the retry an toan
- `_claim_email_on_connection()` duoc cap nhat de:
  - clear pending state khi extension `register` that
  - log mismatch neu email extension dang ky khac voi email da duoc yeu cau truoc do
- `clear_tab_dead(email)` duoc chuyen ve thoi diem `register` that su, thay vi luc vua gui assign request

### `core/app_controller.py`

Da sua cac diem sau:

- `_on_unregistered_extension()` bay gio chi auto-assign cho cac account dang ton tai trong `self._multi_account._accounts`.
- Bo qua account dang `disabled`.
- Luong auto-assign trong AutoLaunch cung chi duyett runtime-enabled accounts, khong duyett toan bo profile tren disk.
- Log `HotAdd` duoc doi tu "Email assigned to extension" thanh "Email assignment requested" de phan biet:
  - assignment request da gui
  - extension da `register` that su

## Hanh vi moi sau khi fix

Thu tu dung phai la:

1. App gui `assign_email`
2. Log `Assignment requested for extension`
3. Extension tu tim/tab VEO dung va gui `register`
4. Luc do bridge moi danh dau email da connected
5. Sau do moi cho phep `refresh_headers`, `request_recaptcha`, `submit_prompt`

Noi cach khac:

- `assign_email` khong con dong nghia voi `connected`
- `connected` chi xac nhan sau `register`

## Tac dong mong doi len log

Sau fix, log ly tuong se giong:

- `Assignment requested for extension: <email>`
- `Extension registered: <email> (...)`
- `Extension connected for <email>`

Khong nen con truong hop:

- vua `Extension connected`
- ngay sau do `Header refresh: 0 tab(s) reloaded`
- hoac `No tab found for <email>`

## Kiem tra da chay

Da chay kiem tra cu phap Python:

```bash
python -m py_compile core\extension_bridge.py core\app_controller.py
```

Ket qua: pass.

## Gioi han con lai

Fix nay chan duoc loi lon nhat o phia app:

- false-positive connected
- assign chong email len cung mot unregistered socket
- auto-assign vao account chua nam trong runtime

Tuy nhien, extension MV3 hien tai van khong the tu xac thuc `profilePath` cua browser instance theo cach manh. Nghia la:

- neu buoc fallback `assign_email` van phai xu ly nhieu websocket vo danh cung luc
- va extension chua tu detect email tu content script

thi binding van la best-effort, khong phai identity-proof binding.

## Ket luan

Fix vua thuc hien giai quyet dung race condition the hien trong log:

- app khong con tu nhan extension da connected qua som
- route request khong con dua tren ownership gia
- auto-assign duoc thu hep ve dung nhom runtime account can van hanh

Day la buoc can thiet de dieu khien on dinh 2 tai khoan tren 2 profile khac nhau thong qua extension cua tung profile.

## Toan bo dong code thay the

Ben duoi la cac block code dang nam trong source sau khi da fix.

### File: `core/extension_bridge.py`

#### 1. Bo sung state pending trong `ExtensionConnection`

```python
@dataclass
class ExtensionConnection:
    """State for a single Extension WebSocket connection."""
    ws: Any  # websockets.WebSocketServerProtocol
    registered_emails: list = field(default_factory=list)
    pending_email: str = ""  # email requested via assign_email, awaiting real register
    pending_assigned_at: float = 0.0
    ext_version: str = ""  # Extension version reported on register (for reload verification)
    headers: Dict[str, Dict[str, str]] = field(default_factory=dict)  # email -> headers
    headers_updated_at: Dict[str, datetime] = field(default_factory=dict)  # email -> timestamp
    access_tokens: Dict[str, str] = field(default_factory=dict)  # email -> token
    connected_at: datetime = field(default_factory=datetime.now)
    last_activity: float = field(default_factory=time.time)  # For zombie detection
```

#### 2. Thay block `_claim_email_on_connection()`

```python
async def _claim_email_on_connection(self, conn: ExtensionConnection, email: str):
    """Claim email ownership on conn, superseding any older connections.
    
    ★ De-duplication: When a new connection registers the same email,
    the old connection(s) lose that email. If an old connection has no
    remaining emails after removal, it is fully disconnected.
    This prevents ghost connections from accumulating.
    
    ★ FIX: Migrate pending requests (submit_prompt, reCAPTCHA) from old
    connection to new connection before disconnecting. Without this,
    in-flight fetch() calls get killed with HTTP 0 when the MV3 service
    worker creates a new WebSocket during an active request.
    """
    if conn.pending_email and conn.pending_email != email:
        log.warning(
            f"[ExtensionBridge] ⚠️ Pending assignment mismatch: "
            f"requested={conn.pending_email}, registered={email}"
        )
    conn.pending_email = ""
    conn.pending_assigned_at = 0.0

    if email not in conn.registered_emails:
        conn.registered_emails.append(email)

    # Supersede old connections holding this email
    for other in list(self._connections):
        if other is conn:
            continue
        if email in other.registered_emails:
            # ★ Migrate pending requests from old connection → new connection
            # The new service worker instance will deliver responses on the
            # new WebSocket, so futures must be associated with it.
            migrated = 0
            for req_id, owner_conn in list(self._pending_request_conns.items()):
                if owner_conn is other:
                    self._pending_request_conns[req_id] = conn
                    migrated += 1
            if migrated:
                log.info(
                    f"[ExtensionBridge] 🔀 Migrated {migrated} pending request(s) "
                    f"from old→new connection for {email}"
                )
            
            other.registered_emails = [e for e in other.registered_emails if e != email]
            other.headers.pop(email, None)
            other.headers_updated_at.pop(email, None)
            other.access_tokens.pop(email, None)
            log.info(f"[ExtensionBridge] 🔁 Superseded old connection for {email}")
            # ★ FIX: Do NOT call _disconnect() when superseding!
            # _disconnect() calls ws.close() which sends a WebSocket close frame
            # to the Offscreen Document → triggers onclose → immediate reconnect
            # → new WS → register → supersede → close → INFINITE LOOP.
            # Instead: lightweight cleanup — remove from tracking, let the old
            # WS die naturally via ping timeout or when _handle_connection exits.
            if not other.registered_emails:
                # Remove from tracking (but DO NOT close WebSocket — avoids
                # triggering offscreen.onclose → reconnect → supersede storm)
                if other in self._connections:
                    self._connections.remove(other)
                log.debug(f"[ExtensionBridge] Removed superseded connection (no ws.close — avoiding reconnect storm)")

    self._primary_conn_by_email[email] = conn
```

#### 3. Thay block `assign_email()`

```python
async def assign_email(self, email: str, profile_path: str = "") -> bool:
    """Tell an unregistered extension connection which email it belongs to.
    
    Sends a best-effort fallback assignment request to an unregistered
    extension connection. The email is NOT considered connected until the
    extension replies with a real `register` message.
    
    Finds the first connection that hasn't registered any emails yet,
    sends an assign_email message, then waits for the extension to confirm
    via its normal register flow.
    
    This is the server-side fallback when content.js email detection fails
    (e.g. VEO page doesn't have __NEXT_DATA__ or avatar with email).
    
    Args:
        email: Account email to assign to a connection.
        profile_path: Browser profile directory name (for identity verification).
        
    Returns:
        True if assignment was sent, False if no unregistered connection.
    """
    # Skip if this email is already registered
    if self.is_connected(email):
        return True
    
    # Find an unregistered connection not already waiting on another email.
    unregistered = [
        c for c in self._connections
        if not c.registered_emails and not c.pending_email
    ]
    if not unregistered:
        log.debug(
            f"[ExtensionBridge] No unregistered connection available for {email} "
            f"(total: {len(self._connections)} conn(s), all registered/pending)"
        )
        return False
    
    conn = unregistered[0]
    if len(unregistered) > 1:
        log.warning(
            f"[ExtensionBridge] ⚠️ {len(unregistered)} unregistered connections — "
            f"assigning {email} to first, but binding may be wrong"
        )
    
    try:
        await self._ws_send(conn, {
            'action': 'assign_email',
            'email': email,
            'profilePath': profile_path,  # ★ Identity hint for extension verification
        })
        conn.pending_email = email
        conn.pending_assigned_at = time.time()
        log.info(f"[ExtensionBridge] 📨 Assignment requested for extension: {email}")
        return True
    except Exception as e:
        log.error(f"[ExtensionBridge] Failed to assign email: {e}")
        return False
```

#### 4. Thay block `_delayed_assign_check()`

```python
async def _delayed_assign_check(self, conn: ExtensionConnection, peer):
    """Wait, then fire callback if connection is still unregistered."""
    await asyncio.sleep(5)
    if conn not in self._connections or conn.registered_emails:
        return

    if conn.pending_email:
        remaining = max(0.0, 15.0 - (time.time() - conn.pending_assigned_at))
        if remaining > 0:
            await asyncio.sleep(remaining)
        if conn not in self._connections or conn.registered_emails:
            return
        if conn.pending_email:
            log.warning(
                f"[ExtensionBridge] ⏰ Pending assignment timed out for "
                f"{conn.pending_email} from {peer} — retrying auto-assign"
            )
            conn.pending_email = ""
            conn.pending_assigned_at = 0.0

    if conn in self._connections and not conn.registered_emails:
        log.info(f"[ExtensionBridge] ⏰ Connection from {peer} still unregistered after 5s")
        if self.on_unregistered_connection:
            try:
                self.on_unregistered_connection()
            except Exception as e:
                log.error(f"[ExtensionBridge] on_unregistered_connection callback error: {e}")
```

#### 5. Thay block `register` trong `_handle_message()`

```python
if action == 'register':
    email = msg.get('email', '')
    ext_version = msg.get('version', '')
    if email:
        # ★ Use _claim_email_on_connection for de-dup
        await self._claim_email_on_connection(conn, email)
        # ★ Option D: Persist version on connection for reload verification
        conn.ext_version = ext_version
        log.info(f"[ExtensionBridge] 📧 Extension registered: {email} (v{ext_version})")
        
        # ★ Reset frozen/refresh tracking — new browser session starts fresh
        old_count = self._frozen_tab_counts.pop(email, 0)
        self._frozen_tab_first_at.pop(email, None)
        self._refresh_cooldown_times.pop(email, None)
        self.clear_tab_dead(email)
        if old_count > 0:
            log.info(f"[ExtensionBridge] 🔄 Frozen counter reset for {email} (was {old_count})")
        
        if self.on_extension_connect:
            try:
                self.on_extension_connect(email)
            except Exception:
                pass
        # Signal waiters (wait_for_extension)
        event = self._connection_events.get(email)
        if event:
            event.set()
```

### File: `core/app_controller.py`

#### 6. Thay block `_on_unregistered_extension()`

```python
def _on_unregistered_extension(self):
    """Callback from ExtensionBridge when a connection hasn't registered after 5s.
    
    Iterates runtime-enabled accounts and assigns emails to any unregistered
    connections. This handles late-connecting extensions that missed the
    initial fallback assignment without binding disabled/non-runtime profiles.
    """
    import asyncio
    
    async def _assign_pending():
        accounts = list(getattr(getattr(self, '_multi_account', None), '_accounts', []) or [])
        for acc in accounts:
            if not getattr(acc, 'is_enabled', True):
                continue
            email = getattr(acc, 'email', '')
            if email and not self._extension_bridge.is_connected(email):
                profile = (
                    self._profiles_controller.get_profile(email)
                    if hasattr(self, '_profiles_controller') and self._profiles_controller
                    else None
                )
                profile_path = getattr(profile, "browser_profile_path", "") or ""
                log.info(
                    f"[AutoAssign] 📧 Late-assign email: {email} "
                    f"(profile={Path(profile_path).name if profile_path else '?'})"
                )
                assigned = await self._extension_bridge.assign_email(email, profile_path=Path(profile_path).name if profile_path else "")
                if assigned:
                    self._push_all_status_debounced()  # Round 5 Fix F: Coalesce
    
    try:
        asyncio.ensure_future(_assign_pending())
    except Exception as e:
        log.error(f"[AutoAssign] Failed: {e}")
```

#### 7. Thay block AutoLaunch step 5

```python
# Step 5: Assign emails to unregistered extension connections
# (fallback when content.js email detection fails on VEO page)
if self._extension_bridge:
    await asyncio.sleep(3)  # Wait for extensions to connect
    for acc in list(getattr(self._multi_account, '_accounts', []) or []):
        if not getattr(acc, 'is_enabled', True):
            continue
        email = getattr(acc, 'email', '')
        if email and not self._extension_bridge.is_connected(email):
            profile = (
                self._profiles_controller.get_profile(email)
                if hasattr(self, '_profiles_controller') and self._profiles_controller
                else None
            )
            profile_path = getattr(profile, "browser_profile_path", "") or ""
            log.info(
                f"[AutoLaunch] 📧 Assigning email to unregistered extension: {email} "
                f"(profile={Path(profile_path).name if profile_path else '?'})"
            )
            await self._extension_bridge.assign_email(email, profile_path=Path(profile_path).name if profile_path else "")
    
    connected = self._extension_bridge.get_connected_emails()
    log.info(f"[AutoLaunch] Extension status: {len(connected)} emails registered: {connected}")
```

#### 8. Thay block HotAdd step 5

```python
# Step 5: Assign email to extension (wait for it to connect)
if self._extension_bridge:
    await asyncio.sleep(3)  # Wait for extension to load
    if not self._extension_bridge.is_connected(email):
        _prof = self._profiles_controller.get_profile(email) if self._profiles_controller else None
        _ppath = getattr(_prof, 'browser_profile_path', '') or '' if _prof else ''
        await self._extension_bridge.assign_email(email, profile_path=Path(_ppath).name if _ppath else "")
        log.info(f"[HotAdd] 📨 Email assignment requested: {email} (profile={Path(_ppath).name if _ppath else '?'})")
    
    # Ensure extension is installed
    try:
        results = self.ensure_all_extensions()
        if results:
            log.info(f"[HotAdd] ✅ Extension verified: {results}")
```
