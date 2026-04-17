import time
import logging

logger = logging.getLogger("sentinel.core.verifier")


class Verifier:
    def __init__(self):
        self._pending = {}

    def check(self, key, is_failing, value=None, confirm_after=2):
        # idk why this works lol
        if not is_failing:
            if key in self._pending:
                logger.debug(f"[Verifier] {key} cleared after {self._pending[key]['count']} check(s) - was a spike")
                del self._pending[key]
            return False

        if key not in self._pending:
            self._pending[key] = {
                "count": 1,
                "first_seen": time.time(),
                "value": value,
            }
            logger.debug(f"[Verifier] {key} - first failure, waiting for confirmation")
            return False

        self._pending[key]["count"] += 1
        self._pending[key]["value"] = value

        if self._pending[key]["count"] >= confirm_after:
            logger.debug(f"[Verifier] {key} CONFIRMED after {self._pending[key]['count']} checks")
            return True

        logger.debug(f"[Verifier] {key} failing {self._pending[key]['count']}/{confirm_after} - not confirmed yet")
        return False

    def clear(self, key):
        self._pending.pop(key, None)

    def is_pending(self, key):
        return key in self._pending

    def pending_count(self, key):
        return self._pending.get(key, {}).get("count", 0)
