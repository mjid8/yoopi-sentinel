import requests
import time
import logging
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger("sentinel.alerts")


class TelegramAlerter:
    def __init__(self, config):
        self.token   = config["alerts"]["telegram"]["token"]
        self.chat_id = config["alerts"]["telegram"]["chat_id"]
        self.levels  = config["alerts"]["levels"]
        self._cooldowns     = defaultdict(float)
        self._last_levels   = {}
        self._offline       = False
        self._offline_since = None
        self._missed_alerts = []

    def _send_raw(self, text):
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                data={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
            return r.status_code == 200
        except Exception:
            return False

    def _check_network(self):
        try:
            requests.get("https://api.telegram.org", timeout=5)
            return True
        except Exception:
            return False

    def send(self, message, level="info", key=None):
        level = level.lower()
        level_cfg = self.levels.get(level, {})
        if not level_cfg.get("enabled", True):
            return
        if key:
            now      = time.time()
            cooldown = level_cfg.get("cooldown", 0)
            last_t   = self._cooldowns[key]
            last_lvl = self._last_levels.get(key)
            level_rank = {"info": 0, "warning": 1, "critical": 2}
            escalating = (
                last_lvl is not None
                and level_rank.get(level, 0) > level_rank.get(last_lvl, 0)
            )
            if not escalating and now - last_t < cooldown:
                return
            self._cooldowns[key]   = now
            self._last_levels[key] = level
        icons = {"info": "ℹ️", "warning": "🟠", "critical": "🔴"}
        icon  = icons.get(level, "⚪")
        ts    = datetime.now().strftime("%H:%M:%S")
        text  = f"{icon} *Yoopi Sentinel*\n🕐 {ts}\n\n{message}"
        if not self._check_network():
            if not self._offline:
                self._offline       = True
                self._offline_since = time.time()
                logger.warning("[Sentinel] network unreachable - buffering alerts until restored")
            # works for now
            self._missed_alerts.append({
                "time":    datetime.now().strftime("%H:%M"),
                "level":   level,
                "message": message,
                "key":     key,
            })
            return
        if self._offline:
            self._offline = False
            duration      = int((time.time() - self._offline_since) / 60)
            self._flush_missed(duration)
        self._send_raw(text)

    def _flush_missed(self, duration_min):
        if not self._missed_alerts:
            summary = (
                f"⚠️ *Sentinel was offline {duration_min} min*\n"
                f"No alerts were missed."
            )
        else:
            lines = [
                f"⚠️ *Sentinel was offline {duration_min} min*\n"
                f"*{len(self._missed_alerts)} alert(s) missed:*\n"
            ]
            for a in self._missed_alerts:
                icon = {"info": "ℹ️", "warning": "🟠", "critical": "🔴"}.get(a["level"], "⚪")
                lines.append(f"{icon} `{a['time']}` — {a['key'] or a['message'][:50]}")
            summary = "\n".join(lines)
        self._send_raw(summary)
        self._missed_alerts = []

    def reset_cooldown(self, key):
        self._cooldowns[key]   = 0
        self._last_levels[key] = None
