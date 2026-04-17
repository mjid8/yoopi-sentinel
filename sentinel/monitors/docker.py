import time
import logging
import re
from collections import defaultdict
from sentinel.core.verifier import Verifier

logger = logging.getLogger("sentinel.monitors.docker")


class DockerMonitor:
    def __init__(self, config, alerter):
        self.cfg     = config["monitors"].get("docker", {})
        self.name    = config["name"]
        self.alerter = alerter
        self.client  = None
        self.verifier = Verifier()

        self._container_states   = {}
        self._container_restarts = defaultdict(list)
        self._available          = False

        if not self.cfg.get("enabled", False):
            return

        self._init_client()

    def _init_client(self):
        try:
            import docker
            self.client     = docker.from_env()
            self._available = True
            logger.info("[Docker] Monitor initialized")
        except ImportError:
            logger.warning(
                "[Docker] 'docker' package not installed.\n"
                "Run: pip install yoopi-sentinel[docker]"
            )
        except Exception as e:
            logger.warning(f"[Docker] Could not connect to Docker daemon: {e}")

    def _get_containers(self):
        try:
            return self.client.containers.list(all=True)
        except Exception as e:
            logger.error(f"[Docker] Failed to list containers: {e}")
            return []

    def check_containers(self):
        if not self._available:
            return []

        now        = time.time()
        containers = self._get_containers()
        expected   = self.cfg.get("expected", [])

        for c in containers:
            name    = c.name
            status  = c.status   # "running", "exited", "restarting", etc.
            is_up   = status == "running"
            key     = f"container_{name}"
            prev    = self._container_states.get(name)

            # Container went down
            if prev == "running" and not is_up:
                if self.verifier.check(key, True):
                    self.alerter.send(
                        f"🚨 *Container Down*\n`{name}`\nStatus: `{status}`",
                        level="critical", key=key
                    )

            # Container recovered
            elif prev and prev != "running" and is_up:
                self.alerter.reset_cooldown(key)
                self.alerter.send(
                    f"✅ *Container Recovered*\n`{name}` is running again",
                    level="info", key=f"{key}_recovered"
                )
                self.verifier.clear(key)

            # Crash loop detection
            if is_up:
                try:
                    # Check if it restarted recently via uptime in attrs
                    started = c.attrs.get("State", {}).get("StartedAt", "")
                    if started:
                        from datetime import datetime, timezone
                        start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                        age_secs = (datetime.now(timezone.utc) - start_dt).total_seconds()
                        if age_secs < 120:   # started less than 2 min ago
                            self._container_restarts[name].append(now)
                            # Keep only restarts in last 10 min
                            self._container_restarts[name] = [
                                t for t in self._container_restarts[name]
                                if now - t < 600
                            ]
                            count = len(self._container_restarts[name])
                            if count >= 3:
                                self.alerter.send(
                                    f"🔁 *Crash Loop Detected*\n`{name}`\nRestarted `{count}x` in 10 minutes",
                                    level="critical", key=f"loop_{name}"
                                )
                                self._container_restarts[name] = []
                except Exception:
                    pass

            self._container_states[name] = status

        # Check expected containers that might be missing entirely
        running_names = {c.name for c in containers}
        for expected_name in expected:
            if expected_name not in running_names:
                key = f"container_missing_{expected_name}"
                if self.verifier.check(key, True):
                    self.alerter.send(
                        f"🚨 *Expected Container Missing*\n`{expected_name}` not found on this server",
                        level="critical", key=key
                    )

        return containers

    def snapshot(self):
        """Return container status for /status command."""
        if not self._available:
            return None

        containers = self._get_containers()
        up   = [c.name for c in containers if c.status == "running"]
        down = [(c.name, c.status) for c in containers if c.status != "running"]

        return {
            "total": len(containers),
            "up":    up,
            "down":  down,
        }

    def run(self):
        if not self._available:
            return
        self.check_containers()
