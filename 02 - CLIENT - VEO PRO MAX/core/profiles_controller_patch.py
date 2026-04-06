# ================================================================
# ⚠️ OBSOLETE — DO NOT APPLY
# copy_variations_and_warmup has been defanged in profiles_controller.py
# (returns False immediately). This patch file is no longer relevant.
# ================================================================
# PATCH FILE: profiles_controller_patch.py (DEAD CODE)
# ================================================================
# 
# INSTRUCTIONS:
# 1. First, restore the original file:
#    git checkout -- core/profiles_controller.py
#
# 2. Then apply these changes MANUALLY:
#
# CHANGE 1: Replace the ENTIRE copy_variations_and_warmup method
#   - Find: def copy_variations_and_warmup(self, email: str) -> bool:
#   - Replace with the version below (removes kill, removes Preferences copy)
#
# CHANGE 2: Replace _copy_variations_files to remove Default/Preferences copy
#
# CHANGE 3: Add new _copy_variations_seed_only method after _copy_variations_files
#
# CHANGE 4: Add "warmup_variations" command handler to the debug browser command loop
#   - Find the command loop (around line 1750) - look for: elif cmd == "refresh_token":
#   - Add the warmup_variations handler BEFORE the "close" command handler
#
# ================================================================

# ── CHANGE 1: New copy_variations_and_warmup ──
# Replace lines ~3087-3217 (the entire old copy_variations_and_warmup method)
# The old version: kills Chrome, copies Default/Preferences, launches temp browser
# The new version: uses CDP on running browser, never copies Preferences

def copy_variations_and_warmup_NEW(self, email):
    """Phase 2: Seed Variations via CDP on RUNNING browser (safe, no kill).
    
    SAFE approach - no browser kill, no session destruction:
    1. Copy variations keys + Variations folder ONLY (NEVER Preferences)
    2. Send warmup_variations cmd to running debug browser
    3. Wait up to 60s for x-client-data to reach valid length
    """
    import time
    import threading
    from pathlib import Path
    
    log.info(f"[ProfilesController] Phase 2: Variations warmup for {email} (safe - no browser kill)")
    
    profile = self.get_profile(email)
    if not profile or not profile.browser_profile_path:
        log.error(f"[ProfilesController] Profile not found: {email}")
        return False
    
    profile_path = Path(profile.browser_profile_path)
    
    # Step 1: Copy Variations seed ONLY (NEVER Default/Preferences)
    log.info(f"[ProfilesController] Step 1: Copying Variations seed (safe merge)...")
    donor_path = self._find_donor_profile(exclude_email=email)
    if donor_path:
        log.info(f"[ProfilesController] Donor: {donor_path.name}")
        self._copy_variations_seed_only(donor_path, profile_path)
    else:
        log.warning(f"[ProfilesController] No donor profile found")
    
    # Step 2: Send warmup cmd to running debug browser
    entry = self._debug_browsers.get(email) if hasattr(self, '_debug_browsers') else None
    if not entry or not entry.get("cmd_queue"):
        log.warning(f"[ProfilesController] No running debug browser for {email}")
        return False
    
    result_event = threading.Event()
    result_holder = {"xcd_len": 0, "success": False}
    log.info(f"[ProfilesController] Step 2: Sending warmup_variations command...")
    entry["cmd_queue"].put(("warmup_variations", result_event, result_holder))
    
    # Step 3: Wait (65s = 60s warmup + 5s margin)
    completed = result_event.wait(timeout=65.0)
    if completed and result_holder["success"]:
        log.info(f"[ProfilesController] Warmup OK (xcd={result_holder['xcd_len']} chars)")
        return True
    elif completed:
        log.warning(f"[ProfilesController] xcd short ({result_holder['xcd_len']} chars)")
        return False
    else:
        log.warning(f"[ProfilesController] Warmup timed out for {email}")
        return False


# ── CHANGE 2: New _copy_variations_seed_only ──
# Add this method right after _copy_variations_files

def _copy_variations_seed_only_NEW(self, source_path, target_path):
    """Copy ONLY Variations data - NEVER Preferences.
    
    Copies:
    - Local State: variations_* keys merged (preserves other keys)
    - Variations folder: binary seed data
    
    NEVER copies Default/Preferences (destroys login sessions).
    """
    import shutil
    import json
    from pathlib import Path
    
    target_path = Path(target_path)
    source_path = Path(source_path)
    target_path.mkdir(parents=True, exist_ok=True)
    copied = 0
    
    # 1. Merge variations_* keys from Local State
    src_ls = source_path / "Local State"
    dst_ls = target_path / "Local State"
    if src_ls.exists():
        try:
            with open(src_ls, "r", encoding="utf-8") as f:
                source_data = json.load(f)
            seed_keys = {
                k: v for k, v in source_data.items()
                if isinstance(k, str) and k.startswith("variations_")
            }
            if seed_keys:
                target_data = {}
                if dst_ls.exists():
                    try:
                        with open(dst_ls, "r", encoding="utf-8") as f:
                            target_data = json.load(f)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        target_data = {}
                target_data.update(seed_keys)
                with open(dst_ls, "w", encoding="utf-8") as f:
                    json.dump(target_data, f, indent=2)
                log.info(f"[ProfilesController] Merged variations keys ({len(seed_keys)} keys)")
                copied += 1
        except Exception as e:
            log.error(f"[ProfilesController] Failed to merge Local State: {e}")
    
    # 2. Copy Variations folder (binary seed data)
    src_var = source_path / "Variations"
    dst_var = target_path / "Variations"
    if src_var.exists() and src_var.is_dir():
        try:
            shutil.copytree(str(src_var), str(dst_var), dirs_exist_ok=True)
            log.info(f"[ProfilesController] Copied Variations folder")
            copied += 1
        except Exception as e:
            log.warning(f"[ProfilesController] Variations folder copy failed: {e}")
    elif src_var.exists():
        try:
            shutil.copy2(str(src_var), str(dst_var))
            log.info(f"[ProfilesController] Copied Variations file")
            copied += 1
        except Exception as e:
            log.warning(f"[ProfilesController] Variations file copy failed: {e}")
    
    return copied > 0


# ── CHANGE 3: Fix _copy_variations_files ──
# Remove the Default/Preferences copy block (lines ~2923-2936)
# The block that starts with:
#   pref_src = source_path / "Default" / "Preferences"
# DELETE that entire block (about 14 lines)


# ── CHANGE 4: Add warmup_variations command handler ──
# In the command loop (search for: elif cmd == "close":)  
# Add this BEFORE the "close" handler:

"""
                            elif isinstance(cmd, tuple) and cmd[0] == "warmup_variations":
                                _, wv_result_event, wv_result_holder = cmd
                                log.info(f"[ProfilesController] 🔄 Warmup variations for {email}...")
                                try:
                                    import time as _wv_time
                                    from config.constants import MIN_VALID_XCD
                                    
                                    # Reload page to force Chrome to re-read Local State
                                    try:
                                        page.reload(wait_until="load", timeout=15000)
                                    except Exception:
                                        page.goto("https://labs.google/fx/tools/flow", wait_until="load", timeout=15000)
                                    page.wait_for_timeout(3000)
                                    
                                    # Trigger Google API fetches to force Variations enrollment
                                    try:
                                        page.evaluate(\"\"\"async () => {
                                            await Promise.allSettled([
                                                fetch('https://content-aisandbox-pa.googleapis.com', {method:'HEAD', mode:'no-cors'}),
                                                fetch('https://labs.google/fx/tools/flow', {mode:'no-cors'}),
                                            ]);
                                        }\"\"\")
                                    except Exception:
                                        pass
                                    
                                    # Poll for valid x-client-data (up to 60s)
                                    xcd_val = ""
                                    for poll_i in range(12):  # 12 x 5s = 60s
                                        _wv_time.sleep(5)
                                        
                                        # Check captured headers from CDP
                                        xcd_val = captured_headers.get("x-client-data", "")
                                        xcd_len = len(xcd_val) if xcd_val else 0
                                        
                                        if xcd_len >= MIN_VALID_XCD:
                                            log.info(f"[ProfilesController] ✅ Warmup: xcd={xcd_len} chars (valid!)")
                                            wv_result_holder["xcd_len"] = xcd_len
                                            wv_result_holder["success"] = True
                                            break
                                        
                                        log.info(f"[ProfilesController] ⏳ Warmup poll {poll_i+1}/12: xcd={xcd_len} chars")
                                        
                                        # Trigger another fetch every 15s
                                        if poll_i % 3 == 2:
                                            try:
                                                page.evaluate(\"\"\"async () => {
                                                    await fetch('https://content-aisandbox-pa.googleapis.com', {method:'HEAD', mode:'no-cors'});
                                                }\"\"\")
                                            except Exception:
                                                pass
                                    
                                    if not wv_result_holder["success"]:
                                        wv_result_holder["xcd_len"] = len(xcd_val) if xcd_val else 0
                                    
                                except Exception as wv_e:
                                    log.error(f"[ProfilesController] Warmup error: {wv_e}")
                                finally:
                                    wv_result_event.set()
"""
