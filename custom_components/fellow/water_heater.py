"""Water heater platform for Stagg EKG integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import StaggEKGDataUpdateCoordinator
from .const import DOMAIN, CONF_TEMPERATURE_UNIT, UNIT_CELSIUS, UNIT_FAHRENHEIT
from .switch import KEEP_WARM_HINT

_LOGGER = logging.getLogger(__name__)

# Temperature bounds (Celsius)
MIN_TEMP_C = 40
MAX_TEMP_C = 100

# Temperature bounds (Fahrenheit)
MIN_TEMP_F = 104
MAX_TEMP_F = 212

# Operation modes
OPERATION_MODE_OFF = "off"
OPERATION_MODE_HEAT = "heat"
OPERATION_MODE_WARM = "warm"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Stagg EKG water heater."""
    coordinator: StaggEKGDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([StaggEKGWaterHeater(coordinator, entry)])


class StaggEKGWaterHeater(CoordinatorEntity, WaterHeaterEntity):
    """Representation of a Stagg EKG kettle as a water heater."""

    _attr_supported_features = (
        WaterHeaterEntityFeature.TARGET_TEMPERATURE
        | WaterHeaterEntityFeature.ON_OFF
        | WaterHeaterEntityFeature.OPERATION_MODE
    )
    _attr_operation_list = [OPERATION_MODE_OFF, OPERATION_MODE_HEAT, OPERATION_MODE_WARM]

    def __init__(
        self, coordinator: StaggEKGDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the water heater."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_water_heater"
        self._attr_name = "Kettle"
        self._attr_has_entity_name = True

        # Set temperature unit based on configuration
        configured_unit = entry.data.get(CONF_TEMPERATURE_UNIT, UNIT_CELSIUS)
        if configured_unit == UNIT_FAHRENHEIT:
            self._attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
            self._attr_min_temp = MIN_TEMP_F
            self._attr_max_temp = MAX_TEMP_F
        else:
            self._attr_temperature_unit = UnitOfTemperature.CELSIUS
            self._attr_min_temp = MIN_TEMP_C
            self._attr_max_temp = MAX_TEMP_C

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
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        if self.coordinator.data and "state" in self.coordinator.data:
            temp_c = self.coordinator.data["state"].current_temp_c
            if temp_c is None:
                return None
            # Convert to configured unit
            if self._attr_temperature_unit == UnitOfTemperature.FAHRENHEIT:
                return round(temp_c * 9/5 + 32, 1)
            return temp_c
        return None

    def _in_unit(self, temp_c: float | None) -> float | None:
        if temp_c is not None and self._attr_temperature_unit == UnitOfTemperature.FAHRENHEIT:
            return round(temp_c * 9/5 + 32, 1)
        return temp_c

    @property
    def target_temperature(self) -> float | None:
        """Return the Heat Up Target (what a boil heats to).

        water_heater.set_temperature sets it, as it always set the kettle's
        target, so existing automations keep working.
        """
        return self._in_unit(self.coordinator.targets.heat_target)


    @property
    def current_operation(self) -> str:
        """Return current operation (off, heat, warm)."""
        if not self.coordinator.data or "state" not in self.coordinator.data:
            return OPERATION_MODE_OFF

        state = self.coordinator.data["state"]

        if state.is_off:
            return OPERATION_MODE_OFF
        elif state.is_heating:
            return OPERATION_MODE_HEAT
        elif state.warming or state.is_holding:
            return OPERATION_MODE_WARM
        else:
            # S_Standby, S_HeatOff without warming = effectively off
            return OPERATION_MODE_OFF

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes.

        hold_temperature is the Hold Target, shown here for reference; set it
        with number.set_value on the Hold Target entity.
        """
        if not self.coordinator.data or "state" not in self.coordinator.data:
            return None
        return {
            "docked": self.coordinator.data["state"].is_docked,
            "hold_temperature": self._in_unit(self.coordinator.targets.hold_target),
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature using batched dial rotation."""
        temperature = kwargs.get("temperature")
        if temperature is None:
            return

        # Convert to Celsius if needed
        if self._attr_temperature_unit == UnitOfTemperature.FAHRENHEIT:
            temp_celsius = (temperature - 32) * 5/9
        else:
            temp_celsius = temperature

        # Same as setting Heat Up Target: written to the kettle now, or when a
        # lowered hold ends.
        await self.coordinator.async_set_heat_target(temp_celsius)

        await self.coordinator.async_request_refresh()

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set operation mode."""
        if operation_mode == OPERATION_MODE_OFF:
            await self.hass.async_add_executor_job(
                self.coordinator.client.stop_heating
            )
            await self.hass.async_add_executor_job(self.coordinator.client.end_hold)
        elif operation_mode == OPERATION_MODE_HEAT:
            await self.coordinator.async_before_boil()
            await self.hass.async_add_executor_job(
                self.coordinator.client.start_heating
            )
        elif operation_mode == OPERATION_MODE_WARM:
            # Like the Warming / Holding switch: a hold only comes from a boil.
            state = (self.coordinator.data or {}).get("state")
            if not (state and state.is_holding):
                raise HomeAssistantError(KEEP_WARM_HINT)

        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the kettle on and start heating."""
        await self.coordinator.async_before_boil()
        await self.hass.async_add_executor_job(
            self.coordinator.client.start_heating
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the kettle off."""
        await self.hass.async_add_executor_job(
            self.coordinator.client.stop_heating
        )
        await self.hass.async_add_executor_job(self.coordinator.client.end_hold)
        await self.coordinator.async_request_refresh()
