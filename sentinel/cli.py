import click
import sys
import os
import requests
import yaml

@click.group()
def cli():
    """Yoopi Sentinel — Honest server monitoring."""
    pass


# ── sentinel init ────────────────────────────────────────────────
@cli.command()
def init():
    """Setup wizard — creates your sentinel.yml config."""
    click.echo("\n☀️  Welcome to Yoopi Sentinel Setup\n")
    click.echo("─" * 40)

    # Step 1 — Server name
    name = click.prompt("Server name (e.g. API-Server, DB-Server)", default="My-Server")

    # Step 2 — Telegram token
    click.echo("\n📱 Telegram Bot Setup")
    click.echo("   1. Open Telegram → search @BotFather")
    click.echo("   2. Send: /newbot")
    click.echo("   3. Follow the steps and copy your token\n")
    token = click.prompt("Paste your bot token here")

    # Validate token
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

    # Step 3 — Auto-detect Chat ID
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

    # Step 4 — What to monitor
    click.echo("\n🔍 What's running on this server?")
    has_docker = click.confirm("Docker containers?", default=False)
    has_pg     = click.confirm("PostgreSQL?",        default=False)
    has_mysql  = click.confirm("MySQL?",             default=False)

    # Build config
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
            "postgresql":  {"enabled": has_pg},
            "mysql":      {"enabled": has_mysql},
            "services":   [],
            "custom":     [],
        }
    }

    # Write config
    with open("sentinel.yml", "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    click.echo("\n✅ Config saved to sentinel.yml")

    # Optional package installs
    extras = []
    if has_docker: extras.append("docker")
    if has_pg:     extras.append("postgresql")
    if has_mysql:  extras.append("mysql")

    if extras:
        click.echo(f"\n📦 Install optional packages:")
        click.echo(f"   pip install yoopi-sentinel[{','.join(extras)}]")

    click.echo("\n🚀 Run 'sentinel start' to begin monitoring!")
    click.echo("─" * 40 + "\n")


# ── sentinel start ───────────────────────────────────────────────
@cli.command()
@click.option("--config", "-c", default="sentinel.yml", help="Path to config file")
def start(config):
    """Start the Sentinel monitoring agent."""
    from sentinel import config as cfg_loader
    from sentinel.agent import Agent

    logging.setup = True
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg = cfg_loader.load(config)
    agent = Agent(cfg)
    agent.start()


# ── sentinel status ──────────────────────────────────────────────
@cli.command()
@click.option("--config", "-c", default="sentinel.yml", help="Path to config file")
def status(config):
    """Print current server status to terminal."""
    from sentinel import config as cfg_loader
    from sentinel.monitors.resources import ResourceMonitor
    from sentinel.monitors.docker import DockerMonitor

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


if __name__ == "__main__":
    cli()
