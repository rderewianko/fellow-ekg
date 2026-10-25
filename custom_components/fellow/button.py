"""Button platform for Stagg EKG integration."""
from __future__ import annotations

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import StaggEKGDataUpdateCoordinator
from .const import DOMAIN
from .kettle import EmergencyStopResult, KettleStopError
from .rise import is_heating_mode, is_holding_mode

NOTIFICATION_TITLE = "Fellow kettle: Emergency Stop"


def describe_result(result: EmergencyStopResult) -> str:
    """Say what the kettle was doing and what the stop achieved."""
    mode = result.mode_before
    if mode is None:
        message = "Couldn't read the kettle first. Stop sent; it now reports Off."
    elif is_heating_mode(mode) or is_holding_mode(mode):
        doing = "holding" if is_holding_mode(mode) else "heating"
        message = f"Kettle was {doing} ({mode}). Stop sent; it now reports Off."
    else:
        already = "already reported Off" if mode == "S_Off" else f"reported {mode}, not heating"
        message = (
            f"Kettle {already}. Stop sent anyway, since the heater has been "
            "seen running while the kettle reports Off."
        )
    if result.attempts > 1:
        message += f" It took {result.attempts} attempts."
    return message


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Stagg EKG buttons."""
    coordinator: StaggEKGDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([StaggEKGEmergencyStopButton(coordinator, entry)])


class StaggEKGEmergencyStopButton(CoordinatorEntity, ButtonEntity):
    """Kill switch: turn the heater and warmer off, whatever the mode says."""

    def __init__(
        self, coordinator: StaggEKGDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{entry.entry_id}_emergency_stop"
        self._attr_name = "Emergency Stop"
        self._attr_icon = "mdi:stop-circle"
        self._last_result: str | None = None

    @property
    def available(self) -> bool:
        """Always pressable, even when polling is failing."""
        return True

    @property
    def extra_state_attributes(self):
        """Return what the last press found and did."""
        return {"last_result": self._last_result}

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

    async def async_press(self) -> None:
        """Send the emergency stop and report what happened.

        A button has no success message in Home Assistant, so the outcome is
        shown as a persistent notification (one per kettle, replaced on each
        press) and in the `last_result` attribute. A failure also raises, so
        the press shows an error.
        """
        try:
            result = await self.hass.async_add_executor_job(
                self.coordinator.client.emergency_stop
            )
        except KettleStopError as err:
            message = f"{err}. Check it now."
            self._report(message)
            raise HomeAssistantError(message) from err
        else:
            self._report(describe_result(result))
        finally:
            await self.coordinator.async_request_refresh()

    def _report(self, message: str) -> None:
        self._last_result = message
        self.async_write_ha_state()
        persistent_notification.async_create(
            self.hass,
            message,
            title=NOTIFICATION_TITLE,
            notification_id=f"{DOMAIN}_{self._entry.entry_id}_emergency_stop",
        )
