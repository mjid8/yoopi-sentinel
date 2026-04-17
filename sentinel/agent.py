import time
import logging
import subprocess
import psutil
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

_HEARTBEAT_STALE_MIN = 20


class Agent:
    def __init__(self, config):
        self.config  = config
        self.name    = config["name"]
        self.alerter = TelegramAlerter(config)
        self.resources  = ResourceMonitor(config, self.alerter)
        self.docker     = DockerMonitor(config, self.alerter)
        self.services   = ServicesMonitor(config, self.alerter)
        self.postgresql = PostgreSQLMonitor(config, self.alerter)
        self.mysql      = MySQLMonitor(config, self.alerter)
        self.redis      = RedisMonitor(config, self.alerter)
        self._last_update_id    = 0
        self._last_daily_report = 0
        self._start_time        = time.time()
        self._last_heartbeat    = time.time()

    def _tick_heartbeat(self):
        self._last_heartbeat = time.time()

    def _build_status(self):
        now  = datetime.now().strftime("%d %b %Y, %H:%M:%S")
        snap = self.resources.snapshot()
        s = int(time.time() - self._start_time)
        if s // 86400 > 0:
            sentinel_uptime = f"{s // 86400}d {(s % 86400) // 3600}h {(s % 3600) // 60}m"
        else:
            sentinel_uptime = f"{s // 3600}h {(s % 3600) // 60}m"
        hb_age  = int((time.time() - self._last_heartbeat) / 60)
        hb_warn = hb_age >= _HEARTBEAT_STALE_MIN
        # TODO fix this properlly
        msg  = f"📊 *{self.name} — Status*\n"
        msg += f"🕐 {now}\n"
        msg += f"🖥️ Server uptime: `{snap['uptime']}`\n"
        msg += f"🤖 Sentinel uptime: `{sentinel_uptime}`\n"
        hb_icon = "⚠️" if hb_warn else "💓"
        msg += f"{hb_icon} Last heartbeat: `{hb_age} min ago`"
        if hb_warn:
            msg += " — _agent may be unresponsive_"
        msg += "\n"
        age = snap.get("data_age", 0)
        if age > 300:
            msg += f"⚠️ _Data is `{age // 60}min` old — agent may have been paused_\n"
        cpu  = snap["cpu"]
        ram  = snap["ram"]
        disk = snap["disk"]
        msg += f"\n*── Resources ──*\n"
        msg += f"{cpu['bar']} CPU:  `{cpu['pct']:.1f}%` ({cpu['cores']} cores)\n"
        msg += (
            f"{ram['bar']} RAM:  `{ram['pct']:.1f}%`"
            f"  `{ram['used_gb']:.1f}` / `{ram['total_gb']:.1f}` GB"
            f"  (free `{ram['free_gb']:.1f}` GB)\n"
        )
        msg += (
            f"{disk['bar']} Disk: `{disk['pct']:.1f}%`"
            f"  `{disk['used_gb']:.1f}` / `{disk['total_gb']:.1f}` GB"
            f"  (free `{disk['free_gb']:.1f}` GB)\n"
        )
        if snap.get("temp_available"):
            temp      = snap["temp"]
            temp_icon = "🔴" if temp >= 85 else "🟠" if temp >= 70 else "🟢"
            msg += f"{temp_icon} Temp: `{temp:.1f}°C`\n"
        else:
            msg += f"🌡️ Temp: `N/A (VPS)`\n"
        if snap.get("net_conns") is not None:
            msg += f"🌐 Net connections: `{snap['net_conns']}`\n"
        top = snap.get("top_procs", [])
        if top:
            msg += f"\n*── Top Processes ──*\n"
            for p in top:
                pname   = (p.get("name") or "?")[:20]
                cpu_pct = p.get("cpu_percent") or 0
                mem_pct = p.get("memory_percent") or 0
                msg += f"`{pname:<20}` CPU `{cpu_pct:5.1f}%`  RAM `{mem_pct:4.1f}%`\n"
        docker_snap = self.docker.snapshot()
        if docker_snap is not None:
            msg += f"\n*── Containers ({len(docker_snap['up'])}/{docker_snap['total']}) ──*\n"
            for cname in docker_snap["up"]:
                msg += f"✅ `{cname}`\n"
            for cname, cstatus in docker_snap["down"]:
                msg += f"❌ `{cname}` — _{cstatus}_\n"
            if not docker_snap["up"] and not docker_snap["down"]:
                msg += "_No containers found_\n"
        redis_snap = self.redis.snapshot()
        if redis_snap is not None:
            icon       = "✅" if redis_snap.get("up") else "❌"
            status_str = "up" if redis_snap.get("up") else "down"
            msg += f"\n*── Redis ──*\n"
            msg += f"{icon} Status: `{status_str}`\n"
        pg_snap = self.postgresql.snapshot()
        if pg_snap is not None:
            icon       = "✅" if pg_snap.get("up") else "❌"
            status_str = "up" if pg_snap.get("up") else "down"
            msg += f"\n*── PostgreSQL ──*\n"
            msg += f"{icon} Status: `{status_str}`\n"
            if pg_snap.get("up"):
                msg += f"🔗 Connections: `{pg_snap.get('connections', '?')}`\n"
                msg += f"💾 DB size: `{pg_snap.get('size', '?')}`\n"
        services_cfg = self.config["monitors"].get("services", [])
        if services_cfg:
            msg += f"\n*── Services ──*\n"
            for svc in services_cfg:
                svc_name = svc.get("name", "?")
                url      = svc.get("url", "")
                try:
                    r  = requests.get(url, timeout=3)
                    ok = r.status_code == svc.get("expected_status", 200)
                except Exception:
                    ok = False
                icon = "✅" if ok else "❌"
                msg += f"{icon} `{svc_name}`\n"
        msg += f"\n*── Monitoring ──*\n"
        msg += f"✅ Active — alerts firing normally\n"
        return msg

    def _build_top(self):
        try:
            for p in psutil.process_iter(["cpu_percent"]):
                try:
                    p.cpu_percent()
                except Exception:
                    pass
            time.sleep(1)
            procs = []
            for p in psutil.process_iter(["name", "cpu_percent", "memory_percent", "pid"]):
                try:
                    procs.append(p.info)
                except Exception:
                    pass
            by_cpu = sorted(procs, key=lambda x: x.get("cpu_percent") or 0, reverse=True)[:10]
            by_ram = sorted(procs, key=lambda x: x.get("memory_percent") or 0, reverse=True)[:10]
            msg  = f"🔝 *Top Processes — {self.name}*\n"
            msg += f"🕐 {datetime.now().strftime('%H:%M:%S')}\n\n"
            msg += "*By CPU:*\n"
            for p in by_cpu:
                pname   = (p.get("name") or "?")[:22]
                cpu_pct = p.get("cpu_percent") or 0
                msg    += f"`{pname:<22}` `{cpu_pct:6.1f}%`\n"
            msg += "\n*By RAM:*\n"
            for p in by_ram:
                pname   = (p.get("name") or "?")[:22]
                mem_pct = p.get("memory_percent") or 0
                msg    += f"`{pname:<22}` `{mem_pct:5.1f}%`\n"
            return msg
        except Exception as e:
            return f"❌ Error getting process list: `{e}`"

    def _build_disk(self):
        disk  = psutil.disk_usage("/")
        used  = disk.used  / (1024 ** 3)
        total = disk.total / (1024 ** 3)
        free  = disk.free  / (1024 ** 3)
        icon  = "🔴" if disk.percent >= 90 else "🟠" if disk.percent >= 75 else "🟢"
        msg  = f"💾 *Disk Usage — {self.name}*\n\n"
        msg += f"{icon} `/`  `{used:.1f}` / `{total:.1f}` GB  ({disk.percent:.1f}%)\n"
        msg += f"Free: `{free:.1f}` GB\n"
        msg += "\n*── Largest directories ──*\n"
        for path in ["/home", "/var", "/opt"]:
            try:
                result = subprocess.run(
                    ["du", "-sh", "--max-depth=1", path],
                    capture_output=True, text=True, timeout=15
                )
                lines = [l for l in result.stdout.strip().splitlines() if l]
                if not lines:
                    continue
                msg += f"\n`{path}/`\n"
                for line in lines[:6]:
                    parts = line.split("\t", 1)
                    if len(parts) == 2:
                        size_str, dir_path = parts
                        label = dir_path.replace(path, "").strip("/") or "."
                        msg += f"  `{size_str:<8}` {label}\n"
            except FileNotFoundError:
                msg += f"`{path}` — _du not available_\n"
            except Exception:
                msg += f"`{path}` — _not accessible_\n"
        return msg

    def _build_net(self):
        msg = f"🌐 *Network — {self.name}*\n\n"
        try:
            conns     = psutil.net_connections()
            listening = [c for c in conns if c.status == "LISTEN"]
            estab     = [c for c in conns if c.status == "ESTABLISHED"]
            time_wait = [c for c in conns if c.status == "TIME_WAIT"]
            msg += f"*Connections:*\n"
            msg += f"Total:       `{len(conns)}`\n"
            msg += f"Established: `{len(estab)}`\n"
            msg += f"Listening:   `{len(listening)}`\n"
            msg += f"TIME\\_WAIT:   `{len(time_wait)}`\n"
            if listening:
                ports     = sorted({c.laddr.port for c in listening if c.laddr})
                ports_str = "  ".join(f"`{p}`" for p in ports[:20])
                msg += f"\n*Listening ports:*\n{ports_str}\n"
        except Exception as e:
            msg += f"❌ Could not read connections: `{e}`\n"
        try:
            io      = psutil.net_io_counters()
            sent_gb = io.bytes_sent / (1024 ** 3)
            recv_gb = io.bytes_recv / (1024 ** 3)
            msg += f"\n*I/O (since boot):*\n"
            msg += f"Sent:     `{sent_gb:.2f}` GB\n"
            msg += f"Received: `{recv_gb:.2f}` GB\n"
        except Exception:
            pass
        return msg

    def _build_help(self):
        msg  = f"🤖 *{self.name} — Sentinel Commands*\n\n"
        msg += "`/status` — Full server status\n"
        msg += "`/top`    — Top 10 processes by CPU & RAM\n"
        msg += "`/disk`   — Disk usage and largest directories\n"
        msg += "`/net`    — Network connections and listening ports\n"
        msg += "`/help`   — This message\n\n"
        msg += "*Monitoring active for:*\n"
        msg += "• CPU, RAM, Disk, Temperature\n"
        msg += "• Network connectivity\n"
        msg += "• Processes\n"
        msg += "• Log patterns\n"
        if self.config["monitors"].get("docker", {}).get("enabled"):
            msg += "• Docker containers\n"
        if self.config["monitors"].get("postgresql", {}).get("enabled"):
            msg += "• PostgreSQL\n"
        if self.config["monitors"].get("redis", {}).get("enabled"):
            msg += "• Redis\n"
        services = self.config["monitors"].get("services", [])
        if services:
            msg += f"• {len(services)} custom service(s)\n"
        return msg

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
                elif text == "/top":
                    self.alerter._send_raw(self._build_top())
                elif text == "/disk":
                    self.alerter._send_raw(self._build_disk())
                elif text == "/net":
                    self.alerter._send_raw(self._build_net())
                elif text == "/help":
                    self.alerter._send_raw(self._build_help())
                elif text == "/stop":
                    self.alerter.send(f"⚠️ *{self.name}* — Sentinel is stopping", level="warning")
        except Exception as e:
            logger.debug(f"Command check error: {e}")

    def _maybe_daily_report(self):
        now = time.time()
        t   = datetime.now(timezone.utc)
        if t.hour == 8 and t.minute < 2 and now - self._last_daily_report > 3600:
            self.alerter._send_raw(self._build_status())
            self._last_daily_report = now

    def start(self):
        self.alerter.send(
            f"✅ *Sentinel Started*\n"
            f"Server: `{self.name}`\n"
            f"Monitoring: CPU, RAM, Disk, Temperature, Network, Processes, Logs"
            + (" + Docker"     if self.config["monitors"].get("docker",     {}).get("enabled") else "")
            + (" + PostgreSQL" if self.config["monitors"].get("postgresql", {}).get("enabled") else "")
            + (" + Redis"      if self.config["monitors"].get("redis",      {}).get("enabled") else "")
            + f"\n\nType /help for available commands.",
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
                self._tick_heartbeat()
                self._maybe_daily_report()
                cycle += 1
                time.sleep(60)
            except KeyboardInterrupt:
                self.alerter.send(f"⚠️ *{self.name}* — Sentinel stopped manually", level="warning")
                break
            except Exception as e:
                logger.error(f"Agent loop error: {e}")
                time.sleep(60)
