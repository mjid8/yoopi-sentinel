☀️ Yoopi Sentinel

**Honest lightweight server monitoring with Telegram alerts**  
Built for developers and sysadmins who want to know the truth about their server status just from theyre phones  instantly without complexity just create a telegram bot and you are ready to go

> *"Production monitoring in 2 minutes, not 2 days."*

---

## Why i made Sentinel? first of all for fun and educational purposes

 some issues and problems and How Sentinel approach them

- tools like Prometheus + Grafana takes days to set up 
- Datadog costs $15–30/server/month
- False alerts from momentary spikes (sentinel does a Double-verification before every alert )
- Silence when network is down 
- Stale data presented as current
- One-size-fits-all installs Install only what you need |


## What It Monitors

### 🖥️ System Resources *(always included)*
- CPU usage — warning + critical thresholds
- RAM usage — warning + critical thresholds
- Disk usage — warning + critical thresholds
- CPU temperature — sensor-aware
- Network connectivity — DNS + outbound checks
- Running processes — alert if required process dies
- Log files — keyword pattern matching with thresholds

### 🐳 Docker *(optional)*
- Container up/down detection
- Crash loop detection (3+ restarts in 10 min)
- Expected container missing alerts

### 🗄️ Databases *(optional)*
- **PostgreSQL** — connection count, long-running queries, replication lag, DB size
- **MySQL** — connection count, slow queries, replication lag
- **Redis** — memory usage, connected clients, ping health

### 🌐 Services *(zero extra packages)*
- HTTP health checks with expected status codes
- Custom scripts — run any bash/python check
- File existence checks
- Process running checks

----------------------------------------------------------------------------------

## The "Never Lie" System of course we cant be always 100% sure but i try my best 

Most monitoring tools stay silent when they can't reach you. Sentinel doesn't.

**1. Double-verification before every alert**

CPU spike detected at 91%
→ Wait for next check cycle
→ Still 91%? → ALERT 🔴
→ Recovered? → Ignore, was a spike ✅

**2. Smart escalation — never repeat, always escalate**

14:00 🟠 CPU Warning — 72%     ← alerted
14:15 CPU still 72%             ← suppressed (cooldown)
14:20 CPU now 91%               ← alerted again (escalated to critical)
14:35 CPU back to 45%           ← ✅ Recovery alert sent


**3. Offline detection + missed alerts summary**

Network drops for 23 minutes
→ Sentinel buffers all alerts locally
→ Network restored
→ Sends: "⚠️ Sentinel was offline 23 min — 2 alerts missed: "


**4. Data freshness on every /status**

📊 API-Server Status
CPU: 45% ✅
RAM: 72% 🟠
⚠️ Network: last confirmed 8 min ago


---

## Quick Start

### 1. Install

in your server run these 

# Base install (system metrics only)
pip install yoopi-sentinel

# With Docker support
pip install yoopi-sentinel[docker]

# With PostgreSQL support
pip install yoopi-sentinel[postgresql]

# With MySQL support
pip install yoopi-sentinel[mysql]

# With Redis support
pip install yoopi-sentinel[redis]

# Everything
pip install yoopi-sentinel[full]

### 2. Setup

sentinel init

The wizard will:
- Ask for your server name
- Walk you through creating a Telegram bot (via @BotFather)
- **Auto-detect your chat ID** — no manual lookup
- Ask what's running on this server
- Generate your `sentinel.yml` config

### 3. Start

sentinel start

Sentinel will starts sends a startup message to Telegram and begins monitoring.

---

## Telegram Commands

Once running, you can run these on your bot:

/status`  Full server status — resources, containers, services
/help`  List all available commands there is more commands 

-----

## Configuration

Sentinel generates `sentinel.yml` automatically via `sentinel init`.  
Every single monitor can be turned on or off independently.


sudo systemctl daemon-reload
sudo systemctl enable sentinel
sudo systemctl start sentinel

# Check status
sudo systemctl status sentinel
-------

## One-Line Install (Fresh Server)

If Python/pip isn't installed yet:


curl -sSL https://install.yoopi.tech/sentinel | bash

This script will:
1. Detect your OS (Ubuntu, Debian, CentOS, Fedora, Arch)
2. Install Python 3 + pip if missing
3. Run `pip install yoopi-sentinel`
4. Run `sentinel init`
5. Set up systemd service automatically

---
 

Sentinel is **read-only by design**. It never restarts services, never modifies your system, never exposes any ports. It only observes and alerts.

---

## OS Support

| OS | Tested |
|---|---|
| Ubuntu 20.04 / 22.04 / 24.04 | ✅ |
| Debian 11 / 12 | ✅ |
| CentOS 8 / Rocky Linux 9 | ✅ |
| Fedora 38+ | ✅ |
| Alpine Linux | ✅ |
| Raspberry Pi OS | ✅ |

---

## FAQ



**Q: Is my data private?**  
A: Yes. Sentinel uses your own Telegram bot. Your data goes directly from your server to your Telegram — nothing passes through Yoopi servers.

**Q: Does it work without internet?**  
A: it needs the server to be online to send you the reports so no it does not work without internet 

**Q: Will it slow down my server?**  
A: No. Sentinel uses `psutil` for system metrics (very lightweight), sleeps 60 seconds between checks, and uses minimal CPU/RAM. It's designed to be invisible.

---

## Roadmap

- [x] System resource monitoring (CPU, RAM, disk, temperature)
- [x] Network connectivity monitoring
- [x] Process monitoring
- [x] Log file monitoring
- [x] Docker container monitoring
- [x] PostgreSQL monitoring
- [x] MySQL monitoring
- [x] Redis monitoring
- [x] Custom checks (HTTP, script, file, process)
- [x] Double-verification (no false alarms)
- [x] Offline detection + missed alerts
- [ ] `sentinel-watch` — external watchdog companion coming soon
- [ ] Kubernetes support
- [ ] MongoDB monitoring
- [ ] more report channels
- [ ] Web dashboard (optional)


## About

Built by  an me majid8 via resource help help from Yoopi Technologies (https://yoopitech.com)  

---

*If this helped you, leave a ⭐ — it helps others find it. please let me know if you have any improvement ideas*
