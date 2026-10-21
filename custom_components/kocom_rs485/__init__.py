"""Kocom RS485 heating integration for Home Assistant.

Controls a Kocom-compatible boiler controller on an RS485 bus through an
Elfin EW11 (TCP).
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # placeholder until the coordinator and climate platform exist
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return True
