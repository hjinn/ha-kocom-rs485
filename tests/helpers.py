"""Helpers shared by tests that set up the integration against a fake EW11."""
from __future__ import annotations

import asyncio

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kocom_rs485.const import DOMAIN


async def eventually(predicate, timeout: float = 2.0) -> None:
    # counts iterations instead of reading a clock: under `freezer` the
    # test's view of time.monotonic is frozen
    for _ in range(int(timeout / 0.01)):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not met in time")


async def setup_entry(hass: HomeAssistant, port: int, rooms: list[int], options: dict | None = None):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"127.0.0.1:{port}",
        data={"host": "127.0.0.1", "port": port, "rooms": rooms},
        options=options or {},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
