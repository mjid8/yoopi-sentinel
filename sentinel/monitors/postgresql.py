import logging
import time
from sentinel.core.verifier import Verifier

logger = logging.getLogger("sentinel.monitors.postgresql")


class PostgreSQLMonitor:
    def __init__(self, config, alerter):
        self.cfg      = config["monitors"].get("postgresql", {})
        self.name     = config["name"]
        self.alerter  = alerter
        self.verifier = Verifier()

        self._was_up     = True
        self._available  = False
        self._conn       = None

        if not self.cfg.get("enabled", False):
            return

        self._init()

    def _init(self):
        try:
            import psycopg2
            self._available = True
            logger.info("[PostgreSQL] Monitor initialized")
        except ImportError:
            logger.warning(
                "[PostgreSQL] 'psycopg2-binary' not installed.\n"
                "Run: pip install yoopi-sentinel[postgresql]"
            )

    def _connect(self):
        import psycopg2
        host     = self.cfg.get("host",     "localhost")
        port     = self.cfg.get("port",     5432)
        database = self.cfg.get("database", "postgres")
        user     = self.cfg.get("user",     "postgres")
        password = self.cfg.get("password", "")

        return psycopg2.connect(
            host=host, port=port,
            database=database, user=user,
            password=password, connect_timeout=5
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
            logger.debug(f"[PostgreSQL] Query failed: {e}")
            return None

    def check(self):
        if not self._available:
            return

        # Check if reachable
        try:
            conn = self._connect()
            conn.close()
            is_up = True
        except Exception:
            is_up = False

        key = "pg_down"

        if not is_up:
            if self.verifier.check(key, True):
                if self._was_up:
                    self._was_up = False
                    self.alerter.send(
                        f"🐘 *PostgreSQL DOWN*\n"
                        f"Database is not responding.\n"
                        f"All dependent services will fail.",
                        level="critical", key=key
                    )
            return

        # Recovered
        if not self._was_up:
            self._was_up = True
            self.alerter.reset_cooldown(key)
            self.alerter.send(
                f"✅ *PostgreSQL Recovered*\nDatabase is responding normally",
                level="info"
            )
        self.verifier.clear(key)

        # Connection count
        max_conn = self.cfg.get("max_connections", 80)
        result   = self._query("SELECT count(*) FROM pg_stat_activity;")
        if result:
            count = int(result[0])
            if self.verifier.check("pg_conn", count > max_conn, value=count):
                self.alerter.send(
                    f"🐘 *PostgreSQL — High Connections*\n"
                    f"Active: `{count}`\nThreshold: `{max_conn}`",
                    level="warning", key="pg_conn"
                )

        # DB size growth alert
        db = self.cfg.get("database", "postgres")
        size_result = self._query(
            f"SELECT pg_size_pretty(pg_database_size('{db}'));"
        )
        if size_result:
            logger.debug(f"[PostgreSQL] DB size: {size_result[0]}")

        # Long running queries
        long_query_sec = self.cfg.get("long_query_seconds", 30)
        long_result = self._query(
            f"SELECT count(*) FROM pg_stat_activity "
            f"WHERE state = 'active' AND query_start < now() - interval '{long_query_sec} seconds';"
        )
        if long_result and int(long_result[0]) > 0:
            count = int(long_result[0])
            self.alerter.send(
                f"🐘 *PostgreSQL — Long Running Queries*\n"
                f"`{count}` quer{'y' if count == 1 else 'ies'} running > {long_query_sec}s",
                level="warning", key="pg_long_query"
            )

        # Replication lag (if replica)
        if self.cfg.get("check_replication", False):
            rep = self._query(
                "SELECT EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp()))::INT;"
            )
            if rep and rep[0]:
                lag = int(rep[0])
                lag_threshold = self.cfg.get("replication_lag_seconds", 60)
                if lag > lag_threshold:
                    self.alerter.send(
                        f"🐘 *PostgreSQL — Replication Lag*\n"
                        f"Lag: `{lag}s`\nThreshold: `{lag_threshold}s`",
                        level="warning", key="pg_replication"
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
            db    = self.cfg.get("database", "postgres")
            conn_ = self._query("SELECT count(*) FROM pg_stat_activity;")
            size  = self._query(f"SELECT pg_size_pretty(pg_database_size('{db}'));")
            result["connections"] = int(conn_[0]) if conn_ else "?"
            result["size"]        = size[0] if size else "?"
        return result

    def run(self):
        if not self._available:
            return
        self.check()
