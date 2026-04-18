# yoopi sentinel ☀️

lightweight server monitoring that sends alerts straight to your telegram
built this for fun and to learn

---

# why i made this

- prometheus and grafana take forever to set up
- datadog costs money every month
- most tools spam false alerts or go silent when something actually breaks
- wanted something simple i could install in 2 minutes and forget about

---

# what it monitors

system — cpu ram disk temperature network connections uptime

optional — docker containers postgresql mysql redis

services — any http or https endpoint you want to check

custom — run any script and alert if it fails

---

# install

requires python 3 on your server

```bash
pip install yoopi-sentinel --break-system-packages
sentinel init
```

or if you want one command that handles everything including python check

```bash
curl -sSL https://raw.githubusercontent.com/mjid8/yoopi-sentinel/main/install.sh | bash
```

---

# what the wizard does

- asks your server name and telegram bot token
- auto detects your chat id — no manual lookup
- asks what is running on this server
- installs required extras automatically
- sets up systemd service so it runs forever in background

---

# after install

```bash
systemctl status sentinel       # is it running
journalctl -u sentinel -f       # live logs
sentinel update                 # pull latest version
```

---

# telegram commands

/status   full server report — ram disk cpu uptime processes
/top      top 10 processes by cpu and ram
/disk     disk usage breakdown
/net      network connections and ports
/help     all commands

reconfigure anytime with sentinel init

---

# the never lie system (well not 100% but i tried my best and will keep improving)

most monitoring tools go silent when network drops or send false alerts from 10 second spikes

sentinel checks twice before alerting — if cpu hits 90% for 10 seconds and recovers it wont wake you up

if network drops it buffers all alerts locally and sends a summary when connection comes back

every status shows how fresh the data is so you always know if youre looking at current info

---

## os support

| os | tested |
|---|---|
| ubuntu 20 22 24 | ✅ |
| debian 11 12 | ✅ |
| centos 8 rocky 9 | ✅ |
| fedora 38+ | ✅ |
| alpine | ✅ |
| raspberry pi | ✅ |

---

## roadmap

- [x] cpu ram disk temperature network
- [x] docker postgresql mysql redis
- [x] double verification no false alarms
- [x] offline detection missed alerts summary
- [x] systemd auto setup
- [x] pip install from pypi
- [ ] sentinel-watch external watchdog
- [ ] kubernetes
- [ ] mongodb
- [ ] slack discord email alerts

---

# about

built by majid as a learning project 
got some free resources and help from
[yoopi technologies](https://yoopitech.com) — gpl v3

leave a ⭐ if it helped and open an issue if something breaks
