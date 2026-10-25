"""Track whether the kettle is on its base.

The kettle reports `tempr=nan` while it's off the base, so every poll says
whether it's docked. Lifted turns on at the first undocked reading and off
after REDOCK_POLLS docked readings in a row, so one flapping reading while
the kettle is being set down doesn't toggle it.
"""
from __future__ import annotations

from typing import Any, Optional

REDOCK_POLLS = 2

LIFTED = "lifted"
SET_DOWN = "set_down"


class DockTracker:
    """Turn per-poll docked readings into a debounced Lifted state."""

    def __init__(self, redock_polls: int = REDOCK_POLLS):
        self.redock_polls = redock_polls
        self.lifted = False
        self.last_lifted: Any = None
        self.last_set_down: Any = None
        self._docked_polls = 0
        self._first_docked_at: Any = None

    def update(self, now: Any, docked: bool) -> Optional[str]:
        """Record a poll. Returns LIFTED or SET_DOWN when Lifted changes."""
        if not docked:
            self._docked_polls = 0
            if self.lifted:
                return None
            self.lifted = True
            self.last_lifted = now
            return LIFTED
        if not self.lifted:
            return None
        if self._docked_polls == 0:
            self._first_docked_at = now
        self._docked_polls += 1
        if self._docked_polls < self.redock_polls:
            return None
        self.lifted = False
        # When it was put down, not when the debounce finished.
        self.last_set_down = self._first_docked_at
        return SET_DOWN
