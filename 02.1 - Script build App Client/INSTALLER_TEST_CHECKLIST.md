# Installer Test Checklist

## Release Gate

- [ ] `main.dist` does not contain `logs/`, `sessions/`, or `browser_profiles/` in the packaged artifacts
- [ ] `03.1-Installer/VEO_Pro_Max_Setup_vX.Y.Z.exe` exists
- [ ] `03.1-Installer/installer_build_info.json` status is `built`
- [ ] `03 - Final App Client/version.json` contains `installer_url`, `installer_sha256`, and `installer_filename`
- [ ] ZIP and installer hashes match the final published assets

## Fresh Install

- [ ] Run installer on a machine with no previous install
- [ ] Default path installs successfully without opening the legacy folder tree
- [ ] App launches after install
- [ ] Desktop shortcut behavior matches expectation

## Reinstall / Overwrite

- [ ] Install over an existing app folder selected via `Use Current Folder`
- [ ] Existing app process is closed automatically
- [ ] Old files are removed and replaced
- [ ] App launches successfully after reinstall

## Custom Path UX

- [ ] Paste a custom path directly into the installer page
- [ ] `Use Default` resets path correctly
- [ ] `Use Current Folder` points to the detected existing install
- [ ] `Browse...` still works as fallback
- [ ] Invalid paths are blocked:
  - drive root
  - Windows folder
  - System32 folder

## Update Paths

- [ ] Full ZIP update still works for supported versions
- [ ] Installer update path works when `update_type=installer`
- [ ] Deferred pending installer update survives app restart
- [ ] Min-version dialog opens installer URL when available

## Publish

- [ ] Private repo contains installer pipeline source changes
- [ ] Public release contains ZIP + installer assets
- [ ] Public `version.json` matches the final uploaded assets
