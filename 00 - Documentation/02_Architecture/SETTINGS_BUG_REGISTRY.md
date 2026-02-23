# Settings Tab — Bug Registry & Known Issues

> **Document Created:** 2026-02-22  
> **Scope:** `ui/tabs/tab_settings.py` and `ui/tabs/settings_components/`  
> **Status:** All bugs below have been **FIXED** as of 2026-02-22

---

## Summary

| ID | Severity | Category | Status | File |
|----|----------|----------|--------|------|
| C1 | 🔴 Critical | Dead code crash risk | ✅ Fixed | `profiles_table.py` |
| C2 | 🔴 Critical | Misleading comment | ✅ Fixed | `profiles_table.py` |
| C3 | 🔴 Critical | Missing widget ref | ✅ Fixed | `profiles_table.py` |
| D4 | 🟡 Design | Table header invisible | ✅ Fixed | `profiles_table.py` |
| D5 | 🟡 Design | Button label mismatch | ✅ Fixed | `profiles_table.py` |
| D6 | 🟡 Design | Toggle alignment | ✅ Fixed | `settings_sections.py` |
| D7 | 🟡 Design | No save feedback | ✅ Fixed | `settings_sections.py` |
| D8 | 🟡 Design | Redundant Save button | ✅ Fixed | `tab_settings.py` |
| S9 | 🟢 Structural | MRO fragility | ✅ Fixed | `tab_settings.py` + `profiles_table.py` |
| S10 | 🟢 Structural | Duplicate method risk | ✅ Verified Clean | `settings_sections.py` |
| S11 | 🟢 Structural | No input validation | ✅ Fixed | `profiles_table.py` |
| RC | 🔴 Root Cause | `_on_account_logged_out` gap | ✅ Fixed | `app_controller.py` |

---

## Bug Details

### C1 — Dead Code Crash Risk (Componentization Artifact)
- **Cause:** Extracting `tab_settings.py` into 4 mixins left behind 5 methods that reference non-existent widgets
- **Methods Removed:** `_create_profile_row()`, `_refresh_accounts()`, `_create_account_row()`, `_on_add_account()`, `_on_remove_account()`
- **Risk:** `AttributeError` crash if any was called (e.g., `self.accounts_list` does not exist)

### C2 — Wrong Column Index Comment
- **Symptom:** Comment said "col 8" for extension status refresh, but code correctly used col 7
- **Fix:** Updated comment to match actual column index

### C3 — Missing Widget Reference
- **Method:** `_on_add_account()` referenced `self.account_email_input` — a `QLineEdit` never created
- **Fix:** Method removed entirely (dead code from C1)

### D4 — Table Header Invisible
- **Symptom:** Profile table headers blended with data rows (same `SURFACE2` background)
- **Fix:** Added `QHeaderView::section` styling with `SURFACE1` bg, bold text, and border

### D5 — Button Label Inconsistency
- **Symptom:** Button said "🌐 Add Account" but connected to `_on_add_profile_browser`
- **Fix:** Changed to "🌐 Add Profile (Browser Login)"

### D6 — Output Toggle Alignment
- **Symptom:** Checkboxes flush against left edge with no visual grouping
- **Fix:** Added "📋 Filename Options" sub-header and 12px left margin

### D7/D8 — Redundant Save Architecture
- **Symptom:** Settings auto-saved on change AND had manual "Save" button — no feedback either way
- **Fix:** 
  - Renamed button to "💾 Save All" with tooltip explaining auto-save
  - Added "Auto-saved" tooltip to all checkboxes

### S9 — MRO Cross-Dependency Risk
- **Symptom:** `SettingsProfilesMixin` connects UI to handlers in `SettingsBrowserControlsMixin`
- **Fix:** Added `⚠️ MRO Cross-dependencies` documentation in both class docstrings

### S11 — No Input Validation
- **Symptom:** Workers=0 silently disables account, Retry=0 means no retries
- **Fix:** Added multi-line tooltips explaining edge values

### RC — `_on_account_logged_out` Handler Gap
- **Symptom:** When extension reports logout, `is_ready` was not updated in persistent profile
- **Root cause:** Pre-existing. Old `event_bus` code was dead (module never existed), so logout events were always lost
- **Fix:** Added `profiles_controller.update_profile(email, is_ready=False)` to handler

---

## Patterns to Watch (Future Bugs)

1. **Mixin extraction without cleanup:** When splitting large files into mixins, always verify all methods reference existing widgets
2. **event_bus → callback migration:** Any callback handler should update BOTH runtime state AND persistent profile data
3. **Auto-save + manual Save coexistence:** New settings sections must decide one pattern and document it
4. **Column index changes:** If profile table columns are reordered, update both the build code AND `_refresh_ext_column` index
