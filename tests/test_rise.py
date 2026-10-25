"""Tests for the rapid temperature-rise detector.

rise.py has no Home Assistant imports, so it is loaded directly by path to
avoid importing the `fellow` package (whose __init__ needs homeassistant).

Run with:  python -m unittest discover tests   (or: pytest tests)
"""
import importlib.util
import math
import pathlib
import sys
import types
import unittest

_RISE_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "custom_components" / "fellow" / "rise.py"
)
_spec = importlib.util.spec_from_file_location("fellow_rise", _RISE_PATH)
rise = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = rise  # dataclasses look the module up
_spec.loader.exec_module(rise)

# Real heat cycles on a Stagg EKG Pro (1200 W, firmware 1.1.75SSP), polled
# about once a second. Heat starts at t=0; (seconds, tempr °C).
FULL_RUN = [
    (1.3, 18.26), (2.5, 18.62), (3.7, 18.57), (4.9, 18.31), (6.2, 18.26),
    (7.4, 18.31), (8.6, 18.62), (9.9, 18.62), (11.1, 18.69), (12.5, 18.60),
    (13.7, 18.65), (14.9, 18.64), (16.1, 18.62), (17.4, 18.45), (18.6, 18.36),
    (19.8, 18.50), (21.0, 18.93), (22.3, 19.02), (23.5, 19.54), (24.9, 20.36),
    (26.4, 21.08), (27.6, 21.83), (28.8, 22.88), (30.0, 23.55), (31.2, 23.23),
    (32.5, 23.81), (33.7, 24.59), (34.9, 24.87), (36.2, 25.38), (37.4, 25.98),
    (39.0, 26.71), (40.6, 27.61), (41.8, 28.10), (43.0, 28.69), (44.4, 29.01),
    (45.6, 29.51), (46.8, 30.11), (48.1, 30.49), (49.3, 31.08), (50.5, 31.85),
    (51.8, 32.08), (53.1, 32.58), (54.3, 33.36), (55.6, 34.17), (56.8, 34.53),
    (58.0, 34.83),
]
LOW_RUN = [
    (1.3, 21.40), (2.7, 21.66), (4.1, 21.64), (5.4, 21.72), (6.6, 21.32),
    (7.8, 21.32), (9.1, 21.34), (10.3, 21.64), (11.5, 21.57), (12.7, 21.74),
    (14.0, 21.74), (15.2, 21.74), (16.8, 21.85), (18.0, 21.62), (19.2, 21.90),
    (20.5, 22.52), (22.1, 24.21), (23.3, 26.04), (24.5, 28.12), (25.8, 29.97),
    (27.0, 32.29), (28.2, 33.64), (29.6, 35.16), (30.9, 37.17), (32.2, 39.31),
    (33.4, 39.99), (34.6, 41.03), (35.8, 42.15), (37.1, 43.30), (38.3, 44.76),
]


def resample(run, interval):
    """Linearly interpolate a run onto a fixed poll interval."""
    out = []
    t = run[0][0]
    i = 0
    while t <= run[-1][0]:
        while run[i + 1][0] < t:
            i += 1
        (t0, v0), (t1, v1) = run[i], run[i + 1]
        out.append((t, v0 + (v1 - v0) * (t - t0) / (t1 - t0)))
        t += interval
    return out


def replay(detector, samples, heating=True):
    """Feed samples; return the times at which update() returned True."""
    return [t for t, temp in samples if detector.update(t, temp, heating)]


def ramp(rate, start=0.0, end=40.0, step=1.0):
    """A kettle rising at `rate` °C/s from 20 °C, polled every `step` s."""
    n = int((end - start) / step)
    return [(start + i * step, 20.0 + rate * i * step) for i in range(n + 1)]


class RapidRiseDetectorTest(unittest.TestCase):

    def test_real_runs_do_not_trigger(self):
        for name, run in (("full", FULL_RUN), ("low", LOW_RUN)):
            for label, samples in (("as polled", run),
                                   ("1 s", resample(run, 1.0)),
                                   ("5 s", resample(run, 5.0))):
                with self.subTest(run=name, polling=label):
                    detector = rise.RapidRiseDetector()
                    peak = 0.0
                    for t, temp in samples:
                        self.assertFalse(detector.update(t, temp, True))
                        peak = max(peak, detector.rate or 0.0)
                    self.assertGreater(peak, 0.3)
                    # Keep a clear margin below the default threshold.
                    self.assertLess(peak, rise.DEFAULT_RISE_THRESHOLD / 1.5)
        # ...but a low enough threshold does catch the low fill.
        self.assertNotEqual(replay(rise.RapidRiseDetector(threshold=1.0),
                                   LOW_RUN), [])

    def test_empty_kettle_triggers_once_after_grace(self):
        for step in (1.0, 5.0):
            with self.subTest(polling=step):
                detector = rise.RapidRiseDetector()
                fired = replay(detector, ramp(5.0, step=step))
                self.assertEqual(len(fired), 1)
                self.assertGreaterEqual(fired[0], rise.STARTUP_GRACE_SECONDS)
                self.assertLess(fired[0], rise.STARTUP_GRACE_SECONDS + step)
                self.assertAlmostEqual(detector.triggered_rate, 5.0)

    def test_missing_reading_clears_history(self):
        for missing in (math.nan, None):
            with self.subTest(reading=missing):
                detector = rise.RapidRiseDetector()
                replay(detector, [(0.0, 20.0), (25.0, 20.0)])
                detector.update(26.0, missing, True)
                self.assertIsNone(detector.rate)
                # Set back down much hotter: the gap must not read as a rise.
                self.assertFalse(detector.update(27.0, 60.0, True))
                self.assertFalse(detector.update(32.0, 61.0, True))
                self.assertAlmostEqual(detector.rate, 1.0 / 5.0)

    def test_latch_lasts_until_next_heat_cycle(self):
        detector = rise.RapidRiseDetector()
        replay(detector, ramp(5.0, end=30.0))
        detector.update(31.0, 170.0, False)
        self.assertTrue(detector.triggered)  # survives heating stopping

        # A new cycle clears it and restarts the grace period.
        fired = replay(detector, ramp(5.0, start=100.0, end=130.0))
        self.assertEqual(len(fired), 1)
        self.assertGreaterEqual(fired[0] - 100.0, rise.STARTUP_GRACE_SECONDS)

        detector.reset()  # what the coordinator does on a lift
        self.assertFalse(detector.triggered)
        self.assertIsNone(detector.triggered_rate)


class ModeTest(unittest.TestCase):

    def test_screen_suffixes_keep_the_base_mode(self):
        # Seen on a Stagg EKG Pro: S_Heat+tset while the dial was turned,
        # S_Heat+menu and S_Hold+menu with a menu open.
        heating = ("S_Heat", "S_Heat+menu", "S_Heat+tset", "S_StartupToTempr")
        holding = ("S_Hold", "S_Hold+menu")
        neither = ("S_Off", "S_Standby", "S_HeatOff", "", None)
        for mode in heating + holding + neither:
            with self.subTest(mode=mode):
                self.assertEqual(rise.is_heating_mode(mode), mode in heating)
                self.assertEqual(rise.is_holding_mode(mode), mode in holding)

    def test_turning_the_dial_does_not_pause_detection(self):
        detector = rise.RapidRiseDetector()
        # The dial is turned 15 s in, before the 20 s grace period ends.
        modes = ["S_Heat"] * 15 + ["S_Heat+tset"] * 3 + ["S_Heat"] * 20
        fired = [t for t, mode in enumerate(modes)
                 if detector.update(float(t), 20.0 + 5.0 * t,
                                    rise.is_heating_mode(mode))]
        self.assertEqual(fired, [20])


class AutoStopTrackerTest(unittest.TestCase):
    """Retry decisions, polled every 5 s like the coordinator."""

    @staticmethod
    def drive(polls, **kwargs):
        """`polls` is a list of (running, in_flight). Returns tracker, actions."""
        tracker = rise.AutoStopTracker(**kwargs)
        tracker.start(0.0)
        actions = [tracker.poll(i * 5.0, running, in_flight)
                   for i, (running, in_flight) in enumerate(polls)]
        return tracker, actions

    def test_retries_until_stopped(self):
        for sends in (1, 3):
            with self.subTest(sends=sends):
                tracker, actions = self.drive(
                    [(True, False)] * sends + [(False, False), (True, False)])
                self.assertEqual(actions, [rise.ACTION_SEND] * sends + [None, None])
                self.assertEqual(tracker.status, rise.STOP_STOPPED)
                self.assertEqual(tracker.attempts, sends)

    def test_waits_for_attempt_in_flight(self):
        tracker, actions = self.drive([
            (True, False), (True, True), (True, True),
            (True, False), (False, True),
        ])
        self.assertEqual(actions, [rise.ACTION_SEND, None, None,
                                   rise.ACTION_SEND, None])
        # The kettle turning off counts even while an attempt is running.
        self.assertEqual(tracker.status, rise.STOP_STOPPED)

    def test_gives_up_once(self):
        cases = {
            # Polls at 0..55 s send; the poll at 60 s gives up.
            "time limit": (dict(give_up_after=60.0, max_attempts=100), 12),
            "attempt limit": (dict(give_up_after=1000.0, max_attempts=3), 3),
        }
        for name, (kwargs, sends) in cases.items():
            with self.subTest(name):
                tracker, actions = self.drive(
                    [(True, False)] * (sends + 2) + [(False, False)], **kwargs)
                self.assertEqual(actions, [rise.ACTION_SEND] * sends
                                 + [rise.ACTION_GIVE_UP, None, None])
                self.assertEqual(tracker.status, rise.STOP_FAILED)

    def test_reset_ends_retries(self):
        # E.g. the kettle is lifted while stops are still being retried.
        tracker, _ = self.drive([(True, False)] * 2)
        tracker.reset()
        self.assertIsNone(tracker.status)
        self.assertIsNone(tracker.poll(20.0, True, False))



class FakeKettle:
    """Heats at `rate` °C/s after a 20 s lag; obeys the Nth stop."""

    def __init__(self, rate, obey_stop=1, unreachable_after_stop=0):
        self.clock = 0.0
        self.mode = "S_Heat"
        self.rate = rate
        self.obey_stop = obey_stop
        self.unreachable_polls = 0
        self.unreachable_after_stop = unreachable_after_stop
        self.stops = 0

    def get_state(self):
        if self.unreachable_polls:
            self.unreachable_polls -= 1
            raise TimeoutError("kettle not answering")
        temp = 20.0 + max(0.0, self.clock - 20.0) * self.rate
        if self.mode == "S_Heat" and temp >= 95.0:
            self.mode = "S_Hold"
        return types.SimpleNamespace(mode=self.mode, current_temp_c=temp)

    def stop(self):
        self.stops += 1
        self.unreachable_polls = self.unreachable_after_stop
        if self.stops >= self.obey_stop:
            self.mode = "S_Off"

    def watch(self, **kwargs):
        def sleep(seconds):
            self.clock += seconds
        return rise.watch_heat_cycle(self.get_state, self.stop, sleep=sleep,
                                     clock=lambda: self.clock, **kwargs)


class WatchHeatCycleTest(unittest.TestCase):

    def test_normal_boil_is_left_alone(self):
        kettle = FakeKettle(rate=0.5)
        result = kettle.watch()
        self.assertEqual(result.outcome, rise.OUTCOME_DONE)
        self.assertEqual(result.state.mode, "S_Hold")
        self.assertEqual(kettle.stops, 0)

    def test_rapid_rise_stops_the_kettle(self):
        for obey_stop in (1, 3):
            with self.subTest(obey_stop=obey_stop):
                kettle = FakeKettle(rate=5.0, obey_stop=obey_stop,
                                    unreachable_after_stop=2)
                result = kettle.watch()
                self.assertEqual(result.outcome, rise.OUTCOME_STOPPED)
                self.assertEqual(kettle.stops, obey_stop)
                self.assertEqual(result.stop_attempts, obey_stop)
                self.assertAlmostEqual(result.triggered_rate, 5.0)

    def test_gives_up_when_kettle_ignores_stops(self):
        kettle = FakeKettle(rate=5.0, obey_stop=99)
        result = kettle.watch()
        self.assertEqual(result.outcome, rise.OUTCOME_STOP_FAILED)
        self.assertEqual(kettle.stops, rise.DEFAULT_STOP_MAX_ATTEMPTS)

    def test_kettle_that_never_heats(self):
        kettle = FakeKettle(rate=0.5)
        kettle.mode = "S_Off"
        result = kettle.watch(start_timeout=30.0)
        self.assertEqual(result.outcome, rise.OUTCOME_NOT_STARTED)
        self.assertGreaterEqual(kettle.clock, 30.0)

    def test_kettle_that_stays_unreachable_raises(self):
        kettle = FakeKettle(rate=0.5)
        kettle.unreachable_polls = rise.MAX_CONSECUTIVE_POLL_FAILURES
        with self.assertRaises(TimeoutError):
            kettle.watch()


if __name__ == "__main__":
    unittest.main()
