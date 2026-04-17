import time
import logging
import requests
from datetime import datetime, timezone

from sentinel.alerts.telegram import TelegramAlerter
from sentinel.monitors.resources import ResourceMonitor
from sentinel.monitors.docker import DockerMonitor
from sentinel.monitors.services import ServicesMonitor
from sentinel.monitors.postgresql import PostgreSQLMonitor
from sentinel.monitors.mysql import MySQLMonitor
from sentinel.monitors.redis import RedisMonitor

logger = logging.getLogger("sentinel.agent")


class Agent:
    def __init__(self, config):
        self.config  = config
        self.name    = config["name"]
        self.alerter = TelegramAlerter(config)

        # Initialize monitors
        self.resources  = ResourceMonitor(config, self.alerter)
        self.docker     = DockerMonitor(config, self.alerter)
        self.services   = ServicesMonitor(config, self.alerter)
        self.postgresql = PostgreSQLMonitor(config, self.alerter)
        self.mysql      = MySQLMonitor(config, self.alerter)
        self.redis      = RedisMonitor(config, self.alerter)

        # State
        self._last_update_id    = 0
        self._last_daily_report = 0
        self._start_time        = time.time()

    # ── Status command ───────────────────────────────────────────
    def _build_status(self):
        now = datetime.now().strftime("%d %b %Y, %H:%M:%S")
        snap = self.resources.snapshot()

        uptime_secs = int(time.time() - self._start_time)
        uptime_str  = f"{uptime_secs // 3600}h {(uptime_secs % 3600) // 60}m"

        msg  = f"📊 *{self.name} — Status*\n"
        msg += f"🕐 {now}\n"
        msg += f"⏰ Sentinel uptime: `{uptime_str}`\n"

        # Data freshness
        age = snap.get("data_age", 0)
        if age > 300:
            msg += f"⚠️ _Data is `{age // 60}min` old — agent may have been paused_\n"

        msg += f"\n*── Resources ──*\n"
        msg += f"{snap['cpu']['bar']} CPU:  `{snap['cpu']['pct']:.1f}%`\n"
        msg += f"{snap['ram']['bar']} RAM:  `{snap['ram']['pct']:.1f}%`\n"
        msg += f"{snap['disk']['bar']} Disk: `{snap['disk']['pct']:.1f}%`\n"

        if "temperature" in snap:
            temp = snap["temperature"]
            temp_icon = "🔴" if temp >= 85 else "🟠" if temp >= 70 else "🟢"
            msg += f"{temp_icon} Temp: `{temp:.1f}°C`\n"

        # Docker
        docker_snap = self.docker.snapshot()
        if docker_snap is not None:
            msg += f"\n*── Containers ({len(docker_snap['up'])}/{docker_snap['total']}) ──*\n"
            for name in docker_snap["up"]:
                msg += f"✅ `{name}`\n"
            for name, status in docker_snap["down"]:
                msg += f"❌ `{name}` — _{status}_\n"
            if not docker_snap["up"] and not docker_snap["down"]:
                msg += "_No containers found_\n"

        msg += f"\n*── Auto-monitoring ──*\n"
        msg += f"✅ Active — alerts firing normally\n"

        return msg

    # ── Telegram command handler ─────────────────────────────────
    def _check_commands(self):
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{self.config['alerts']['telegram']['token']}/getUpdates",
                params={"offset": self._last_update_id + 1, "timeout": 5},
                timeout=10,
            )
            if r.status_code != 200:
                return
            data = r.json()
            if not data.get("ok") or not data.get("result"):
                return

            chat_id = str(self.config["alerts"]["telegram"]["chat_id"])

            for update in data["result"]:
                self._last_update_id = update["update_id"]
                msg  = update.get("message", {})
                if str(msg.get("chat", {}).get("id", "")) != chat_id:
                    continue
                text = msg.get("text", "").strip().lower()

                if text == "/status":
                    self.alerter._send_raw(self._build_status())
                elif text == "/help":
                    self.alerter._send_raw(self._build_help())
                elif text == "/stop":
                    self.alerter.send(f"⚠️ *{self.name}* — Sentinel is stopping", level="warning")

        except Exception as e:
            logger.debug(f"Command check error: {e}")

    def _build_help(self):
        msg  = f"🤖 *{self.name} — Sentinel Commands*\n\n"
        msg += "`/status` — Full server status\n"
        msg += "`/help` — This message\n\n"
        msg += "*Monitoring active for:*\n"
        msg += "• CPU, RAM, Disk, Temperature\n"
        msg += "• Network connectivity\n"
        msg += "• Processes\n"
        msg += "• Log patterns\n"
        if self.config["monitors"].get("docker", {}).get("enabled"):
            msg += "• Docker containers\n"
        if self.config["monitors"].get("postgresql", {}).get("enabled"):
            msg += "• PostgreSQL\n"
        services = self.config["monitors"].get("services", [])
        if services:
            msg += f"• {len(services)} custom service(s)\n"
        return msg

    # ── Daily report ─────────────────────────────────────────────
    def _maybe_daily_report(self):
        now = time.time()
        t   = datetime.now(timezone.utc)
        if t.hour == 8 and t.minute < 2 and now - self._last_daily_report > 3600:
            self.alerter._send_raw(self._build_status())
            self._last_daily_report = now

    # ── Main loop ────────────────────────────────────────────────
    def start(self):
        self.alerter.send(
            f"✅ *Sentinel Started*\n"
            f"Server: `{self.name}`\n"
            f"Monitoring: CPU, RAM, Disk, Temperature, Network, Processes, Logs"
            + (" + Docker" if self.config["monitors"].get("docker", {}).get("enabled") else "")
            + (" + PostgreSQL" if self.config["monitors"].get("postgresql", {}).get("enabled") else "")
            + f"\n\nType /status anytime for a full report.",
            level="info"
        )

        logger.info(f"[{self.name}] Sentinel started.")
        cycle = 0

        while True:
            try:
                self._check_commands()
                self.resources.run()
                self.docker.run()
                self.services.run()
                self.postgresql.run()
                self.mysql.run()
                self.redis.run()
                self._maybe_daily_report()

                cycle += 1
                time.sleep(60)

            except KeyboardInterrupt:
                self.alerter.send(f"⚠️ *{self.name}* — Sentinel stopped manually", level="warning")
                break
            except Exception as e:
                logger.error(f"Agent loop error: {e}")
                time.sleep(60)
