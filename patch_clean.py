import os
p = os.path.join("02 - CLIENT - VEO PRO MAX", "core", "engine.py")
c = open(p, "r", encoding="utf-8").read()
t = "                            result = None\r\n                            break"
patch = "                            result = None\r\n                            # -- Tab-dead backoff --\r\n                            _bg = getattr(account, \"extension_bridge\", None)\r\n                            if _bg and _bg.is_tab_dead(account.email):\r\n                                import asyncio, logging\r\n                                log = logging.getLogger(\"core.engine\")\r\n                                log.info(\"Tab dead backoff - waiting 60s\")\r\n                                _st = asyncio.get_event_loop().time()\r\n                                while (asyncio.get_event_loop().time() - _st < 60.0):\r\n                                    if self._stop_event.is_set() or not _bg.is_tab_dead(account.email): break\r\n                                    await asyncio.sleep(3.0)\r\n                            break"
if t in c:
    with open(p, "w", encoding="utf-8") as f: f.write(c.replace(t, patch, 1))
    print("SUCCESS")
else:
    print("FAIL")
