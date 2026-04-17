import logging
from sentinel.core.verifier import Verifier

logger = logging.getLogger("sentinel.monitors.redis")


class RedisMonitor:
    def __init__(self, config, alerter):
        self.cfg      = config["monitors"].get("redis", {})
        self.alerter  = alerter
        self.verifier = Verifier()

        self._was_up    = True
        self._available = False

        if not self.cfg.get("enabled", False):
            return

        self._init()

    def _init(self):
        try:
            import redis
            self._available = True
            logger.info("[Redis] Monitor initialized")
        except ImportError:
            logger.warning(
                "[Redis] 'redis' package not installed.\n"
                "Run: pip install yoopi-sentinel[redis]"
            )

    def _client(self):
        import redis
        return redis.Redis(
            host     = self.cfg.get("host",     "localhost"),
            port     = self.cfg.get("port",     6379),
            password = self.cfg.get("password", None),
            db       = self.cfg.get("db",       0),
            socket_connect_timeout = 5,
        )

    def check(self):
        if not self._available:
            return

        key = "redis_down"
        try:
            r = self._client()
            r.ping()
            is_up = True
        except Exception:
            is_up = False

        if not is_up:
            if self.verifier.check(key, True):
                if self._was_up:
                    self._was_up = False
                    self.alerter.send(
                        f"🔴 *Redis DOWN*\nCache/queue server not responding.",
                        level="critical", key=key
                    )
            return

        if not self._was_up:
            self._was_up = True
            self.alerter.reset_cooldown(key)
            self.alerter.send(
                f"✅ *Redis Recovered*\nCache server is back online",
                level="info"
            )
        self.verifier.clear(key)

        # Memory usage
        try:
            r    = self._client()
            info = r.info("memory")
            used = info.get("used_memory", 0)
            max_ = info.get("maxmemory", 0)

            if max_ > 0:
                pct = (used / max_) * 100
                mem_threshold = self.cfg.get("memory_warning", 80)
                if self.verifier.check("redis_mem", pct > mem_threshold, value=pct):
                    self.alerter.send(
                        f"🔴 *Redis — High Memory*\n"
                        f"Usage: `{pct:.1f}%`\nThreshold: `{mem_threshold}%`",
                        level="warning", key="redis_mem"
                    )

            # Connected clients
            clients    = r.info("clients").get("connected_clients", 0)
            max_clients = self.cfg.get("max_clients", 100)
            if clients > max_clients:
                self.alerter.send(
                    f"🔴 *Redis — High Client Count*\n"
                    f"Connected: `{clients}`\nThreshold: `{max_clients}`",
                    level="warning", key="redis_clients"
                )
        except Exception as e:
            logger.debug(f"[Redis] Info check failed: {e}")

    def snapshot(self):
        if not self._available:
            return None
        try:
            r = self._client()
            r.ping()
            return {"up": True}
        except Exception:
            return {"up": False}

    def run(self):
        if not self._available:
            return
        self.check()
