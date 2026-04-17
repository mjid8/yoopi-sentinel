# ☀️ Yoopi Sentinel

lightweight server monitoring straight to your telegram no dashboards no complexity just create a bot and go

---

## why i made this

i got tired of tools that are either too complex or too expensive so i built my own

- prometheus + grafana takes days to setup
- datadog costs $15-30/server/month
- most tools spam false alerts or go silent when network drops
- sentinel tries to fix all that

---

## what it monitors

**always included**
- cpu ram disk temperature
- network connectivity
- processes — alerts if something dies
- log files — keyword pattern alerts

**optional**
- docker containers crash loops detection
- postgresql mysql redis
- custom http checks custom scripts

---

## the never lie system

i cant promise 100% but i tried my best

before any alert sentinel checks twice — if cpu spikes for 10 seconds and recovers it wont wake you up at 3am

if network drops it buffers the alerts and sends a summary when its back

every /status shows how old the data is so you always know if youre looking at fresh info or not

---

## quick start

    pip install yoopi-sentinel

with extras

    pip install yoopi-sentinel[docker]
    pip install yoopi-sentinel[postgresql]
    pip install yoopi-sentinel[redis]
    pip install yoopi-sentinel[full]

then run

    sentinel init

wizard asks your server name sets up telegram bot and generates the config automatically

then

    sentinel start

thats it

---

## telegram commands

once running send to your bot

    /status    full server status
    /help      available commands

---

## run as a service so it survives reboots

    sudo systemctl enable sentinel
    sudo systemctl start sentinel

---

## one line install for fresh servers

    curl -sSL https://install.yoopi.tech/sentinel | bash

detects your os installs python if missing sets everything up automatically

---

## important

sentinel is read only — it never touches your system never restarts services never opens ports just watches and alerts

---

## os support

ubuntu debian centos fedora alpine raspberry pi

---

## faq

**is my data private** yes your bot your data nothing goes through yoopi servers

**does it work offline** no needs internet to send alerts but buffers them if connection drops temporarily

**will it slow my server** no its designed to be invisible uses almost nothing

---

## roadmap

- [x] cpu ram disk temperature network processes logs
- [x] docker postgresql mysql redis
- [x] double verification no false alarms
- [x] offline detection missed alerts summary
- [ ] sentinel-watch external watchdog
- [ ] kubernetes mongodb
- [ ] more alert channels slack discord email

---

built by majid — [yoopi technologies](https://yoopitech.com)

*leave a ⭐ if this helped and open an issue if you have ideas*
