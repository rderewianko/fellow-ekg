"""Config flow for Stagg EKG integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_RAPID_RISE_AUTO_STOP,
    CONF_RAPID_RISE_THRESHOLD,
    CONF_TEMP_SET_METHOD,
    CONF_TEMPERATURE_UNIT,
    DEFAULT_RAPID_RISE_AUTO_STOP,
    DEFAULT_RAPID_RISE_THRESHOLD,
    DOMAIN,
    MAX_RAPID_RISE_THRESHOLD,
    MIN_RAPID_RISE_THRESHOLD,
    TEMP_METHOD_DIAL,
    TEMP_METHOD_DIRECT,
    UNIT_CELSIUS,
    UNIT_FAHRENHEIT,
)
from .discovery import discover_kettles
from .kettle import StaggEKGClient

_LOGGER = logging.getLogger(__name__)

# Sentinel option in the discovery picker that means "skip the list and
# enter an IP by hand."
MANUAL_HOST_CHOICE = "manual"

STEP_MANUAL_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_TEMPERATURE_UNIT, default=UNIT_CELSIUS): vol.In(
            [UNIT_CELSIUS, UNIT_FAHRENHEIT]
        ),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    client = StaggEKGClient(host=data[CONF_HOST])

    try:
        # Try to get state to verify connectivity
        state = await hass.async_add_executor_job(client.get_state)
    except Exception as err:
        _LOGGER.error("Cannot connect to kettle: %s", err)
        raise CannotConnect

    # Return info that you want to store in the config entry.
    return {"title": f"Stagg EKG+ ({data[CONF_HOST]})"}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Stagg EKG."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow state."""
        self._discovered: list[str] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Run discovery first, then route to the picker or manual entry."""
        self._discovered = await discover_kettles(self.hass)
        if self._discovered:
            return await self.async_step_pick()
        return await self.async_step_manual()

    async def async_step_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Let the user choose a discovered kettle or fall through to manual entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            choice = user_input[CONF_HOST]
            if choice == MANUAL_HOST_CHOICE:
                return await self.async_step_manual()
            data = {
                CONF_HOST: choice,
                CONF_TEMPERATURE_UNIT: user_input[CONF_TEMPERATURE_UNIT],
            }
            try:
                info = await validate_input(self.hass, data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=data)

        host_options = {ip: ip for ip in self._discovered}
        host_options[MANUAL_HOST_CHOICE] = "Enter IP manually"

        return self.async_show_form(
            step_id="pick",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=self._discovered[0]): vol.In(
                        host_options
                    ),
                    vol.Required(
                        CONF_TEMPERATURE_UNIT, default=UNIT_CELSIUS
                    ): vol.In([UNIT_CELSIUS, UNIT_FAHRENHEIT]),
                }
            ),
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manual host entry (used when discovery finds nothing or user opts out)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="manual", data_schema=STEP_MANUAL_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Stagg EKG."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Update kettle units if changed
            new_unit = user_input[CONF_TEMPERATURE_UNIT]
            current_unit = self.config_entry.data.get(CONF_TEMPERATURE_UNIT, UNIT_CELSIUS)

            if new_unit != current_unit:
                # Update the kettle's unit setting
                client = StaggEKGClient(host=self.config_entry.data[CONF_HOST])
                try:
                    if new_unit == UNIT_CELSIUS:
                        await self.hass.async_add_executor_job(client.set_units_celsius)
                    else:
                        await self.hass.async_add_executor_job(client.set_units_fahrenheit)
                except Exception as err:
                    _LOGGER.error("Failed to update kettle units: %s", err)

            # Update config entry with new data
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={**self.config_entry.data, **user_input}
            )
            return self.async_create_entry(title="", data={})

        current_unit = self.config_entry.data.get(CONF_TEMPERATURE_UNIT, UNIT_CELSIUS)
        current_method = self.config_entry.data.get(
            CONF_TEMP_SET_METHOD, TEMP_METHOD_DIRECT
        )
        current_auto_stop = self.config_entry.data.get(
            CONF_RAPID_RISE_AUTO_STOP, DEFAULT_RAPID_RISE_AUTO_STOP
        )
        current_threshold = self.config_entry.data.get(
            CONF_RAPID_RISE_THRESHOLD, DEFAULT_RAPID_RISE_THRESHOLD
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TEMPERATURE_UNIT,
                        default=current_unit
                    ): vol.In([UNIT_CELSIUS, UNIT_FAHRENHEIT]),
                    vol.Required(
                        CONF_TEMP_SET_METHOD,
                        default=current_method,
                    ): vol.In([TEMP_METHOD_DIRECT, TEMP_METHOD_DIAL]),
                    vol.Required(
                        CONF_RAPID_RISE_AUTO_STOP,
                        default=current_auto_stop,
                    ): bool,
                    vol.Required(
                        CONF_RAPID_RISE_THRESHOLD,
                        default=current_threshold,
                    ): vol.All(
                        vol.Coerce(float),
                        vol.Range(
                            min=MIN_RAPID_RISE_THRESHOLD,
                            max=MAX_RAPID_RISE_THRESHOLD,
                        ),
                    ),
                }
            ),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
