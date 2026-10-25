"""Binary sensor platform for Stagg EKG integration."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import StaggEKGDataUpdateCoordinator
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Stagg EKG binary sensors."""
    coordinator: StaggEKGDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        StaggEKGPowerBinarySensor(coordinator, entry),
        StaggEKGOnBaseBinarySensor(coordinator, entry),
        StaggEKGRapidRiseBinarySensor(coordinator, entry),
    ]

    async_add_entities(entities)


class StaggEKGBinarySensorBase(CoordinatorEntity, BinarySensorEntity):
    """Base class for Stagg EKG binary sensors."""

    def __init__(
        self, coordinator: StaggEKGDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the binary sensor."""
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


class StaggEKGPowerBinarySensor(StaggEKGBinarySensorBase):
    """On while the kettle answers Home Assistant, off once it stops.

    It goes off after two failed polls in a row (about 15-30 s), while the
    other entities keep the last known state for longer. Whether the kettle
    is awake or heating is what the Mode sensor is for.
    """

    _attr_device_class = BinarySensorDeviceClass.POWER

    def __init__(
        self, coordinator: StaggEKGDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_power"
        self._attr_name = "Power"

    @property
    def available(self) -> bool:
        """Always available, so an unreachable kettle shows Off."""
        return True

    @property
    def is_on(self) -> bool:
        """Return true while the kettle is answering polls."""
        return self.coordinator.reachable

    @property
    def extra_state_attributes(self):
        """Return additional state attributes."""
        if self.coordinator.data and "state" in self.coordinator.data:
            state = self.coordinator.data["state"]
            return {
                "mode": state.mode,
                "screen": state.screen_name,
                "in_menu": state.is_in_menu,
                "last_poll": self.coordinator.last_poll,
            }
        return {}


class StaggEKGOnBaseBinarySensor(StaggEKGBinarySensorBase):
    """Whether the kettle is sitting on its base.

    On while docked, so dashboards show the active color for "on the base"
    and grey for "lifted". The states read "On base" / "Off base" (from
    strings.json) rather than a device class's generic wording.
    """

    _attr_translation_key = "on_base"

    def __init__(
        self, coordinator: StaggEKGDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_on_base"

    @property
    def is_on(self) -> bool:
        """Return true while the kettle is on the base."""
        return not self.coordinator.dock.lifted

    @property
    def icon(self) -> str:
        """A filled kettle on the base, an outline when lifted."""
        return "mdi:kettle" if self.is_on else "mdi:kettle-outline"

    @property
    def extra_state_attributes(self):
        """Return when the kettle was last lifted and set back down."""
        return {
            "last_lifted": self.coordinator.dock.last_lifted,
            "last_set_down": self.coordinator.dock.last_set_down,
        }


def _round_rate(rate: float | None) -> float | None:
    return round(rate, 2) if rate is not None else None


class StaggEKGRapidRiseBinarySensor(StaggEKGBinarySensorBase):
    """Binary sensor for an implausibly fast temperature rise while heating.

    A fast rise suggests an empty or nearly empty kettle. Stays on until the
    next heat cycle starts or the kettle is lifted off the base.
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self, coordinator: StaggEKGDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_rapid_rise"
        self._attr_name = "Rapid Temperature Rise"
        self._attr_icon = "mdi:kettle-alert"

    @property
    def is_on(self) -> bool:
        """Return true if a rapid rise was seen during this heat cycle."""
        return self.coordinator.rise_detector.triggered

    @property
    def extra_state_attributes(self):
        """Return additional state attributes."""
        detector = self.coordinator.rise_detector
        return {
            # Live 10 s average; None when not heating or no reading.
            "rise_rate": _round_rate(detector.rate),
            # Rate that tripped the alert; None until it triggers.
            "triggered_rate": _round_rate(detector.triggered_rate),
            "threshold": detector.threshold,
            "auto_stop": self.coordinator.rise_auto_stop,
            # None, "pending", "stopped" or "failed".
            "stop_status": self.coordinator.auto_stop.status,
        }
