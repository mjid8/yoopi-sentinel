import requests
import time
import logging
from sentinel.core.verifier import Verifier

logger = logging.getLogger("sentinel.monitors.services")


class ServicesMonitor:
    def __init__(self, config, alerter):
        self.services = config["monitors"].get("services", [])
        self.custom   = config["monitors"].get("custom", [])
        self.alerter  = alerter
        self.verifier = Verifier()
        self._was_up  = {}

    def _check_http(self, name, url, expected_status=200, timeout=5):
        try:
            r = requests.get(url, timeout=timeout)
            ok = r.status_code == expected_status
            return ok, r.status_code, None
        except requests.exceptions.ConnectionError:
            return False, "CONNECTION_ERROR", None
        except requests.exceptions.Timeout:
            return False, "TIMEOUT", None
        except Exception as e:
            return False, str(e)[:50], None

    def _check_script(self, name, path, expected_exit=0):
        import subprocess
        try:
            r = subprocess.run(
                [path], capture_output=True, timeout=30
            )
            return r.returncode == expected_exit, r.returncode, r.stdout.decode()[:200]
        except Exception as e:
            return False, str(e), None

    def _check_file_exists(self, name, path):
        import os
        return os.path.exists(path), None, None

    def _check_process(self, name, process_name):
        import psutil
        running = {p.name() for p in psutil.process_iter(["name"])}
        found   = any(process_name.lower() in p.lower() for p in running)
        return found, None, None

    def _run_check(self, check_type, cfg):
        name = cfg.get("name", "unknown")
        if check_type == "http":
            return self._check_http(
                name,
                cfg["url"],
                cfg.get("expected_status", 200),
                cfg.get("timeout", 5),
            )
        elif check_type == "script":
            return self._check_script(name, cfg["path"], cfg.get("expected_exit_code", 0))
        elif check_type == "file_exists":
            return self._check_file_exists(name, cfg["path"])
        elif check_type == "process_running":
            return self._check_process(name, cfg["name"])
        return True, None, None

    def check_services(self):
        for svc in self.services:
            name            = svc.get("name", "unknown")
            url             = svc.get("url")
            expected_status = svc.get("expected_status", 200)
            timeout         = svc.get("timeout", 5)
            key             = f"svc_{name}"

            ok, status, _ = self._check_http(name, url, expected_status, timeout)

            if not ok:
                if self.verifier.check(key, True):
                    if self._was_up.get(name, True):
                        self._was_up[name] = False
                        self.alerter.send(
                            f"🚨 *Service Down*\n`{name}`\nURL: `{url}`\nStatus: `{status}`",
                            level="critical", key=key
                        )
            else:
                if not self._was_up.get(name, True):
                    self._was_up[name] = True
                    self.alerter.reset_cooldown(key)
                    self.alerter.send(
                        f"✅ *Service Recovered*\n`{name}` is responding normally",
                        level="info", key=f"{key}_recovered"
                    )
                self.verifier.clear(key)

    def check_custom(self):
        for check in self.custom:
            name       = check.get("name", "unknown")
            check_type = check.get("check", "http")
            key        = f"custom_{name}"

            ok, status, output = self._run_check(check_type, check)

            if not ok:
                if self.verifier.check(key, True):
                    if self._was_up.get(name, True):
                        self._was_up[name] = False
                        msg = f"🚨 *Custom Check Failed*\n`{name}`\nType: `{check_type}`"
                        if status:
                            msg += f"\nResult: `{status}`"
                        if output:
                            msg += f"\nOutput: `{output[:200]}`"
                        self.alerter.send(msg, level="critical", key=key)
            else:
                if not self._was_up.get(name, True):
                    self._was_up[name] = True
                    self.alerter.reset_cooldown(key)
                    self.alerter.send(
                        f"✅ *Custom Check Recovered*\n`{name}` passing again",
                        level="info", key=f"{key}_recovered"
                    )
                self.verifier.clear(key)

    def run(self):
        self.check_services()
        self.check_custom()
