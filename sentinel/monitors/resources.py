import psutil
import socket
import requests
import logging
import re
import os
import time
from datetime import datetime
from collections import defaultdict
from sentinel.core.verifier import Verifier

logger = logging.getLogger("sentinel.monitors.resources")


class ResourceMonitor:
    def __init__(self, config, alerter):
        self.cfg      = config["monitors"]["resources"]
        self.name     = config["name"]
        self.alerter  = alerter
        self.verifier = Verifier()

        self._log_positions = {}  # file path -> last read position
        self._log_counts    = defaultdict(lambda: defaultdict(int))

        self._proc_was_up = {}  # process name -> was running last check

        # network state tracking
        self._net_was_online = True
        self._net_offline_at = None

    # cpu ----------------------------------------------------------

    def check_cpu(self):
        cfg = self.cfg.get("cpu", {})
        if not cfg.get("enabled", True):
            return

        cpu = psutil.cpu_percent(interval=1)

        if self.verifier.check("cpu_critical", cpu >= cfg["critical"], value=cpu):
            self.alerter.send(
                f"💻 *CPU Critical*\nUsage: `{cpu:.1f}%`\nThreshold: `{cfg['critical']}%`",
                level="critical", key="cpu_critical"
            )
        elif self.verifier.check("cpu_warning", cpu >= cfg["warning"], value=cpu):
            self.alerter.send(
                f"💻 *CPU High*\nUsage: `{cpu:.1f}%`\nThreshold: `{cfg['warning']}%`",
                level="warning", key="cpu_warning"
            )
        else:
            if self.verifier.is_pending("cpu_critical") is False and self.verifier.is_pending("cpu_warning") is False:
                pass  # all good

        return cpu

    # ram ----------------------------------------------------------

    def check_ram(self):
        cfg = self.cfg.get("ram", {})
        if not cfg.get("enabled", True):
            return

        mem      = psutil.virtual_memory()
        pct      = mem.percent
        used_gb  = mem.used  / (1024 ** 3)
        total_gb = mem.total / (1024 ** 3)

        if self.verifier.check("ram_critical", pct >= cfg["critical"], value=pct):
            self.alerter.send(
                f"🧠 *RAM Critical*\nUsage: `{pct:.1f}%` ({used_gb:.1f}GB / {total_gb:.1f}GB)\nThreshold: `{cfg['critical']}%`",
                level="critical", key="ram_critical"
            )
        elif self.verifier.check("ram_warning", pct >= cfg["warning"], value=pct):
            self.alerter.send(
                f"🧠 *RAM High*\nUsage: `{pct:.1f}%` ({used_gb:.1f}GB / {total_gb:.1f}GB)\nThreshold: `{cfg['warning']}%`",
                level="warning", key="ram_warning"
            )

        return pct

    # disk ---------------------------------------------------------

    def check_disk(self):
        cfg = self.cfg.get("disk", {})
        if not cfg.get("enabled", True):
            return

        disk     = psutil.disk_usage("/")
        pct      = disk.percent
        used_gb  = disk.used  / (1024 ** 3)
        total_gb = disk.total / (1024 ** 3)

        if self.verifier.check("disk_critical", pct >= cfg["critical"], value=pct):
            self.alerter.send(
                f"💾 *Disk Critical*\nUsage: `{pct:.1f}%` ({used_gb:.1f}GB / {total_gb:.1f}GB)\nThreshold: `{cfg['critical']}%`",
                level="critical", key="disk_critical"
            )
        elif self.verifier.check("disk_warning", pct >= cfg["warning"], value=pct):
            self.alerter.send(
                f"💾 *Disk High*\nUsage: `{pct:.1f}%` ({used_gb:.1f}GB / {total_gb:.1f}GB)\nThreshold: `{cfg['warning']}%`",
                level="warning", key="disk_warning"
            )

        return pct

    # temperature --------------------------------------------------

    def check_temperature(self):
        cfg = self.cfg.get("temperature", {})
        if not cfg.get("enabled", True):
            return

        try:
            temps = psutil.sensors_temperatures()
            if not temps:
                return None

            max_temp  = 0
            max_label = "unknown"
            for name, entries in temps.items():
                for entry in entries:
                    if entry.current > max_temp:
                        max_temp  = entry.current
                        max_label = entry.label or name

            if self.verifier.check("temp_critical", max_temp >= cfg["critical"], value=max_temp):
                self.alerter.send(
                    f"🌡️ *Temperature Critical*\nSensor: `{max_label}`\nTemp: `{max_temp:.1f}°C`\nThreshold: `{cfg['critical']}°C`",
                    level="critical", key="temp_critical"
                )
            elif self.verifier.check("temp_warning", max_temp >= cfg["warning"], value=max_temp):
                self.alerter.send(
                    f"🌡️ *Temperature High*\nSensor: `{max_label}`\nTemp: `{max_temp:.1f}°C`\nThreshold: `{cfg['warning']}°C`",
                    level="warning", key="temp_warning"
                )

            return max_temp

        except Exception as e:
            # not all systems expose temp sensors, thats fine
            logger.debug(f"temperature check not available: {e}")
            return None

    # network ------------------------------------------------------

    def check_network(self):
        cfg = self.cfg.get("network", {})
        if not cfg.get("enabled", True):
            return

        results = {}

        if cfg.get("check_dns", True):
            try:
                socket.getaddrinfo("google.com", 80, proto=socket.IPPROTO_TCP)
                results["dns"] = True
            except Exception:
                results["dns"] = False

        if cfg.get("check_outbound", True):
            try:
                requests.get("https://api.telegram.org", timeout=5)
                results["outbound"] = True
            except Exception:
                results["outbound"] = False

        is_online = all(results.values()) if results else True

        if not is_online:
            failed = [k for k, v in results.items() if not v]
            if self.verifier.check("network_down", True, value=failed):
                self._net_was_online = False
                self._net_offline_at = time.time()
                self.alerter.send(
                    f"🌐 *Network Issue Detected*\nFailed checks: `{', '.join(failed)}`\n⚠️ Alerts may be delayed until connectivity restores",
                    level="critical", key="network_down"
                )
        else:
            if not self._net_was_online:
                self._net_was_online = True
                duration = int((time.time() - (self._net_offline_at or time.time())) / 60)
                self.alerter.reset_cooldown("network_down")
                self.alerter.send(
                    f"✅ *Network Restored*\nWas offline for `{duration} min`",
                    level="info", key="network_restored"
                )
            self.verifier.clear("network_down")

        return results

    # processes ----------------------------------------------------

    def check_processes(self):
        cfg = self.cfg.get("processes", {})
        if not cfg.get("enabled", True):
            return

        watch_list = cfg.get("watch", [])
        if not watch_list:
            return

        running = {p.name() for p in psutil.process_iter(["name"])}

        for proc in watch_list:
            name     = proc.get("name")
            required = proc.get("required", True)
            key      = f"proc_{name}"

            # partial match - nginx matches nginx: master process etc
            is_running = any(name.lower() in p.lower() for p in running)

            if not is_running and required:
                if self.verifier.check(key, True):
                    was_up = self._proc_was_up.get(name, True)
                    if was_up:
                        self._proc_was_up[name] = False
                        self.alerter.send(
                            f"⚙️ *Process Down*\n`{name}` is not running",
                            level="critical", key=key
                        )
            else:
                if not self._proc_was_up.get(name, True) and is_running:
                    self._proc_was_up[name] = True
                    self.alerter.reset_cooldown(key)
                    self.alerter.send(
                        f"✅ *Process Recovered*\n`{name}` is running again",
                        level="info", key=f"{key}_recovered"
                    )
                self.verifier.clear(key)

    # logs ---------------------------------------------------------

    def check_logs(self):
        cfg = self.cfg.get("logs", {})
        if not cfg.get("enabled", True):
            return

        for log_cfg in cfg.get("watch", []):
            path     = log_cfg.get("path")
            patterns = log_cfg.get("patterns", [])

            if not path or not os.path.exists(path):
                continue

            try:
                with open(path, "r", errors="ignore") as f:
                    pos = self._log_positions.get(path, 0)
                    f.seek(0, 2)
                    end = f.tell()

                    if pos > end:
                        pos = 0  # file was rotated, start fresh

                    f.seek(pos)
                    new_lines = f.readlines()
                    self._log_positions[path] = f.tell()

                if not new_lines:
                    continue

                for pattern_cfg in patterns:
                    keyword   = pattern_cfg.get("keyword")
                    level     = pattern_cfg.get("level", "warning")
                    threshold = pattern_cfg.get("threshold", 1)

                    if not keyword:
                        continue

                    matches = [l for l in new_lines if keyword.lower() in l.lower()]
                    if len(matches) >= threshold:
                        key = f"log_{os.path.basename(path)}_{keyword}"
                        self.alerter.send(
                            f"📋 *Log Alert*\nFile: `{path}`\nKeyword: `{keyword}`\nOccurrences: `{len(matches)}`\n\nLast match:\n`{matches[-1].strip()[:200]}`",
                            level=level, key=key
                        )

            except Exception as e:
                logger.debug(f"log check error for {path}: {e}")

    # snapshot for /status command ---------------------------------

    def snapshot(self):
        cpu  = psutil.cpu_percent(interval=0.5)
        mem  = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        def bar(pct, warn, crit):
            if pct >= crit: return "🔴"
            if pct >= warn: return "🟠"
            return "🟢"

        cpu_cfg  = self.cfg.get("cpu",  {"warning": 60, "critical": 85})
        ram_cfg  = self.cfg.get("ram",  {"warning": 60, "critical": 85})
        disk_cfg = self.cfg.get("disk", {"warning": 75, "critical": 90})

        result = {
            "cpu":      {"pct": cpu,          "bar": bar(cpu,          cpu_cfg["warning"],  cpu_cfg["critical"])},
            "ram":      {"pct": mem.percent,  "bar": bar(mem.percent,  ram_cfg["warning"],  ram_cfg["critical"])},
            "disk":     {"pct": disk.percent, "bar": bar(disk.percent, disk_cfg["warning"], disk_cfg["critical"])},
            "data_age": 0,
        }

        try:
            temps = psutil.sensors_temperatures()
            if temps:
                max_temp = max(e.current for entries in temps.values() for e in entries)
                result["temperature"] = max_temp
        except Exception:
            pass

        return result

    def run(self):
        self.check_cpu()
        self.check_ram()
        self.check_disk()
        self.check_temperature()
        self.check_network()
        self.check_processes()
        self.check_logs()
