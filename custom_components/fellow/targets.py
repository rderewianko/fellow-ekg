"""Heat Up Target, Hold Target and the hold countdown.

The kettle has a single target temperature (`settempr`): it heats to it, then
holds there for the Hold Duration. To hold lower than it boils, the
integration lowers the kettle's target when the hold starts and puts the
heat-up target back once the hold is over. The kettle reports S_HeatOff when
the hold runs out and S_Off when it's turned off. Lifting the kettle to pour
keeps the hold target: the kettle reports S_Standby while lifted, then
reheats and holds again when it's set down.

Outside a lowered hold the kettle's own target is the heat-up target, so a
change made with the dial is picked up.

Measured on a Stagg EKG Pro (firmware 1.1.75SSP): lowering the target to 85 C
during a hold took effect at once. The water cooled to 85 C and was held at
84.2-85.7 C, and the hold still ended 15 minutes after it started.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from .rise import HOLD_MODE, base_mode, is_heating_mode, is_holding_mode

MIN_TARGET_C = 40.0
MAX_TARGET_C = 100.0
# Minutes the water stays at the heat-up target after the boil, so there's
# time to pour, before the target drops to the Hold Target.
DEFAULT_HOLD_DELAY_MIN = 2.0
MAX_HOLD_DELAY_MIN = 60.0
HOLD_OVER_MODES = ("S_HeatOff", "S_Off")
# Below the kettle's 0.5 C step, two targets count as the same.
SAME_TARGET_C = 0.25
# Water this far above the target is cooling toward it, not being held at it.
# A hold measured at 85 C stayed within 84.2-85.7 C.
COOLING_MARGIN_C = 1.0

COOLING_TO_TARGET = "Cooling to target"
COOLING_TO_HOLD_TARGET = "Cooling to hold target"


def cooling_label(mode: Optional[str], temp_c: Optional[float],
                  target_c: Optional[float]) -> Optional[str]:
    """Say so when the water is above the target and cooling toward it.

    The kettle stays in its heating mode when the target is lowered below the
    water's temperature mid-boil, and in its hold mode while the water cools
    to a lowered Hold Target; it heats nothing until the water gets there.
    """
    if temp_c is None or target_c is None or temp_c <= target_c + COOLING_MARGIN_C:
        return None
    if is_holding_mode(mode):
        return COOLING_TO_HOLD_TARGET
    if is_heating_mode(mode):
        return COOLING_TO_TARGET
    return None


def clamp_target(celsius: float) -> float:
    return max(MIN_TARGET_C, min(MAX_TARGET_C, float(celsius)))


class TargetManager:
    """Decide when to switch the kettle's target between heat-up and hold.

    Methods that return a float are asking the caller to write that target to
    the kettle and then call written(); None means nothing to write.
    """

    def __init__(self, heat_target: Optional[float] = None,
                 hold_target: Optional[float] = None, applied: bool = False,
                 hold_delay: float = DEFAULT_HOLD_DELAY_MIN):
        self.heat_target = heat_target
        self.hold_target = hold_target
        # True while the kettle's target is the hold target (written by us).
        self.applied = applied
        self.hold_delay = hold_delay  # minutes
        self.changed = False  # something worth saving
        # When the boil first reached its target and the kettle started
        # holding. Pours (S_Standby, then a reheat) don't reset it; the hold
        # ending or the kettle turning off does.
        self._hold_reached_at: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "TargetManager":
        data = data or {}
        return cls(data.get("heat_target"), data.get("hold_target"),
                   bool(data.get("applied", False)),
                   data.get("hold_delay", DEFAULT_HOLD_DELAY_MIN))

    def as_dict(self) -> Dict[str, Any]:
        return {"heat_target": self.heat_target, "hold_target": self.hold_target,
                "applied": self.applied, "hold_delay": self.hold_delay}

    def _holds_lower(self) -> bool:
        return (self.heat_target is not None and self.hold_target is not None
                and self.hold_target <= self.heat_target - 2 * SAME_TARGET_C)

    def poll(self, mode: Optional[str], kettle_target: Optional[float],
             now: datetime) -> Optional[float]:
        """Record a poll; return a target to write, or None."""
        if base_mode(mode) in HOLD_OVER_MODES:
            self._hold_reached_at = None
        elif is_holding_mode(mode) and self._hold_reached_at is None:
            self._hold_reached_at = now
        if self.applied:
            if base_mode(mode) in HOLD_OVER_MODES:
                return self.heat_target
            return None  # still holding, or a pour/reheat in the middle of it
        if self.heat_target is None or (
                kettle_target is not None and kettle_target >= MIN_TARGET_C
                and abs(kettle_target - self.heat_target) >= SAME_TARGET_C):
            # Not in a lowered hold, so the kettle's target is the heat-up
            # target: follow it, including changes made with the dial.
            if kettle_target is not None and kettle_target >= MIN_TARGET_C:
                self.heat_target = kettle_target
                if self.hold_target is None:
                    self.hold_target = kettle_target
                self.changed = True
        if is_holding_mode(mode) and self._holds_lower() and self._delay_over(now):
            return self.hold_target
        return None

    def _delay_over(self, now: datetime) -> bool:
        return (self._hold_reached_at is not None
                and now - self._hold_reached_at >= timedelta(minutes=self.hold_delay))

    def drops_at(self) -> Optional[datetime]:
        """When the target will drop to the Hold Target, if that's pending."""
        if self.applied or self._hold_reached_at is None or not self._holds_lower():
            return None
        return self._hold_reached_at + timedelta(minutes=self.hold_delay)

    def set_hold_delay(self, minutes: float) -> None:
        self.hold_delay = max(0.0, min(MAX_HOLD_DELAY_MIN, float(minutes)))
        self.changed = True

    def written(self, target: float) -> None:
        """The kettle accepted `target`."""
        self.applied = (target == self.hold_target and self._holds_lower())
        self.changed = True

    def set_heat_target(self, celsius: float, holding: bool) -> Optional[float]:
        """Set what boils heat to.

        During a hold this only applies to future boils: the kettle holds at
        whatever its target is, so writing it now would reheat the water. It's
        written when the hold ends, the same way as after a lowered hold.
        During a boil it applies to that boil, like turning the dial.
        """
        self.heat_target = clamp_target(celsius)
        self.changed = True
        if self.applied:
            return None
        if holding:
            self.applied = True  # keep the current hold; restore when it ends
            return None
        return self.heat_target

    def set_hold_target(self, celsius: float, holding: bool) -> Optional[float]:
        self.hold_target = clamp_target(celsius)
        self.changed = True
        if self.applied:
            # Already holding lower: move to the new hold target, or back to
            # the heat-up target if the hold target is no longer lower.
            return self.hold_target if self._holds_lower() else self.heat_target
        # Otherwise the next poll lowers it, once the hold delay is over.
        return None

    def before_boil(self) -> Optional[float]:
        """A boil is about to start: make sure it heats to the heat-up target."""
        return self.heat_target if self.applied else None


class HoldTimer:
    """Estimate when the kettle's hold ends.

    The kettle restarts its Hold Duration every time its mode becomes plain
    S_Hold: when a boil or a reheat reaches the target, and when a menu opened
    during the hold is closed (S_Hold+menu -> S_Hold). Measured twice, the
    estimate matched the actual end to within a poll.
    """

    def __init__(self):
        self.started_at: Optional[datetime] = None
        self._last_mode: Optional[str] = None

    def update(self, now: datetime, mode: Optional[str]) -> None:
        if mode == HOLD_MODE and self._last_mode != HOLD_MODE:
            self.started_at = now
        elif not is_holding_mode(mode):
            self.started_at = None
        self._last_mode = mode

    def ends_at(self, hold_minutes: Optional[int]) -> Optional[datetime]:
        if self.started_at is None or not hold_minutes:
            return None
        return self.started_at + timedelta(minutes=hold_minutes)
