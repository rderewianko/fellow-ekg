"""Tests for Heat Up Target / Hold Target and the hold countdown.

targets.py imports rise.py relatively, so both are loaded into a stand-in
package rather than importing `fellow` (whose __init__ needs homeassistant).
"""
import importlib.util
import pathlib
import sys
import types
import unittest
from datetime import datetime, timedelta

_DIR = pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "fellow"
_pkg = types.ModuleType("fellow_targets_pkg")
_pkg.__path__ = [str(_DIR)]
sys.modules[_pkg.__name__] = _pkg
for _name in ("rise", "targets"):
    _spec = importlib.util.spec_from_file_location(
        f"{_pkg.__name__}.{_name}", _DIR / f"{_name}.py")
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = _mod
    _spec.loader.exec_module(_mod)
targets = sys.modules[f"{_pkg.__name__}.targets"]


T0 = datetime(2026, 10, 25, 8, 0, 0)


def run(manager, polls, start=T0, step=5):
    """Feed (mode, kettle_target) polls every `step` s, writing what's asked."""
    writes = []
    kettle = None
    for i, (mode, kettle_target) in enumerate(polls):
        kettle = kettle if kettle_target is None else kettle_target
        target = manager.poll(mode, kettle, start + timedelta(seconds=i * step))
        if target is not None:
            writes.append((mode, target))
            manager.written(target)
            kettle = target
    return writes


class TargetManagerTest(unittest.TestCase):

    def test_hold_lower_then_restore_when_hold_runs_out(self):
        m = targets.TargetManager(heat_target=100.0, hold_target=85.0, hold_delay=0)
        writes = run(m, [("S_Off", 100.0), ("S_Heat", None), ("S_Hold", None),
                         ("S_Hold", None), ("S_HeatOff", None), ("S_Off", None)])
        self.assertEqual(writes, [("S_Hold", 85.0), ("S_HeatOff", 100.0)])
        self.assertFalse(m.applied)

    def test_pour_mid_hold_keeps_hold_target(self):
        # Seen on the kettle: lifted mid-hold reports S_Standby, set down it
        # reheats (S_Heat) and holds again.
        m = targets.TargetManager(heat_target=100.0, hold_target=85.0, hold_delay=0)
        writes = run(m, [("S_Heat", 100.0), ("S_Hold", None), ("S_Standby", None),
                         ("S_Heat", None), ("S_Hold", None), ("S_Hold+menu", None)])
        self.assertEqual(writes, [("S_Hold", 85.0)])
        self.assertTrue(m.applied)

    def test_turning_off_mid_hold_restores(self):
        m = targets.TargetManager(heat_target=100.0, hold_target=85.0, hold_delay=0)
        writes = run(m, [("S_Heat", 100.0), ("S_Hold", None), ("S_Off", None)])
        self.assertEqual(writes, [("S_Hold", 85.0), ("S_Off", 100.0)])

    def test_hold_target_at_or_above_heat_target_changes_nothing(self):
        for hold in (100.0, 100.2, 105.0):
            with self.subTest(hold=hold):
                m = targets.TargetManager(heat_target=100.0, hold_target=hold, hold_delay=0)
                self.assertEqual(run(m, [("S_Heat", 100.0), ("S_Hold", None),
                                         ("S_HeatOff", None)]), [])

    def test_dial_changes_follow_outside_a_lowered_hold(self):
        m = targets.TargetManager(heat_target=100.0, hold_target=85.0, hold_delay=0)
        run(m, [("S_Off", 100.0), ("S_Heat+tset", 93.0), ("S_Heat", 93.0)])
        self.assertEqual(m.heat_target, 93.0)
        # ...but not during one, where the kettle's target is the hold target.
        run(m, [("S_Hold", None), ("S_Hold", 85.0)])
        self.assertEqual(m.heat_target, 93.0)

    def test_first_poll_takes_the_kettles_target(self):
        m = targets.TargetManager()
        run(m, [("S_Off", 100.0)])
        self.assertEqual((m.heat_target, m.hold_target), (100.0, 100.0))
        self.assertTrue(m.changed)

    def test_restart_mid_hold_keeps_heat_target(self):
        m = targets.TargetManager(heat_target=100.0, hold_target=85.0, hold_delay=0)
        run(m, [("S_Heat", 100.0), ("S_Hold", None)])
        restored = targets.TargetManager.from_dict(m.as_dict())
        # The kettle reads 85 now; that must not become the heat-up target.
        writes = run(restored, [("S_Hold", 85.0), ("S_HeatOff", None)])
        self.assertEqual(writes, [("S_HeatOff", 100.0)])
        self.assertEqual(restored.heat_target, 100.0)

    def test_changing_targets(self):
        m = targets.TargetManager(heat_target=100.0, hold_target=100.0, hold_delay=0)
        self.assertEqual(m.set_heat_target(95.0, holding=False), 95.0)  # now
        m.written(95.0)
        # Not lowered yet: setting a lower hold target waits for the next poll.
        self.assertIsNone(m.set_hold_target(80.0, holding=True))
        self.assertEqual(run(m, [("S_Hold", 95.0)]), [("S_Hold", 80.0)])
        self.assertEqual(m.set_heat_target(98.0, holding=True), None)   # later
        self.assertEqual(m.set_hold_target(75.0, holding=True), 75.0)
        m.written(75.0)
        self.assertEqual(m.before_boil(), 98.0)
        self.assertEqual(m.set_hold_target(99.0, holding=True), 98.0)  # not lower
        m.written(98.0)
        self.assertFalse(m.applied)
        self.assertEqual(m.set_hold_target(20.0, holding=False), None)
        self.assertEqual(m.hold_target, targets.MIN_TARGET_C)

    def test_changing_heat_target_mid_hold_waits_for_the_hold_to_end(self):
        # Holding at the heat-up target (no lower Hold Target): raising the
        # heat-up target must not reheat the water now.
        m = targets.TargetManager(heat_target=80.5, hold_target=80.5)
        run(m, [("S_Heat", 80.5), ("S_Hold", None)])
        self.assertIsNone(m.set_heat_target(100.0, holding=True))
        writes = run(m, [("S_Hold", 80.5), ("S_Hold+menu", 80.5), ("S_HeatOff", None)])
        self.assertEqual(writes, [("S_HeatOff", 100.0)])
        self.assertEqual(m.heat_target, 100.0)

    def test_hold_delay_leaves_time_to_pour(self):
        m = targets.TargetManager(heat_target=100.0, hold_target=85.0)  # 2 min
        self.assertEqual(m.hold_delay, targets.DEFAULT_HOLD_DELAY_MIN)
        # Boil reaches 100 at poll 2 (10 s); a pour at about 1 min (lifted,
        # set down, reheat, hold again) doesn't restart the delay.
        polls = ([("S_Heat", 100.0)] * 2 + [("S_Hold", None)] * 10
                 + [("S_Standby", None), ("S_Heat", None)]
                 + [("S_Hold", None)] * 20)
        writes = run(m, polls)
        self.assertEqual(writes, [("S_Hold", 85.0)])
        # Dropped on the first poll at least 2 minutes after the boil.
        dropped_at = [i for i, _ in enumerate(polls) if i * 5 >= 10 + 120][0]
        m2 = targets.TargetManager(heat_target=100.0, hold_target=85.0)
        before = run(m2, polls[:dropped_at])
        self.assertEqual(before, [])
        self.assertEqual(m2.drops_at(), T0 + timedelta(seconds=10 + 120))

    def test_hold_delay_resets_when_the_hold_ends(self):
        m = targets.TargetManager(heat_target=100.0, hold_target=85.0, hold_delay=1)
        run(m, [("S_Heat", 100.0), ("S_Hold", None), ("S_Off", None)])
        self.assertIsNone(m.drops_at())
        # A new boil gets the full delay again.
        writes = run(m, [("S_Heat", None)] + [("S_Hold", None)] * 13,
                     start=T0 + timedelta(minutes=10))
        self.assertEqual(writes, [("S_Hold", 85.0)])

    def test_zero_delay_drops_at_once_and_delay_is_saved(self):
        m = targets.TargetManager(heat_target=100.0, hold_target=85.0)
        m.set_hold_delay(0)
        self.assertEqual(run(m, [("S_Heat", 100.0), ("S_Hold", None)]), [("S_Hold", 85.0)])
        self.assertEqual(targets.TargetManager.from_dict(m.as_dict()).hold_delay, 0)
        m.set_hold_delay(500)
        self.assertEqual(m.hold_delay, targets.MAX_HOLD_DELAY_MIN)


class CoolingLabelTest(unittest.TestCase):

    def test_labels(self):
        label = targets.cooling_label
        # Seen on the kettle: target lowered to 80.6 mid-boil at 84 C.
        self.assertEqual(label("S_Heat", 84.0, 80.6), targets.COOLING_TO_TARGET)
        self.assertEqual(label("S_Heat+tset", 84.0, 80.6), targets.COOLING_TO_TARGET)
        # Lowered Hold Target while the water cools to it.
        self.assertEqual(label("S_Hold", 99.0, 85.0), targets.COOLING_TO_HOLD_TARGET)
        self.assertEqual(label("S_Hold+menu", 99.0, 85.0), targets.COOLING_TO_HOLD_TARGET)
        # Normal holding wobble (84.2-85.7 C at 85) and heating below target.
        self.assertIsNone(label("S_Hold", 85.7, 85.0))
        self.assertIsNone(label("S_Heat", 60.0, 100.0))
        # Off, or no reading.
        self.assertIsNone(label("S_Off", 90.0, 80.0))
        self.assertIsNone(label("S_Heat", None, 80.0))


class HoldTimerTest(unittest.TestCase):

    def test_matches_the_measured_hold(self):
        # 2026-10-24 on a Stagg EKG Pro: menu use mid-hold restarted the
        # 15-minute hold when the menu closed (S_Hold+menu -> S_Hold at
        # 22:04:23); the hold ended at 22:19:24.
        t = lambda hms: datetime(2026, 10, 24, *map(int, hms.split(":")))
        timer = targets.HoldTimer()
        for hms, mode in (("22:02:40", "S_Heat+tset"), ("22:03:00", "S_Hold+menu"),
                          ("22:03:21", "S_Heat"), ("22:03:52", "S_Hold"),
                          ("22:04:13", "S_Hold+menu"), ("22:04:23", "S_Hold")):
            timer.update(t(hms), mode)
        self.assertEqual(timer.ends_at(15), t("22:19:23"))

    def test_empty_when_not_holding_or_no_duration(self):
        timer = targets.HoldTimer()
        now = datetime(2026, 1, 1)
        timer.update(now, "S_Hold")
        self.assertIsNone(timer.ends_at(None))
        self.assertEqual(timer.ends_at(30), now + timedelta(minutes=30))
        timer.update(now, "S_HeatOff")
        self.assertIsNone(timer.ends_at(30))


if __name__ == "__main__":
    unittest.main()
