"""Tests for the poll interval choice. Loads polling.py by path, like test_rise.py."""
import importlib.util
import pathlib
import unittest
from datetime import timedelta

_POLLING_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "custom_components" / "fellow" / "polling.py"
)
_spec = importlib.util.spec_from_file_location("fellow_polling", _POLLING_PATH)
polling = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(polling)

ACTIVE = timedelta(seconds=5)
IDLE = timedelta(seconds=60)


def interval(busy=False, failures=0):
    return polling.poll_interval(busy=busy, failures=failures, max_failures=6,
                                 active=ACTIVE, idle=IDLE)


class PollIntervalTest(unittest.TestCase):

    def test_busy_polls_fast(self):
        self.assertEqual(interval(busy=True), ACTIVE)

    def test_idle_uses_configured_interval(self):
        self.assertEqual(interval(), IDLE)

    def test_failed_polls_are_followed_up_fast(self):
        for failures in range(1, 7):
            for busy in (False, True):
                with self.subTest(failures=failures, busy=busy):
                    self.assertEqual(interval(busy, failures), ACTIVE)

    def test_offline_kettle_falls_back_to_idle(self):
        # Past max_failures HA marks it unavailable; don't hammer it.
        for busy in (False, True):
            with self.subTest(busy=busy):
                self.assertEqual(interval(busy, failures=7), IDLE)

    def test_idle_shorter_than_active_is_respected(self):
        # Not reachable through the options flow (min 5 s), but the
        # function shouldn't silently override it.
        fast = timedelta(seconds=2)
        self.assertEqual(polling.poll_interval(
            busy=False, failures=0, max_failures=6, active=ACTIVE, idle=fast,
        ), fast)


if __name__ == "__main__":
    unittest.main()
