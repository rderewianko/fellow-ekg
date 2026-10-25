"""Switch platform for Stagg EKG integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import StaggEKGDataUpdateCoordinator
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Stagg EKG switches."""
    coordinator: StaggEKGDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        StaggEKGHeatingSwitch(coordinator, entry),
        StaggEKGWarmingSwitch(coordinator, entry),
    ]

    async_add_entities(entities)


class StaggEKGSwitchBase(CoordinatorEntity, SwitchEntity):
    """Base class for Stagg EKG switches."""

    def __init__(
        self, coordinator: StaggEKGDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the switch."""
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


class StaggEKGHeatingSwitch(StaggEKGSwitchBase):
    """Switch to control heating."""

    def __init__(
        self, coordinator: StaggEKGDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_heating"
        self._attr_name = "Heating"
        self._attr_icon = "mdi:fire"

    @property
    def is_on(self) -> bool:
        """Return true if heating is on."""
        if self.coordinator.data and "state" in self.coordinator.data:
            return self.coordinator.data["state"].is_heating
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn heating on."""
        # A lowered hold leaves the kettle at the Hold Target; boil to the
        # Heat Up Target instead.
        await self.coordinator.async_before_boil()
        # Use start_heating to properly wake screen and start heating
        await self.hass.async_add_executor_job(self.coordinator.client.start_heating)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn heating off."""
        # Use stop_heating to properly stop and return to standby
        await self.hass.async_add_executor_job(self.coordinator.client.stop_heating)
        await self.coordinator.async_request_refresh()


KEEP_WARM_HINT = "To keep water warm, start a new boil with Heating."


class StaggEKGWarmingSwitch(StaggEKGSwitchBase):
    """On while the kettle holds the water at temperature after a boil.

    The kettle has no separate warming mode: it holds for the Hold Duration
    once a boil reaches its target. So this only reports the hold and lets
    you end it. Turning it on is refused, because a hold should only come
    from a boil and never run longer than configured. It doesn't drive the
    warming element directly.
    """

    def __init__(
        self, coordinator: StaggEKGDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_warming"
        self._attr_name = "Warming / Holding"
        self._attr_icon = "mdi:fire-circle"

    @property
    def is_on(self) -> bool:
        """Return true if warming is on."""
        if self.coordinator.data and "state" in self.coordinator.data:
            state = self.coordinator.data["state"]
            return state.warming or state.is_holding
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Refuse: holds only come from a boil."""
        if self.is_on:
            return
        raise HomeAssistantError(KEEP_WARM_HINT)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """End the hold; the kettle turns off."""
        await self.hass.async_add_executor_job(self.coordinator.client.end_hold)
        await self.coordinator.async_request_refresh()
