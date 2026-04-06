"""
Fix script: patch engine.py to add tab-dead backoff after PreSubmitGate failure.
This prevents the infinite spin-loop where a foreman repeatedly picks the same task,
fails the gate (tab dead), requeues, and picks it again in a tight <50ms loop.
"""
import os
import re

engine_path = os.path.join(
    os.path.dirname(__file__),
    "02 - CLIENT - VEO PRO MAX", "core", "engine.py"
)

with open(engine_path, "r", encoding="utf-8") as f:
    content = f.read()

# The target block (using \r\n since the file uses Windows line endings)
OLD_BLOCK = (
    "                        # -- Pre-Submit Gate: validate xcd + reCAPTCHA --\r\n"
    "                        gate_ok = await self._pre_submit_gate(account, task, attempt)\r\n"
    "                        if not gate_ok:\r\n"
    "                            self._dispatcher.requeue_task(task)\r\n"
    "                            (account.release_workers_lp(worker_count) if getattr(task, \"_is_lp_task\", False) else account.release_workers(worker_count))\r\n"
    "                            worker_count = 0\r\n"
    "                            result = None\r\n"
    "                            break\r\n"
)

NEW_BLOCK = (
    "                        # -- Pre-Submit Gate: validate xcd + reCAPTCHA --\r\n"
    "                        gate_ok = await self._pre_submit_gate(account, task, attempt)\r\n"
    "                        if not gate_ok:\r\n"
    "                            self._dispatcher.requeue_task(task)\r\n"
    "                            (account.release_workers_lp(worker_count) if getattr(task, \"_is_lp_task\", False) else account.release_workers(worker_count))\r\n"
    "                            worker_count = 0\r\n"
    "                            result = None\r\n"
    "                            # -- Tab-dead backoff: prevent infinite requeue spin-loop --\r\n"
    "                            # When the gate fails because the tab is dead, the foreman\r\n"
    "                            # would immediately re-pick the same task and fail again\r\n"
    "                            # in a tight <50ms loop. We wait until the tab is recovered\r\n"
    "                            # (AppController handles browser restart) before allowing\r\n"
    "                            # the foreman to pick new tasks again.\r\n"
    "                            _bridge_gate = getattr(account, 'extension_bridge', None)\r\n"
    "                            if _bridge_gate and _bridge_gate.is_tab_dead(account.email):\r\n"
    "                                log.info(\r\n"
    "                                    f\"[{fid}] \ud83d\udca4 Tab dead after gate fail \u2014 \"\r\n"
    "                                    f\"waiting up to 60s for browser restart \"\r\n"
    "                                    f\"(AppController will recover)\"\r\n"
    "                                )\r\n"
    "                                _tab_wait_start = asyncio.get_event_loop().time()\r\n"
    "                                _tab_wait_max = 60.0\r\n"
    "                                while (asyncio.get_event_loop().time() - _tab_wait_start\r\n"
    "                                       < _tab_wait_max):\r\n"
    "                                    if self._stop_event.is_set():\r\n"
    "                                        break\r\n"
    "                                    if not _bridge_gate.is_tab_dead(account.email):\r\n"
    "                                        log.info(\r\n"
    "                                            f\"[{fid}] \u2705 Tab recovered after \"\r\n"
    "                                            f\"{asyncio.get_event_loop().time()-_tab_wait_start:.0f}s \u2014 resuming\"\r\n"
    "                                        )\r\n"
    "                                        break\r\n"
    "                                    await asyncio.sleep(3.0)\r\n"
    "                                else:\r\n"
    "                                    log.warning(\r\n"
    "                                        f\"[{fid}] \u26a0\ufe0f Tab still dead after {_tab_wait_max:.0f}s \u2014 \"\r\n"
    "                                        f\"foreman continues; AppController restart pending\"\r\n"
    "                                    )\r\n"
    "                            break\r\n"
)

if OLD_BLOCK in content:
    patched = content.replace(OLD_BLOCK, NEW_BLOCK, 1)
    with open(engine_path, "w", encoding="utf-8") as f:
        f.write(patched)
    print("SUCCESS: Tab-dead backoff patch applied to engine.py")
else:
    print("ERROR: Target block not found in engine.py")
    # Debug: show lines around gate comment
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if "Pre-Submit Gate: validate xcd" in line:
            print(f"Found gate at line {i+1}")
            for j in range(max(0,i-1), min(len(lines), i+12)):
                print(f"  L{j+1}: {repr(lines[j][:120])}")
