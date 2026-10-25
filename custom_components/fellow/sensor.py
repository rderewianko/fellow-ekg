"""Sensor platform for Stagg EKG integration."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import StaggEKGDataUpdateCoordinator
from .const import DOMAIN
from .targets import cooling_label


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Stagg EKG sensors."""
    coordinator: StaggEKGDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        StaggEKGCurrentTempSensor(coordinator, entry),
        StaggEKGTargetTempSensor(coordinator, entry),
        StaggEKGHoldEndsSensor(coordinator, entry),
        StaggEKGModeSensor(coordinator, entry),
        StaggEKGRawStatusSensor(coordinator, entry),
    ]

    async_add_entities(entities)


class StaggEKGSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for Stagg EKG sensors."""

    def __init__(
        self, coordinator: StaggEKGDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_has_entity_name = True

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Stagg EKG+",
            "manufacturer": "Fellow",
            "model": "Stagg EKG+",
            "sw_version": "1.1.76SSP",
        }


class StaggEKGCurrentTempSensor(StaggEKGSensorBase):
    """Current temperature sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(
        self, coordinator: StaggEKGDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_current_temp"
        self._attr_name = "Current Temperature"

    @property
    def native_value(self) -> float | None:
        """Return the current temperature."""
        if self.coordinator.data and "state" in self.coordinator.data:
            return self.coordinator.data["state"].current_temp_c
        return None


class StaggEKGTargetTempSensor(StaggEKGSensorBase):
    """The kettle's own target temperature, read-only.

    The kettle has a single target: it heats to it, then holds there. The
    integration sets it to the Heat Up Target for boils and lowers it to the
    Hold Target while holding, so the hold temperature can differ. Change
    those two instead; this shows which one the kettle is using.
    """

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _unrecorded_attributes = frozenset({"note"})

    def __init__(
        self, coordinator: StaggEKGDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_target_temp"
        # "Native" so a dashboard card shows this is the kettle's own setting,
        # not one of the two the integration manages.
        self._attr_name = "Native Target Temperature"

    @property
    def native_value(self) -> float | None:
        """Return the kettle's active target."""
        if self.coordinator.data and "state" in self.coordinator.data:
            return self.coordinator.data["state"].set_temp_c
        return None

    @property
    def extra_state_attributes(self):
        """Say which target is in use, and why there are two."""
        return {
            "role": "hold" if self.coordinator.targets.applied else "heat_up",
            "note": (
                "The kettle's own target: it heats to this, then holds there. "
                "The integration sets it to Heat Up Target for boils and lowers "
                "it to Hold Target during a hold, so the hold temperature can "
                "differ. Change Heat Up Target or Hold Target instead."
            ),
        }


class StaggEKGModeSensor(StaggEKGSensorBase):
    """Kettle mode sensor.

    Shows the kettle's mode, except while the water is above the target and
    cooling toward it, which the kettle reports as heating or holding.
    """

    def __init__(
        self, coordinator: StaggEKGDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_mode"
        self._attr_name = "Mode"

    @property
    def icon(self) -> str:
        """Steam the kettle icon while it's actively heating."""
        if self.coordinator.data and "state" in self.coordinator.data:
            if self._cooling():
                return "mdi:thermometer-chevron-down"
            if self.coordinator.data["state"].is_heating:
                return "mdi:kettle-steam"
        return "mdi:kettle"

    def _cooling(self) -> str | None:
        state = self.coordinator.data["state"]
        return cooling_label(state.mode, state.current_temp_c, state.set_temp_c)

    @property
    def native_value(self) -> str | None:
        """Return the kettle mode."""
        if self.coordinator.data and "state" in self.coordinator.data:
            cooling = self._cooling()
            if cooling:
                return cooling
            mode = self.coordinator.data["state"].mode
            # Clean up mode name
            if mode.startswith("S_"):
                mode = mode[2:]
            return mode
        return None


class StaggEKGRawStatusSensor(StaggEKGSensorBase):
    """What the kettle's `state` command returned on the latest poll.

    For debugging: the state is the mode and the unrounded temperature, and
    the full response is in the `raw` attribute (kept out of the recorder,
    since it changes every poll).
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _unrecorded_attributes = frozenset({"raw"})

    def __init__(
        self, coordinator: StaggEKGDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_raw_status"
        self._attr_name = "Raw Status"
        self._attr_icon = "mdi:console"

    @property
    def native_value(self) -> str | None:
        """Return the mode and temperature, e.g. "S_Heat 74.280831 C"."""
        if not (self.coordinator.data and "state" in self.coordinator.data):
            return None
        state = self.coordinator.data["state"]
        temp = "nan" if state.current_temp_c is None else repr(state.current_temp_c)
        return f"{state.mode} {temp} C"

    @property
    def extra_state_attributes(self):
        """Return the parsed fields and the raw response."""
        if not (self.coordinator.data and "state" in self.coordinator.data):
            return {}
        state = self.coordinator.data["state"]
        return {
            "mode": state.mode,
            "temperature": state.current_temp_c,
            "target_temperature": state.set_temp_c,
            "screen": state.screen_name,
            "clock": state.clock,
            "last_poll": self.coordinator.last_poll,
            "raw": state.raw,
        }


class StaggEKGHoldEndsSensor(StaggEKGSensorBase):
    """When the current hold ends; shown as a countdown.

    The kettle restarts its Hold Duration each time its mode becomes plain
    S_Hold (see targets.HoldTimer), so this is accurate to about one poll.
    Empty when the kettle isn't holding.
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self, coordinator: StaggEKGDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_hold_ends"
        self._attr_name = "Hold Ends"
        self._attr_icon = "mdi:timer-sand-complete"

    @property
    def native_value(self):
        """Return when the hold ends, or None if not holding."""
        return self.coordinator.hold_timer.ends_at(self.coordinator.hold_minutes)

    @property
    def extra_state_attributes(self):
        """The end as a local clock time, e.g. "23:06", next to the countdown."""
        ends = self.native_value
        return {"ends_at": dt_util.as_local(ends).strftime("%H:%M") if ends else None}
