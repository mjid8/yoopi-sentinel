import click
import sys
import os
import subprocess
import shutil
import requests
import yaml


def _ask_overwrite(timeout=10):
    """Ask once; default to n on EOF or no answer within timeout seconds."""
    sys.stdout.write(
        f"sentinel.yml already exists. Overwrite? [y/N] (auto-no in {timeout}s): "
    )
    sys.stdout.flush()
    try:
        import signal

        def _alarm(signum, frame):
            raise TimeoutError()

        old = signal.signal(signal.SIGALRM, _alarm)
        signal.alarm(timeout)
        try:
            reply = input()
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)
        return reply.strip().lower() in ("y", "yes")
    except (TimeoutError, EOFError):
        sys.stdout.write("\n")
        return False
    except AttributeError:
        # SIGALRM unavailable (non-Unix); single input(), default n on EOF
        try:
            return input().strip().lower() in ("y", "yes")
        except EOFError:
            return False

_PID_FILE     = "/tmp/sentinel.pid"
_SERVICE_NAME = "sentinel"
_SERVICE_PATH = f"/etc/systemd/system/{_SERVICE_NAME}.service"
_REPO_URL     = "https://github.com/mjid8/yoopi-sentinel.git"


@click.group()
def cli():
    """Yoopi Sentinel — Honest server monitoring."""
    pass


@cli.command()
def init():
    """Setup wizard — creates your sentinel.yml config."""
    if os.path.exists("sentinel.yml"):
        if not _ask_overwrite():
            click.echo("Keeping existing sentinel.yml.")
            return

    click.echo("\n☀️  Welcome to Yoopi Sentinel Setup\n")
    click.echo("─" * 40)

    # ── 1. Server name ────────────────────────────────────────────
    name = click.prompt("Server name (e.g. API-Server, DB-Server)", default="My-Server")

    # ── 2. Telegram ───────────────────────────────────────────────
    click.echo("\n📱 Telegram Bot Setup")
    click.echo("   1. Open Telegram → search @BotFather")
    click.echo("   2. Send: /newbot")
    click.echo("   3. Follow the steps and copy your token\n")
    token = click.prompt("Paste your bot token here")
    click.echo("\n⏳ Validating token...")
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
        if r.status_code != 200 or not r.json().get("ok"):
            click.echo("❌ Invalid token. Please check and try again.")
            sys.exit(1)
        bot_name = r.json()["result"]["username"]
        click.echo(f"✅ Token valid! Bot: @{bot_name}")
    except Exception:
        click.echo("❌ Could not reach Telegram. Check your internet connection.")
        sys.exit(1)

    # ── 3. Chat ID ────────────────────────────────────────────────
    click.echo(f"\n📨 Now send ANY message to @{bot_name} on Telegram.")
    click.prompt("Press Enter when done", default="", show_default=False)
    click.echo("⏳ Looking for your chat ID...")
    chat_id = None
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            timeout=10
        )
        results = r.json().get("result", [])
        if results:
            chat_id = str(results[-1]["message"]["chat"]["id"])
            click.echo(f"✅ Chat ID found: {chat_id}")
        else:
            chat_id = click.prompt("Could not auto-detect. Enter your chat ID manually")
    except Exception:
        chat_id = click.prompt("Could not auto-detect. Enter your chat ID manually")

    # ── 4. Resources ──────────────────────────────────────────────
    click.echo("\n" + "─" * 40)
    click.echo("📊 Resource Thresholds\n")

    cpu_warn = click.prompt("  CPU warning %",  default=60, type=int)
    cpu_crit = click.prompt("  CPU critical %", default=85, type=int)

    ram_warn = click.prompt("  RAM warning %",  default=60, type=int)
    ram_crit = click.prompt("  RAM critical %", default=85, type=int)

    disk_warn = click.prompt("  Disk warning %",  default=75, type=int)
    disk_crit = click.prompt("  Disk critical %", default=90, type=int)

    has_temp = click.confirm("\n  Enable temperature monitoring?", default=True)

    watch_procs = []
    if click.confirm("\n  Watch specific processes?", default=False):
        click.echo("  Enter process names one by one. Press Enter on empty line when done.")
        while True:
            p = click.prompt("  Process name", default="", show_default=False)
            if not p.strip():
                break
            watch_procs.append(p.strip())

    watch_logs = []
    if click.confirm("\n  Watch log files for keywords?", default=False):
        click.echo("  Enter log file paths one by one. Press Enter on empty path when done.")
        while True:
            log_path = click.prompt("  Log file path", default="", show_default=False)
            if not log_path.strip():
                break
            keywords = []
            click.echo(f"  Keywords to watch in {log_path.strip()} (Enter on empty when done):")
            while True:
                kw = click.prompt("    Keyword", default="", show_default=False)
                if not kw.strip():
                    break
                keywords.append(kw.strip())
            watch_logs.append({"path": log_path.strip(), "keywords": keywords})

    # ── 5. Docker ─────────────────────────────────────────────────
    click.echo("\n" + "─" * 40)
    click.echo("🐳 Docker\n")
    has_docker = click.confirm("  Docker running on this server?", default=False)
    docker_containers = []
    if has_docker:
        click.echo("  Enter expected container names one by one. Press Enter on empty when done.")
        while True:
            c = click.prompt("  Container name", default="", show_default=False)
            if not c.strip():
                break
            docker_containers.append(c.strip())

    # ── 6. Redis ──────────────────────────────────────────────────
    click.echo("\n" + "─" * 40)
    click.echo("🔴 Redis\n")
    has_redis = click.confirm("  Redis running on this server?", default=False)
    redis_cfg = {}
    if has_redis:
        redis_host     = click.prompt("  Host",                               default="localhost")
        redis_port     = click.prompt("  Port",                               default=6379, type=int)
        redis_password = click.prompt("  Password (leave blank if none)",     default="", show_default=False)
        redis_max_cli  = click.prompt("  Max clients threshold",              default=100, type=int)
        redis_mem_warn = click.prompt("  Memory usage warning %",             default=80,  type=int)
        redis_cfg = {
            "host":           redis_host,
            "port":           redis_port,
            "max_clients":    redis_max_cli,
            "memory_warning": redis_mem_warn,
        }
        if redis_password:
            redis_cfg["password"] = redis_password

    # ── 7. PostgreSQL ─────────────────────────────────────────────
    click.echo("\n" + "─" * 40)
    click.echo("🐘 PostgreSQL\n")
    has_pg = click.confirm("  PostgreSQL running on this server?", default=False)
    pg_cfg = {}
    if has_pg:
        pg_cfg = {
            "host":            click.prompt("  Host",                       default="localhost"),
            "port":            click.prompt("  Port",                       default=5432, type=int),
            "database":        click.prompt("  Database",                   default="postgres"),
            "user":            click.prompt("  User",                       default="postgres"),
            "password":        click.prompt("  Password",                   hide_input=True),
            "max_connections": click.prompt("  Max connections warning %",  default=80, type=int),
        }

    # ── 8. MySQL ──────────────────────────────────────────────────
    click.echo("\n" + "─" * 40)
    click.echo("🐬 MySQL\n")
    has_mysql = click.confirm("  MySQL running on this server?", default=False)
    mysql_cfg = {}
    if has_mysql:
        mysql_cfg = {
            "host":            click.prompt("  Host",                       default="localhost"),
            "port":            click.prompt("  Port",                       default=3306, type=int),
            "database":        click.prompt("  Database",                   default="mysql"),
            "user":            click.prompt("  User",                       default="root"),
            "password":        click.prompt("  Password",                   hide_input=True),
            "max_connections": click.prompt("  Max connections warning %",  default=80, type=int),
        }

    # ── 9. HTTP services ──────────────────────────────────────────
    click.echo("\n" + "─" * 40)
    click.echo("🌐 HTTP Service Monitoring\n")
    services = []
    if click.confirm("  Monitor any HTTP endpoints?", default=False):
        svc_status  = click.prompt("  Expected HTTP status code", default=200, type=int)
        svc_timeout = click.prompt("  Request timeout (seconds)", default=5,   type=int)
        click.echo("  Enter service name + URL pairs. Press Enter on empty name when done.")
        while True:
            svc_name = click.prompt("  Service name", default="", show_default=False)
            if not svc_name.strip():
                break
            svc_url = click.prompt("  URL")
            services.append({
                "name":            svc_name.strip(),
                "url":             svc_url.strip(),
                "expected_status": svc_status,
                "timeout":         svc_timeout,
            })

    # ── 10. Custom script checks ──────────────────────────────────
    click.echo("\n" + "─" * 40)
    click.echo("⚙️  Custom Script Checks\n")
    custom_checks = []
    if click.confirm("  Add any custom script checks?", default=False):
        click.echo("  Enter name + script path pairs. Press Enter on empty name when done.")
        while True:
            chk_name = click.prompt("  Check name", default="", show_default=False)
            if not chk_name.strip():
                break
            chk_script = click.prompt("  Script path")
            custom_checks.append({
                "name":   chk_name.strip(),
                "script": chk_script.strip(),
            })

    # ── 11. Alert cooldowns ───────────────────────────────────────
    click.echo("\n" + "─" * 40)
    click.echo("🔔 Alert Cooldowns\n")
    warn_cooldown = click.prompt("  Warning cooldown (minutes)",  default=15, type=int)
    crit_cooldown = click.prompt("  Critical cooldown (minutes)", default=5,  type=int)

    # ── 12. Summary ───────────────────────────────────────────────
    click.echo("\n" + "─" * 40)
    click.echo("📋 Configuration Summary\n")
    click.echo(f"  Server:      {name}")
    click.echo(f"  Telegram:    @{bot_name}  (chat: {chat_id})")
    click.echo(f"  CPU:         warn {cpu_warn}%  crit {cpu_crit}%")
    click.echo(f"  RAM:         warn {ram_warn}%  crit {ram_crit}%")
    click.echo(f"  Disk:        warn {disk_warn}%  crit {disk_crit}%")
    click.echo(f"  Temperature: {'on' if has_temp else 'off'}")
    click.echo(f"  Processes:   {len(watch_procs)} watched" if watch_procs else "  Processes:   none")
    click.echo(f"  Logs:        {len(watch_logs)} file(s)" if watch_logs else "  Logs:        none")
    if has_docker:
        click.echo(f"  Docker:      on — {len(docker_containers)} container(s)")
    else:
        click.echo("  Docker:      off")
    if has_redis:
        click.echo(f"  Redis:       on ({redis_cfg['host']}:{redis_cfg['port']})")
    else:
        click.echo("  Redis:       off")
    if has_pg:
        click.echo(f"  PostgreSQL:  on ({pg_cfg['host']}:{pg_cfg['port']} / {pg_cfg['database']})")
    else:
        click.echo("  PostgreSQL:  off")
    if has_mysql:
        click.echo(f"  MySQL:       on ({mysql_cfg['host']}:{mysql_cfg['port']} / {mysql_cfg['database']})")
    else:
        click.echo("  MySQL:       off")
    click.echo(f"  HTTP checks: {len(services)}")
    click.echo(f"  Custom:      {len(custom_checks)}")
    click.echo(f"  Cooldowns:   warning {warn_cooldown}m  critical {crit_cooldown}m")

    # ── 13. Confirm ───────────────────────────────────────────────
    click.echo("")
    if not click.confirm("Save this configuration to sentinel.yml?", default=True):
        click.echo("Aborted — nothing saved.")
        return

    # ── Build and write config ────────────────────────────────────
    config = {
        "name": name,
        "alerts": {
            "telegram": {
                "token":   token,
                "chat_id": chat_id,
            },
            "levels": {
                "info":     {"enabled": True},
                "warning":  {"enabled": True, "cooldown": warn_cooldown * 60},
                "critical": {"enabled": True, "cooldown": crit_cooldown * 60},
            },
        },
        "monitors": {
            "resources": {
                "cpu":         {"enabled": True, "warning": cpu_warn,  "critical": cpu_crit},
                "ram":         {"enabled": True, "warning": ram_warn,  "critical": ram_crit},
                "disk":        {"enabled": True, "warning": disk_warn, "critical": disk_crit},
                "temperature": {"enabled": has_temp, "warning": 70, "critical": 85},
                "network":     {"enabled": True, "check_dns": True, "check_outbound": True},
                "processes":   {"enabled": bool(watch_procs), "watch": watch_procs},
                "logs":        {"enabled": bool(watch_logs),  "watch": watch_logs},
            },
            "docker": {
                "enabled":    has_docker,
                "containers": docker_containers,
            },
            "redis": {
                "enabled": has_redis,
                **redis_cfg,
            },
            "postgresql": {
                "enabled": has_pg,
                **pg_cfg,
            },
            "mysql": {
                "enabled": has_mysql,
                **mysql_cfg,
            },
            "services": services,
            "custom":   custom_checks,
        },
    }

    with open("sentinel.yml", "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    click.echo("\n✅ Config saved to sentinel.yml")

    for flag, extra, label in [
        (has_docker, "docker",     "Docker"),
        (has_redis,  "redis",      "Redis"),
        (has_pg,     "postgresql", "PostgreSQL"),
        (has_mysql,  "mysql",      "MySQL"),
    ]:
        if flag:
            click.echo(f"📦 Installing {label} support...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install",
                 f"yoopi-sentinel[{extra}]", "--break-system-packages"],
                capture_output=True,
            )

    # ── 14. Systemd service ───────────────────────────────────────
    click.echo("")
    if click.confirm("Install as background service?", default=True):
        sentinel_bin = shutil.which("sentinel") or sys.argv[0]
        current_user = os.getenv("USER") or os.getenv("LOGNAME") or "root"
        home_dir = os.path.expanduser("~")
        service_content = f"""[Unit]
Description=Yoopi Sentinel
After=network.target

[Service]
Type=simple
User={current_user}
WorkingDirectory={home_dir}
ExecStart={sentinel_bin} start
Restart=always
RestartSec=10
StartLimitIntervalSec=0

[Install]
WantedBy=multi-user.target
"""
        result = subprocess.run(
            ["sudo", "tee", "/etc/systemd/system/sentinel.service"],
            input=service_content,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            if "permission denied" in result.stderr.lower():
                click.echo("❌ Permission denied — run with sudo or as root.")
            else:
                click.echo(f"❌ Failed to write service file: {result.stderr.strip()}")
            return
        for cmd, label in [
            (["sudo", "systemctl", "daemon-reload"], "Reloading systemd daemon"),
            (["sudo", "systemctl", "enable", "sentinel"], "Enabling sentinel on boot"),
            (["sudo", "systemctl", "restart", "sentinel"], "Starting sentinel"),
        ]:
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                click.echo(f"❌ {label} failed: {r.stderr.strip()}")
                return
        click.echo("✅ Sentinel is running as a service")
    else:
        click.echo("\n🚀 Run 'sentinel start' to begin monitoring!")
    click.echo("─" * 40 + "\n")


@cli.command()
@click.option("--config", "-c", default="sentinel.yml", help="Path to config file")
@click.option("--daemon", "-d", is_flag=True,           help="Fork to background and write PID to /tmp/sentinel.pid")
def start(config, daemon):
    """Start the Sentinel monitoring agent."""
    config_path = os.path.abspath(config)
    if not os.path.exists(config_path):
        click.echo(f"❌ Config file not found: {config_path}")
        sys.exit(1)
    if daemon:
        _start_daemon(config_path)
        return
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    from sentinel import config as cfg_loader
    from sentinel.agent import Agent
    cfg   = cfg_loader.load(config_path)
    agent = Agent(cfg)
    agent.start()


def _start_daemon(config_path):
    try:
        pid = os.fork()
        if pid > 0:
            import time
            time.sleep(1)
            if os.path.exists(_PID_FILE):
                with open(_PID_FILE) as f:
                    daemon_pid = f.read().strip()
                click.echo(f"✅ Sentinel started in background  (PID {daemon_pid})")
                click.echo(f"   PID file: {_PID_FILE}")
                click.echo(f"   Stop with: kill $(cat {_PID_FILE})")
            else:
                click.echo("✅ Sentinel started in background")
            return
    except AttributeError:
        click.echo("❌ --daemon is not supported on this OS (requires Unix fork)")
        sys.exit(1)
    os.setsid()
    try:
        pid = os.fork()
        if pid > 0:
            os._exit(0)
    except OSError:
        os._exit(1)
    sys.stdout.flush()
    sys.stderr.flush()
    with open(os.devnull, "r") as devnull:
        os.dup2(devnull.fileno(), sys.stdin.fileno())
    with open("/tmp/sentinel.log", "a") as logfile:
        os.dup2(logfile.fileno(), sys.stdout.fileno())
        os.dup2(logfile.fileno(), sys.stderr.fileno())
    with open(_PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        filename="/tmp/sentinel.log",
    )
    from sentinel import config as cfg_loader
    from sentinel.agent import Agent
    try:
        cfg   = cfg_loader.load(config_path)
        agent = Agent(cfg)
        agent.start()
    finally:
        if os.path.exists(_PID_FILE):
            os.remove(_PID_FILE)



@cli.command("update")
def update():
    """Update Sentinel to the latest version from GitHub."""
    click.echo("\n🔄 Updating Yoopi Sentinel...\n")
    result = subprocess.run(
        [
            sys.executable, "-m", "pip", "install",
            f"git+{_REPO_URL}",
            "--break-system-packages",
            "--force-reinstall",
            "--quiet",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        click.echo("❌ Update failed:\n")
        click.echo(result.stderr.strip())
        sys.exit(1)
    click.echo("✅ Sentinel updated successfully")
    ver_result = subprocess.run(
        [sys.executable, "-m", "pip", "show", "yoopi-sentinel"],
        capture_output=True, text=True,
    )
    for line in ver_result.stdout.splitlines():
        if line.lower().startswith("version"):
            click.echo(f"   {line}")
            break
    if _has_systemd() and _service_exists():
        click.echo(f"\n🔄 Restarting systemd service '{_SERVICE_NAME}'...")
        result = subprocess.run(
            ["sudo", "systemctl", "restart", _SERVICE_NAME],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            click.echo(f"⚠️  Service restart failed: {result.stderr.strip()}")
            click.echo(f"   Run 'sudo systemctl restart sentinel' manually to apply the update")
        else:
            click.echo(f"✅ Service restarted")
            subprocess.run(["sudo", "systemctl", "status", _SERVICE_NAME, "--no-pager", "-l"])
    else:
        click.echo("\n   No systemd service found — restart Sentinel manually.")
    click.echo()


@cli.command()
@click.option("--config", "-c", default="sentinel.yml", help="Path to config file")
def status(config):
    """Print current server status to terminal."""
    from sentinel import config as cfg_loader
    cfg  = cfg_loader.load(config)
    import psutil
    cpu  = psutil.cpu_percent(interval=1)
    mem  = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    click.echo(f"\n📊 {cfg['name']} — Sentinel Status\n")
    click.echo(f"  CPU:  {cpu:.1f}%")
    click.echo(f"  RAM:  {mem.percent:.1f}%")
    click.echo(f"  Disk: {disk.percent:.1f}%")
    click.echo()


def _has_systemd():
    try:
        result = subprocess.run(
            ["systemctl", "--version"],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _service_exists():
    return os.path.exists(_SERVICE_PATH)



if __name__ == "__main__":
    cli()
