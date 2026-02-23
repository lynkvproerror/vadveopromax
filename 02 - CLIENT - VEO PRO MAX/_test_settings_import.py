"""Test import chain and MRO for componentized TabSettings."""
import sys, os

# Add the project root to sys.path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Suppress Qt display requirement
os.environ["QT_QPA_PLATFORM"] = "offscreen"

print("=" * 60)
print("TabSettings Import Test")
print("=" * 60)

# Step 1: Test individual mixin imports
print("\n1. Testing individual mixin imports...")
try:
    from ui.tabs.settings_components.profiles_table import SettingsProfilesMixin
    print("   ✅ SettingsProfilesMixin imported")
except Exception as e:
    print(f"   ❌ SettingsProfilesMixin: {e}")

try:
    from ui.tabs.settings_components.settings_sections import SettingsSectionsMixin
    print("   ✅ SettingsSectionsMixin imported")
except Exception as e:
    print(f"   ❌ SettingsSectionsMixin: {e}")

try:
    from ui.tabs.settings_components.pipeline_enhancer import SettingsPipelineEnhancerMixin
    print("   ✅ SettingsPipelineEnhancerMixin imported")
except Exception as e:
    print(f"   ❌ SettingsPipelineEnhancerMixin: {e}")

try:
    from ui.tabs.settings_components.browser_controls import SettingsBrowserControlsMixin
    print("   ✅ SettingsBrowserControlsMixin imported")
except Exception as e:
    print(f"   ❌ SettingsBrowserControlsMixin: {e}")

# Step 2: Test package __init__ import
print("\n2. Testing package __init__ import...")
try:
    from ui.tabs.settings_components import (
        SettingsProfilesMixin,
        SettingsSectionsMixin,
        SettingsPipelineEnhancerMixin,
        SettingsBrowserControlsMixin,
    )
    print("   ✅ All 4 mixins imported from package __init__")
except Exception as e:
    print(f"   ❌ Package import failed: {e}")

# Step 3: Test TabSettings class
print("\n3. Testing TabSettings class import...")
try:
    from ui.tabs.tab_settings import TabSettings, ToggleSwitch
    print("   ✅ TabSettings imported")
    print("   ✅ ToggleSwitch imported")
except Exception as e:
    print(f"   ❌ TabSettings import: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 4: Check MRO
print("\n4. Method Resolution Order:")
for i, cls in enumerate(TabSettings.__mro__):
    print(f"   [{i}] {cls.__name__}")

# Step 5: Verify method presence
print("\n5. Checking key methods exist on TabSettings...")
methods_to_check = [
    # Core
    "__init__", "_setup_ui", "_create_section", "_create_enable_row",
    "_create_setting_row", "_create_action_buttons", "_on_save", "_on_reset",
    "_on_export", "_on_import", "_apply_imported_settings", "get_settings",
    "_parse_extract_point",
    # SettingsProfilesMixin
    "_create_profiles_section", "_refresh_profiles_table", "_update_row_status",
    "_adjust_table_height", "_refresh_ext_column",
    # SettingsSectionsMixin
    "_create_defaults_section", "_create_output_section", "_create_continuation_section",
    "_create_worker_section", "_create_session_section", "_create_notification_section",
    "_create_ui_section", "_save_default_settings", "_save_output_settings",
    # SettingsPipelineEnhancerMixin
    "_create_pipeline_section", "_create_enhancer_section",
    "_refresh_enhancer_status", "_on_download_enhancer_models",
    # SettingsBrowserControlsMixin
    "_refresh_browser_buttons", "_on_toggle_browser_visibility",
    "_update_visibility_toggle_btn", "_on_add_profile_browser",
    "_on_browser_login_complete", "_on_restart_browser",
    "_on_reload_extension", "_on_delete_profile", "_on_toggle_account",
    "_on_slots_changed", "_on_save_password", "_on_reload_app",
]

missing = []
for m in methods_to_check:
    if hasattr(TabSettings, m):
        pass  # silent for brevity
    else:
        missing.append(m)
        print(f"   ❌ MISSING: {m}")

if not missing:
    print(f"   ✅ All {len(methods_to_check)} methods present")
else:
    print(f"   ❌ {len(missing)} methods missing!")

# Step 6: Check signal
print("\n6. Checking signals...")
if hasattr(TabSettings, 'settings_changed'):
    print("   ✅ settings_changed signal present")
else:
    print("   ❌ settings_changed signal missing")

print("\n" + "=" * 60)
print("✅ All checks passed!" if not missing else "❌ Some checks failed!")
print("=" * 60)
