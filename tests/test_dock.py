"""Tests for Lifted detection. Loads dock.py by path, like test_rise.py."""
import importlib.util
import pathlib
import unittest

_DOCK_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "custom_components" / "fellow" / "dock.py"
)
_spec = importlib.util.spec_from_file_location("fellow_dock", _DOCK_PATH)
dock = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dock)


def polls(start, docked_by_time, end, step=5):
    """5 s polls from `start` to `end`; docked unless the time is listed."""
    return [(t, docked_by_time.get(t, True)) for t in range(start, end + 1, step)]


def replay(tracker, samples):
    return [(t, change) for t, docked in samples
            if (change := tracker.update(t, docked))]


class DockTrackerTest(unittest.TestCase):

    def test_real_lifts_clear_soon_after_set_down(self):
        # Seconds after 20:33:18, from Home Assistant's history of a Stagg
        # EKG Pro: lifted at 20:33:33 and set down at 20:33:48, then lifted
        # at 20:44:17 and set down at 20:44:22 (that poll was 4 s late).
        off_base = {15: False, 20: False, 25: False, 659: False}
        samples = polls(0, off_base, 650) + polls(659, off_base, 700)
        tracker = dock.DockTracker()
        self.assertEqual(replay(tracker, samples), [
            (15, dock.LIFTED), (35, dock.SET_DOWN),
            (659, dock.LIFTED), (669, dock.SET_DOWN),
        ])
        # The set-down time is the first docked reading, not the debounce.
        self.assertEqual(tracker.last_set_down, 664)
        self.assertEqual(tracker.last_lifted, 659)
        self.assertFalse(tracker.lifted)

    def test_one_flapping_reading_does_not_clear_lifted(self):
        tracker = dock.DockTracker()
        changes = replay(tracker, [(0, True), (5, False), (10, True),
                                   (15, False), (20, True), (25, True)])
        self.assertEqual(changes, [(5, dock.LIFTED), (25, dock.SET_DOWN)])
        self.assertEqual(tracker.last_set_down, 20)

    def test_starting_off_the_base(self):
        tracker = dock.DockTracker()
        self.assertEqual(tracker.update(0, False), dock.LIFTED)
        self.assertTrue(tracker.lifted)


if __name__ == "__main__":
    unittest.main()
