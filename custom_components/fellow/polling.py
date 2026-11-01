"""How often the coordinator polls the kettle.

No Home Assistant imports, so the tests can load it directly.
"""
from __future__ import annotations

from datetime import timedelta


def poll_interval(*, busy: bool, failures: int, max_failures: int,
                  active: timedelta, idle: timedelta) -> timedelta:
    """Pick the interval until the next poll.

    `busy` is heating, holding or stopping after a rapid rise: rapid-rise
    detection and the stop retries need `active` polls then. A failed poll
    (`failures` > 0) is also followed up at `active`, until there have been
    more than `max_failures` in a row and the kettle is treated as offline.
    """
    if failures:
        return active if failures <= max_failures else idle
    return active if busy else idle
