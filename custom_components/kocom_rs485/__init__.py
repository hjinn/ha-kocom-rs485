"""Kocom RS485 heating integration for Home Assistant.

Controls a Kocom-compatible boiler controller on an RS485 bus through an
Elfin EW11 (TCP).
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant

from .coordinator import KocomConfigEntry, KocomCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: KocomConfigEntry) -> bool:
    coordinator = KocomCoordinator(hass, entry)
    await coordinator.async_connect()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KocomConfigEntry) -> bool:
    await entry.runtime_data.async_shutdown()
    return True
