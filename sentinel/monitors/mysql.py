import logging
from sentinel.core.verifier import Verifier

logger = logging.getLogger("sentinel.monitors.mysql")


class MySQLMonitor:
    def __init__(self, config, alerter):
        self.cfg      = config["monitors"].get("mysql", {})
        self.name     = config["name"]
        self.alerter  = alerter
        self.verifier = Verifier()
        self._was_up    = True
        self._available = False
        if not self.cfg.get("enabled", False):
            return
        self._init()

    def _init(self):
        try:
            import pymysql
            self._available = True
            logger.info("[MySQL] Monitor initialized")
        except ImportError:
            logger.warning(
                "[MySQL] 'pymysql' not installed.\n"
                "Run: pip install yoopi-sentinel[mysql]"
            )

    def _connect(self):
        import pymysql
        return pymysql.connect(
            host            = self.cfg.get("host",     "localhost"),
            port            = self.cfg.get("port",     3306),
            database        = self.cfg.get("database", "mysql"),
            user            = self.cfg.get("user",     "root"),
            password        = self.cfg.get("password", ""),
            connect_timeout = 5,
        )

    def _query(self, sql):
        try:
            conn = self._connect()
            cur  = conn.cursor()
            cur.execute(sql)
            result = cur.fetchone()
            cur.close()
            conn.close()
            return result
        except Exception as e:
            logger.debug(f"[MySQL] Query failed: {e}")
            return None

    def check(self):
        if not self._available:
            return
        try:
            conn = self._connect()
            conn.close()
            is_up = True
        except Exception:
            is_up = False
        key = "mysql_down"
        if not is_up:
            if self.verifier.check(key, True):
                if self._was_up:
                    self._was_up = False
                    self.alerter.send(
                        f"🗄️ *MySQL DOWN*\n"
                        f"Database is not responding.\n"
                        f"All dependent services will fail.",
                        level="critical", key=key
                    )
            return
        if not self._was_up:
            self._was_up = True
            self.alerter.reset_cooldown(key)
            self.alerter.send(
                f"✅ *MySQL Recovered*\nDatabase is responding normally",
                level="info"
            )
        self.verifier.clear(key)
        max_conn = self.cfg.get("max_connections", 80)
        result   = self._query("SHOW STATUS LIKE 'Threads_connected';")
        if result:
            count = int(result[1])
            if self.verifier.check("mysql_conn", count > max_conn, value=count):
                self.alerter.send(
                    f"🗄️ *MySQL — High Connections*\n"
                    f"Connected threads: `{count}`\nThreshold: `{max_conn}`",
                    level="warning", key="mysql_conn"
                )
        slow = self._query("SHOW STATUS LIKE 'Slow_queries';")
        if slow:
            slow_count     = int(slow[1])
            slow_threshold = self.cfg.get("slow_query_threshold", 10)
            if slow_count > slow_threshold:
                self.alerter.send(
                    f"🗄️ *MySQL — Slow Queries*\n"
                    f"Count: `{slow_count}`\nThreshold: `{slow_threshold}`",
                    level="warning", key="mysql_slow"
                )
        if self.cfg.get("check_replication", False):
            rep = self._query("SHOW SLAVE STATUS;")
            if rep:
                lag           = rep[32] if len(rep) > 32 else None
                lag_threshold = self.cfg.get("replication_lag_seconds", 60)
                if lag and int(lag) > lag_threshold:
                    self.alerter.send(
                        f"🗄️ *MySQL — Replication Lag*\n"
                        f"Lag: `{lag}s`\nThreshold: `{lag_threshold}s`",
                        level="warning", key="mysql_replication"
                    )

    def snapshot(self):
        if not self._available:
            return None
        try:
            conn = self._connect()
            conn.close()
            is_up = True
        except Exception:
            is_up = False
        result = {"up": is_up}
        if is_up:
            threads = self._query("SHOW STATUS LIKE 'Threads_connected';")
            result["connections"] = int(threads[1]) if threads else "?"
        return result

    def run(self):
        if not self._available:
            return
        self.check()
