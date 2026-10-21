"""Config flow: EW11 address, then rooms (discovered, or chosen by hand) (ADR-0004)."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_ROOMS,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .discovery import ROOMS, CannotConnect, discover_rooms

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(int, vol.Range(min=1, max=65535)),
    }
)

ROOM_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=[str(room) for room in ROOMS],
        multiple=True,
        mode=SelectSelectorMode.LIST,
        translation_key="room",
    )
)


SCAN_INTERVAL_SELECTOR = vol.All(
    NumberSelector(
        NumberSelectorConfig(
            min=MIN_SCAN_INTERVAL,
            max=MAX_SCAN_INTERVAL,
            step=1,
            unit_of_measurement="s",
            mode=NumberSelectorMode.BOX,
        )
    ),
    vol.Coerce(int),
)


class KocomRs485ConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> KocomRs485OptionsFlow:
        return KocomRs485OptionsFlow()

    def __init__(self) -> None:
        self._host = ""
        self._port = DEFAULT_PORT
        self._found: list[int] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._host = user_input[CONF_HOST]
            self._port = user_input[CONF_PORT]
            # before discovery: a configured EW11's bus belongs to the running integration
            await self.async_set_unique_id(f"{self._host}:{self._port}")
            self._abort_if_unique_id_configured()
            try:
                self._found = await discover_rooms(self._host, self._port)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_rooms()
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_rooms(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None and not user_input[CONF_ROOMS]:
            errors["base"] = "no_rooms"
        elif user_input is not None:
            return self.async_create_entry(
                title=f"Kocom RS485 ({self._host})",
                data={
                    CONF_HOST: self._host,
                    CONF_PORT: self._port,
                    CONF_ROOMS: sorted(int(room) for room in user_input[CONF_ROOMS]),
                },
            )
        schema = vol.Schema(
            {vol.Required(CONF_ROOMS, default=[str(room) for room in self._found]): ROOM_SELECTOR}
        )
        return self.async_show_form(
            step_id="rooms",
            data_schema=schema,
            errors=errors,
            description_placeholders={"found": str(len(self._found))},
        )


class KocomRs485OptionsFlow(OptionsFlowWithReload):
    """Polling interval (ADR-0015); saving reloads the entry."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Required(CONF_SCAN_INTERVAL, default=current): SCAN_INTERVAL_SELECTOR}
            ),
        )
