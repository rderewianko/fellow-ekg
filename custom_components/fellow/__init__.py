"""The Fellow Stagg EKG+ integration."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from functools import partial

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_RAPID_RISE_AUTO_STOP,
    DEFAULT_RAPID_RISE_THRESHOLD,
    DOMAIN,
    EVENT_RAPID_RISE,
    EVENT_RAPID_RISE_STOP_FAILED,
)
from .dock import LIFTED, DockTracker
from .kettle import KettleTransientError, StaggEKGClient
from .targets import HoldTimer, TargetManager
from .rise import (
    ACTION_GIVE_UP,
    ACTION_SEND,
    STOP_STOPPED,
    AutoStopTracker,
    RapidRiseDetector,
)

# After this many consecutive transient failures, give up holding the
# last known state and let HA mark the device unavailable. At a 5s poll
# interval that's roughly half a minute of staleness — long enough to
# absorb the "kettle just turned off" window, short enough that a truly
# offline kettle doesn't show stale data forever.
MAX_CONSECUTIVE_TRANSIENT_FAILURES = 6

# The Power sensor goes off after this many failed polls in a row, well
# before the rest of the device goes unavailable. The kettle's usual "not
# answering while it turns off" blip is a single failed poll.
POWER_OFF_AFTER_FAILURES = 2

# The hold duration is a setting, not live state, so it's re-read about once
# a minute rather than every poll; that still picks up a change made from
# the kettle's own menu.
HOLD_REFRESH_POLLS = 12

# A failed Hold Target / Heat Up Target write is retried at most this often.
TARGET_RETRY_SECONDS = 60

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.WATER_HEATER,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.NUMBER,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Stagg EKG from a config entry."""
    from .const import (
        CONF_RAPID_RISE_AUTO_STOP,
        CONF_RAPID_RISE_THRESHOLD,
        CONF_TEMP_SET_METHOD,
        CONF_TEMPERATURE_UNIT,
        TEMP_METHOD_DIRECT,
        UNIT_CELSIUS,
    )

    host = entry.data["host"]
    # Options take precedence over the original entry data so changes from
    # the options flow apply without re-adding the integration.
    temp_method = entry.options.get(
        CONF_TEMP_SET_METHOD,
        entry.data.get(CONF_TEMP_SET_METHOD, TEMP_METHOD_DIRECT),
    )

    # Create API client
    client = StaggEKGClient(host=host, temp_method=temp_method)

    # Sync kettle units with configured preference
    configured_unit = entry.data.get(CONF_TEMPERATURE_UNIT, UNIT_CELSIUS)
    try:
        if configured_unit == UNIT_CELSIUS:
            await hass.async_add_executor_job(client.set_units_celsius)
        else:
            await hass.async_add_executor_job(client.set_units_fahrenheit)
    except Exception as err:
        _LOGGER.warning("Failed to sync kettle temperature units: %s", err)

    rise_threshold = entry.options.get(
        CONF_RAPID_RISE_THRESHOLD,
        entry.data.get(CONF_RAPID_RISE_THRESHOLD, DEFAULT_RAPID_RISE_THRESHOLD),
    )
    rise_auto_stop = entry.options.get(
        CONF_RAPID_RISE_AUTO_STOP,
        entry.data.get(CONF_RAPID_RISE_AUTO_STOP, DEFAULT_RAPID_RISE_AUTO_STOP),
    )

    # Heat Up Target / Hold Target live in Home Assistant, since the kettle
    # has only one target; saved so a restart mid-hold doesn't lose them.
    store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.targets")

    # Create update coordinator
    coordinator = StaggEKGDataUpdateCoordinator(
        hass,
        client,
        rise_threshold=rise_threshold,
        rise_auto_stop=rise_auto_stop,
        targets=TargetManager.from_dict(await store.async_load()),
        targets_store=store,
    )

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload when options change so settings like temp_set_method take
    # effect without an HA restart.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when the user changes options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class StaggEKGDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Stagg EKG data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: StaggEKGClient,
        rise_threshold: float = DEFAULT_RAPID_RISE_THRESHOLD,
        rise_auto_stop: bool = DEFAULT_RAPID_RISE_AUTO_STOP,
        targets: TargetManager | None = None,
        targets_store: Store | None = None,
    ) -> None:
        """Initialize."""
        self.client = client
        self._consecutive_transient_failures = 0
        self.dock = DockTracker()
        self.targets = targets or TargetManager()
        self._targets_store = targets_store
        self.hold_timer = HoldTimer()
        self._next_target_retry = 0.0
        self.hold_minutes: int | None = None
        self._polls_since_hold_read = HOLD_REFRESH_POLLS
        self.last_poll = None
        self.rise_detector = RapidRiseDetector(threshold=rise_threshold)
        self.rise_auto_stop = rise_auto_stop
        self.auto_stop = AutoStopTracker()
        self._stop_task: asyncio.Task | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=5),
        )

    @property
    def reachable(self) -> bool:
        """Whether the kettle is answering polls (what Power shows)."""
        return (
            self.last_update_success
            and self._consecutive_transient_failures < POWER_OFF_AFTER_FAILURES
        )

    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            state = await self.hass.async_add_executor_job(self.client.get_state)
        except KettleTransientError as err:
            # The kettle stops answering HTTP (or returns truncated data)
            # for a few seconds when it transitions to Off. Hold the last
            # known state for a while instead of surfacing an error every
            # time that happens — but give up after enough consecutive
            # failures so HA can mark the device unavailable if it really
            # is offline.
            self._consecutive_transient_failures += 1
            if (
                self.data is not None
                and self._consecutive_transient_failures
                <= MAX_CONSECUTIVE_TRANSIENT_FAILURES
            ):
                _LOGGER.debug(
                    "Kettle transient failure %d/%d, keeping last state: %s",
                    self._consecutive_transient_failures,
                    MAX_CONSECUTIVE_TRANSIENT_FAILURES,
                    err,
                )
                return self.data
            raise UpdateFailed(f"Kettle unresponsive: {err}")
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

        self._consecutive_transient_failures = 0
        self.last_poll = dt_util.utcnow()

        self._polls_since_hold_read += 1
        if self._polls_since_hold_read >= HOLD_REFRESH_POLLS:
            self._polls_since_hold_read = 0
            try:
                self.hold_minutes = await self.hass.async_add_executor_job(
                    self.client.get_hold_minutes
                )
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.debug("Couldn't read the hold setting: %s", err)
                self._polls_since_hold_read = HOLD_REFRESH_POLLS  # next poll

        if self.dock.update(self.last_poll, state.is_docked) == LIFTED:
            # Lifting usually means a refill, so clear any rapid-rise alert.
            self.rise_detector.reset()

        now = time.monotonic()
        if self.rise_detector.update(now, state.current_temp_c, state.is_heating):
            self._handle_rapid_rise(now)
        if not self.rise_detector.triggered:
            # New heat cycle or a lift: any auto-stop in progress is over.
            self.auto_stop.reset()
        self._drive_auto_stop(now, state.is_heating or state.is_holding)

        self.hold_timer.update(self.last_poll, state.mode)
        target = self.targets.poll(state.mode, state.set_temp_c, self.last_poll)
        if target is not None and now >= self._next_target_retry:
            if not await self.async_write_target(target):
                self._next_target_retry = now + TARGET_RETRY_SECONDS
        self._save_targets()

        return {"state": state}

    async def async_write_target(self, target: float, *, dial_ok: bool = False) -> bool:
        """Write a target the TargetManager asked for; True if it took.

        Mid-hold writes must use the direct command (write_target). With
        dial_ok, the configured method (set_temperature) is used instead, for
        a heat-up target set while no lowered hold is in place.
        """
        write = self.client.set_temperature if dial_ok else self.client.write_target
        try:
            await self.hass.async_add_executor_job(write, target)
        except Exception as err:  # pylint: disable=broad-except
            # Asked again on the next poll if it's still needed.
            _LOGGER.warning("Couldn't set the kettle target to %.1f C: %s", target, err)
            return False
        self.targets.written(target)
        self._save_targets()
        return True

    def _save_targets(self) -> None:
        if self.targets.changed and self._targets_store is not None:
            self.targets.changed = False
            self._targets_store.async_delay_save(self.targets.as_dict, 1)

    async def async_set_heat_target(self, celsius: float) -> None:
        state = (self.data or {}).get("state")
        target = self.targets.set_heat_target(celsius, bool(state and state.is_holding))
        if target is not None:
            await self.async_write_target(target, dial_ok=True)
        self._save_targets()

    async def async_set_hold_target(self, celsius: float) -> None:
        state = (self.data or {}).get("state")
        target = self.targets.set_hold_target(celsius, bool(state and state.is_holding))
        if target is not None:
            await self.async_write_target(target)
        self._save_targets()

    def set_hold_delay(self, minutes: float) -> None:
        self.targets.set_hold_delay(minutes)
        self._save_targets()

    async def async_before_boil(self) -> None:
        """Put the heat-up target back if a lowered hold is in place."""
        target = self.targets.before_boil()
        if target is not None:
            await self.async_write_target(target)

    def _handle_rapid_rise(self, now: float) -> None:
        """React to the first poll of a heat cycle that shows a rapid rise."""
        rate = self.rise_detector.triggered_rate
        threshold = self.rise_detector.threshold
        _LOGGER.warning(
            "Kettle temperature rising at %.2f °C/s (threshold %.2f °C/s); "
            "the kettle may be empty or very low on water%s",
            rate,
            threshold,
            ", stopping heat" if self.rise_auto_stop else "",
        )
        self.hass.bus.async_fire(
            EVENT_RAPID_RISE,
            {
                "rate": round(rate, 2),
                "threshold": threshold,
                "auto_stop": self.rise_auto_stop,
            },
        )
        if self.rise_auto_stop:
            self.auto_stop.start(now)

    def _drive_auto_stop(self, now: float, running: bool) -> None:
        """Send another stop, or give up, based on what this poll saw.

        Each attempt runs as a background task so a slow or unresponsive
        kettle doesn't hold up polling; the next poll checks whether it
        worked.
        """
        in_flight = self._stop_task is not None and not self._stop_task.done()
        was_stopped = self.auto_stop.status == STOP_STOPPED
        action = self.auto_stop.poll(now, running, in_flight)
        if not was_stopped and self.auto_stop.status == STOP_STOPPED:
            _LOGGER.info(
                "Kettle stopped after rapid rise (%d attempt(s))",
                self.auto_stop.attempts,
            )
        if action == ACTION_SEND:
            self._stop_task = self.hass.async_create_background_task(
                self._async_stop_attempt(self.auto_stop.attempts),
                name=f"{DOMAIN} rapid-rise stop",
            )
        elif action == ACTION_GIVE_UP:
            self._give_up_auto_stop()

    async def _async_stop_attempt(self, attempt: int) -> None:
        """Send one stop. Retries come from later polls, not from here."""
        try:
            await self.hass.async_add_executor_job(
                partial(self.client.stop_heating, max_attempts=1)
            )
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning(
                "Rapid-rise stop attempt %d failed: %s", attempt, err
            )

    def _give_up_auto_stop(self) -> None:
        """Tell the user the kettle didn't turn off after a rapid rise."""
        attempts = self.auto_stop.attempts
        _LOGGER.error(
            "Kettle still on after %d stop attempt(s) following a rapid "
            "temperature rise; giving up",
            attempts,
        )
        self.hass.bus.async_fire(
            EVENT_RAPID_RISE_STOP_FAILED,
            {
                "rate": round(self.rise_detector.triggered_rate, 2),
                "attempts": attempts,
            },
        )
        persistent_notification.async_create(
            self.hass,
            "The kettle's temperature rose fast enough to suggest it is empty "
            f"or very low on water, and it did not turn off after {attempts} "
            "stop attempt(s). Check it now.",
            title="Fellow kettle did not turn off",
            notification_id=f"{DOMAIN}_rapid_rise_stop_failed",
        )
