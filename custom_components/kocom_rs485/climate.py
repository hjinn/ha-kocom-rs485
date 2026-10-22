"""Heater entities: one climate entity per room (ADR-0016, ADR-0017)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    PRESET_AWAY,
    PRESET_HOME,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, PRECISION_WHOLE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ROOM_KEYS
from .coordinator import KocomConfigEntry, KocomCoordinator
from .protocol import ThermoMode, ThermoState

PARALLEL_UPDATES = 0  # the Master already puts one request at a time on the bus


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KocomConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(KocomHeater(coordinator, room) for room in coordinator.data)


class KocomHeater(CoordinatorEntity[KocomCoordinator], ClimateEntity):
    _attr_has_entity_name = True
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_preset_modes = [PRESET_HOME, PRESET_AWAY]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_precision = PRECISION_WHOLE
    _attr_target_temperature_step = 1
    _attr_min_temp = 5  # ADR-0005; the controller's own range is unverified
    _attr_max_temp = 40

    def __init__(self, coordinator: KocomCoordinator, room: int) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        key = ROOM_KEYS[room]
        self._room = room
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self.entity_id = f"climate.heater_{key}"  # language independent (ADR-0017)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            translation_key="heater",
            manufacturer="Kocom",
            model="RS485 boiler controller",
        )

    @property
    def _state(self) -> ThermoState | None:
        return self.coordinator.data[self._room].state

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data[self._room].available

    @property
    def hvac_mode(self) -> HVACMode | None:
        if self._state is None:
            return None
        return HVACMode.OFF if self._state.mode is ThermoMode.OFF else HVACMode.HEAT

    @property
    def preset_mode(self) -> str | None:
        """Home while heating, away while away; none applies while off."""
        if self._state is None or self._state.mode is ThermoMode.OFF:
            return None
        return PRESET_AWAY if self._state.mode is ThermoMode.AWAY else PRESET_HOME

    @property
    def target_temperature(self) -> float | None:
        return self._state.target_temp if self._state else None

    @property
    def current_temperature(self) -> float | None:
        return self._state.current_temp if self._state else None

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Heat at the given temperature; this also turns heating on from off or away (Q20)."""
        mode = ThermoMode.OFF if kwargs.get(ATTR_HVAC_MODE) == HVACMode.OFF else ThermoMode.HEAT
        await self._command(mode, int(kwargs[ATTR_TEMPERATURE]))

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Off, or heat at the room's last heating setpoint."""
        mode = ThermoMode.OFF if hvac_mode == HVACMode.OFF else ThermoMode.HEAT
        await self._command(mode)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Away, or back to heating at the room's last heating setpoint."""
        mode = ThermoMode.AWAY if preset_mode == PRESET_AWAY else ThermoMode.HEAT
        await self._command(mode)

    async def _command(self, mode: ThermoMode, target_temp: int | None = None) -> None:
        try:
            await self.coordinator.async_command(self._room, mode, target_temp)
        except HomeAssistantError as err:
            # same message, but naming the room as the user sees it ("거실")
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"room": str(self.name)},
            ) from err
