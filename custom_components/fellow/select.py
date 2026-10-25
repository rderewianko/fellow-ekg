"""Select platform for Stagg EKG integration."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import StaggEKGDataUpdateCoordinator
from .const import DOMAIN
from .kettle import HOLD_MINUTES_OPTIONS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Stagg EKG selects."""
    coordinator: StaggEKGDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([StaggEKGHoldDurationSelect(coordinator, entry)])


def _label(minutes: int) -> str:
    return f"{minutes} min"


class StaggEKGHoldDurationSelect(CoordinatorEntity, SelectEntity):
    """How long the kettle holds temperature after a boil.

    A regular control rather than a configuration entity, so it shows on
    dashboards next to the Heating switch: it's something people change
    from day to day.
    """

    _attr_options = [_label(m) for m in HOLD_MINUTES_OPTIONS]

    def __init__(
        self, coordinator: StaggEKGDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the select."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{entry.entry_id}_hold_duration"
        self._attr_name = "Hold Duration"
        self._attr_icon = "mdi:timer-sand"

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

    @property
    def current_option(self) -> str | None:
        """Return the hold duration the kettle reports."""
        minutes = self.coordinator.hold_minutes
        return _label(minutes) if minutes in HOLD_MINUTES_OPTIONS else None

    async def async_select_option(self, option: str) -> None:
        """Write the chosen hold duration to the kettle."""
        minutes = int(option.split()[0])
        try:
            self.coordinator.hold_minutes = await self.hass.async_add_executor_job(
                self.coordinator.client.set_hold_minutes, minutes
            )
        except Exception as err:
            raise HomeAssistantError(f"Couldn't set the hold to {option}: {err}") from err
        self.async_write_ha_state()
