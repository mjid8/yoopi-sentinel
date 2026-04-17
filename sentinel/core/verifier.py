import time
import logging

logger = logging.getLogger("sentinel.core.verifier")


class Verifier:
    """
    double-checks conditions before we fire any alert.
    flow:
      1. first failure -> record it, dont alert yet
      2. next cycle still failing -> confirm and return True
      3. recovered in between -> clear it, was just a spike

    this is how we avoid waking someone up at 3am for a 10-second cpu blip
    """

    def __init__(self):
        # tracks pending failures: key -> {count, first_seen, value}
        self._pending = {}

    def check(self, key, is_failing, value=None, confirm_after=2):
        """
        key           - unique string id eg "cpu_warning"
        is_failing    - is the condition bad right now
        value         - current metric value (just for context/logging)
        confirm_after - how many consecutive fails before we confirm

        returns True only when confirmed, False otherwise
        """
        if not is_failing:
            # cleared - remove from pending if it was there
            if key in self._pending:
                logger.debug(f"[Verifier] {key} cleared after {self._pending[key]['count']} check(s) - was a spike")
                del self._pending[key]
            return False

        # still failing
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
        # call this manually on recovery
        self._pending.pop(key, None)

    def is_pending(self, key):
        return key in self._pending

    def pending_count(self, key):
        return self._pending.get(key, {}).get("count", 0)
