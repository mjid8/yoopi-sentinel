import click
import sys
import os
import subprocess
import requests
import yaml

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
    click.echo("\n☀️  Welcome to Yoopi Sentinel Setup\n")
    click.echo("─" * 40)
    name  = click.prompt("Server name (e.g. API-Server, DB-Server)", default="My-Server")
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
    click.echo("\n🔍 What's running on this server?")
    has_docker = click.confirm("Docker containers?", default=False)
    has_pg     = click.confirm("PostgreSQL?",        default=False)
    has_mysql  = click.confirm("MySQL?",             default=False)
    config = {
        "name": name,
        "alerts": {
            "telegram": {
                "token":   token,
                "chat_id": chat_id,
            },
            "levels": {
                "info":     {"enabled": True},
                "warning":  {"enabled": True, "cooldown": 900},
                "critical": {"enabled": True, "cooldown": 300},
            }
        },
        "monitors": {
            "resources": {
                "cpu":         {"enabled": True, "warning": 60, "critical": 85},
                "ram":         {"enabled": True, "warning": 60, "critical": 85},
                "disk":        {"enabled": True, "warning": 75, "critical": 90},
                "temperature": {"enabled": True, "warning": 70, "critical": 85},
                "network":     {"enabled": True, "check_dns": True, "check_outbound": True},
                "processes":   {"enabled": True, "watch": []},
                "logs":        {"enabled": True, "watch": []},
            },
            "docker":     {"enabled": has_docker},
            "postgresql": {"enabled": has_pg},
            "mysql":      {"enabled": has_mysql},
            "services":   [],
            "custom":     [],
        }
    }
    with open("sentinel.yml", "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    click.echo("\n✅ Config saved to sentinel.yml")
    extras = []
    if has_docker: extras.append("docker")
    if has_pg:     extras.append("postgresql")
    if has_mysql:  extras.append("mysql")
    if extras:
        click.echo(f"\n📦 Install optional packages:")
        click.echo(f"   pip install yoopi-sentinel[{','.join(extras)}]")
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


@cli.command("install")
@click.option("--config", "-c", default="/etc/sentinel/sentinel.yml",
              help="Path to config file the service will use")
def install(config):
    """Install Sentinel as a systemd service."""
    click.echo("\n🔧 Sentinel — systemd installer\n")
    has_systemd = _has_systemd()
    if not has_systemd:
        _print_manual_instructions(config)
        return
    try:
        current_user = subprocess.check_output(["whoami"], text=True).strip()
    except Exception:
        current_user = os.environ.get("USER", "root")
    sentinel_bin = _which("sentinel")
    if not sentinel_bin:
        click.echo("❌ Could not find the 'sentinel' binary in PATH.")
        click.echo("   Make sure yoopi-sentinel is installed: pip install yoopi-sentinel")
        sys.exit(1)
    click.echo(f"  User:    {current_user}")
    click.echo(f"  Binary:  {sentinel_bin}")
    click.echo(f"  Config:  {config}")
    click.echo(f"  Service: {_SERVICE_PATH}\n")
    if not os.path.exists(config):
        click.echo(f"⚠️  Config file not found at {config}")
        click.echo(f"   Create it first with 'sentinel init', then move it to {config}")
        click.echo(f"   Continuing to write the service unit anyway...\n")
    service_content = f"""[Unit]
Description=Yoopi Sentinel — Server Monitoring
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=3

[Service]
Type=simple
User={current_user}
ExecStart={sentinel_bin} start --config {config}
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
    try:
        with open(_SERVICE_PATH, "w") as f:
            f.write(service_content)
        click.echo(f"✅ Service file written to {_SERVICE_PATH}")
    except PermissionError:
        click.echo(f"❌ Permission denied writing to {_SERVICE_PATH}")
        click.echo(f"   Run this command with sudo.")
        sys.exit(1)
    steps = [
        (["systemctl", "daemon-reload"],         "Reloading systemd daemon"),
        (["systemctl", "enable", _SERVICE_NAME], f"Enabling {_SERVICE_NAME} on boot"),
        (["systemctl", "start",  _SERVICE_NAME], f"Starting {_SERVICE_NAME}"),
    ]
    for cmd, label in steps:
        click.echo(f"  ⏳ {label}...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            click.echo(f"  ❌ Failed: {result.stderr.strip()}")
            sys.exit(1)
        click.echo(f"  ✅ Done")
    click.echo("\n── Service status ──────────────────────")
    subprocess.run(["systemctl", "status", _SERVICE_NAME, "--no-pager", "-l"])
    click.echo("\n✅ Sentinel is installed and running as a system service.")
    click.echo(f"   Logs:    journalctl -u {_SERVICE_NAME} -f")
    click.echo(f"   Stop:    systemctl stop {_SERVICE_NAME}")
    click.echo(f"   Restart: systemctl restart {_SERVICE_NAME}\n")


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
            ["systemctl", "restart", _SERVICE_NAME],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            click.echo(f"⚠️  Service restart failed: {result.stderr.strip()}")
            click.echo(f"   Restart manually: systemctl restart {_SERVICE_NAME}")
        else:
            click.echo(f"✅ Service restarted")
            subprocess.run(["systemctl", "status", _SERVICE_NAME, "--no-pager", "-l"])
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


def _which(binary):
    try:
        path = subprocess.check_output(["which", binary], text=True).strip()
        return path if path else None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _print_manual_instructions(config_path):
    sentinel_bin = _which("sentinel") or "/usr/local/bin/sentinel"
    try:
        current_user = subprocess.check_output(["whoami"], text=True).strip()
    except Exception:
        current_user = "your-user"
    click.echo("⚠️  systemd not detected on this system.\n")
    click.echo("To run Sentinel as a background service, choose one of:\n")
    click.echo("── Option 1: screen / tmux ──────────────────────")
    click.echo(f"   screen -dmS sentinel sentinel start --config {config_path}")
    click.echo(f"   # or")
    click.echo(f"   tmux new-session -d -s sentinel 'sentinel start --config {config_path}'")
    click.echo("\n── Option 2: nohup ──────────────────────────────")
    click.echo(f"   nohup sentinel start --config {config_path} > /tmp/sentinel.log 2>&1 &")
    click.echo("\n── Option 3: manual service file ────────────────")
    click.echo(f"   Save this to /etc/systemd/system/sentinel.service:\n")
    click.echo(f"   [Unit]")
    click.echo(f"   Description=Yoopi Sentinel")
    click.echo(f"   After=network.target")
    click.echo(f"")
    click.echo(f"   [Service]")
    click.echo(f"   Type=simple")
    click.echo(f"   User={current_user}")
    click.echo(f"   ExecStart={sentinel_bin} start --config {config_path}")
    click.echo(f"   Restart=on-failure")
    click.echo(f"")
    click.echo(f"   [Install]")
    click.echo(f"   WantedBy=multi-user.target")
    click.echo()


if __name__ == "__main__":
    cli()
