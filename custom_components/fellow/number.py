"""Number platform for Stagg EKG integration."""
from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import StaggEKGDataUpdateCoordinator
from .const import DOMAIN
from .targets import MAX_HOLD_DELAY_MIN, MAX_TARGET_C, MIN_TARGET_C


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Stagg EKG numbers."""
    coordinator: StaggEKGDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([
        StaggEKGHeatUpTargetNumber(coordinator, entry),
        StaggEKGHoldTargetNumber(coordinator, entry),
        StaggEKGHoldDelayNumber(coordinator, entry),
    ])


class StaggEKGTargetNumberBase(CoordinatorEntity, NumberEntity):
    """A target temperature kept by the integration."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = MIN_TARGET_C
    _attr_native_max_value = MAX_TARGET_C
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX

    def __init__(
        self, coordinator: StaggEKGDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the number."""
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


class StaggEKGHeatUpTargetNumber(StaggEKGTargetNumberBase):
    """What a boil heats to. Follows the kettle's dial outside a lowered hold."""

    def __init__(
        self, coordinator: StaggEKGDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the number."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_heat_up_target"
        self._attr_name = "Heat Up Target"
        self._attr_icon = "mdi:thermometer-chevron-up"

    @property
    def native_value(self) -> float | None:
        """Return the heat-up target."""
        return self.coordinator.targets.heat_target

    async def async_set_native_value(self, value: float) -> None:
        """Set the heat-up target."""
        await self.coordinator.async_set_heat_target(value)
        self.async_write_ha_state()


class StaggEKGHoldTargetNumber(StaggEKGTargetNumberBase):
    """What the kettle holds at after a boil.

    At or above the heat-up target, the kettle holds at the heat-up target as
    usual. Lower, the integration lowers the kettle's target when the hold
    starts, so the water cools to this and is held there.
    """

    def __init__(
        self, coordinator: StaggEKGDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the number."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_hold_target"
        self._attr_name = "Hold Target"
        self._attr_icon = "mdi:thermometer-chevron-down"

    @property
    def native_value(self) -> float | None:
        """Return the hold target."""
        return self.coordinator.targets.hold_target

    @property
    def extra_state_attributes(self):
        """When the target drops to this, while that's still to come."""
        drops = self.coordinator.targets.drops_at()
        return {"drops_at": dt_util.as_local(drops).strftime("%H:%M") if drops else None}

    async def async_set_native_value(self, value: float) -> None:
        """Set the hold target; takes effect at once if already lowered."""
        await self.coordinator.async_set_hold_target(value)
        self.async_write_ha_state()


class StaggEKGHoldDelayNumber(StaggEKGTargetNumberBase):
    """Minutes at the heat-up target before dropping to the Hold Target.

    Time to pour after the boil. Counted from when the boil first reaches its
    target; lifting the kettle to pour doesn't restart it. 0 drops at once.
    """

    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = 0
    _attr_native_max_value = MAX_HOLD_DELAY_MIN
    _attr_native_step = 1

    def __init__(
        self, coordinator: StaggEKGDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the number."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_hold_delay"
        self._attr_name = "Hold Delay"
        self._attr_icon = "mdi:timer-pause-outline"

    @property
    def native_value(self) -> float | None:
        """Return the hold delay in minutes."""
        return self.coordinator.targets.hold_delay

    async def async_set_native_value(self, value: float) -> None:
        """Set the hold delay; applies to the hold in progress too."""
        self.coordinator.set_hold_delay(value)
        self.async_write_ha_state()
