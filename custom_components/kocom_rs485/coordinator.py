"""Coordinator: owns the EW11 connection and the state of every room."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import CONF_ROOMS, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, ROOM_KEYS
from .master import Master, NoResponse
from .protocol import ThermoMode, ThermoState
from .transport import TcpTransport

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 10
DEFAULT_HEAT_TEMP = 23  # until a room has been seen heating (ADR-0005)
MISSES_UNTIL_UNAVAILABLE = 2  # ADR-0007: one miss can be a bus collision
# extra keyword arguments for the bus layers; tests shorten the timings
TRANSPORT_OPTIONS: dict = {}
MASTER_OPTIONS: dict = {}


@dataclass
class RoomData:
    state: ThermoState | None = None
    available: bool = False
    misses: int = 0  # consecutive polls without an answer
    lost: bool = False  # unavailable because of misses; logged once each way
    heat_temp: int = DEFAULT_HEAT_TEMP  # last heating setpoint seen (ADR-0005)
    reported_at: datetime | None = None  # last report that changed the state


type KocomConfigEntry = ConfigEntry[KocomCoordinator]


class KocomCoordinator(DataUpdateCoordinator[dict[int, RoomData]]):
    config_entry: KocomConfigEntry

    def __init__(self, hass: HomeAssistant, entry: KocomConfigEntry) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.data = {room: RoomData() for room in entry.data[CONF_ROOMS]}
        self._connected = asyncio.Event()
        self._ever_connected = False
        self.transport = TcpTransport(
            entry.data[CONF_HOST],
            entry.data[CONF_PORT],
            on_data=self._on_data,
            on_connection_change=self._on_connection_change,
            idle_timeout=interval * 3,  # ADR-0013
            **TRANSPORT_OPTIONS,
        )
        self.master = Master(self.transport.write, on_report=self._on_report, **MASTER_OPTIONS)

    async def async_connect(self) -> None:
        await self.transport.start()
        try:
            await asyncio.wait_for(self._connected.wait(), CONNECT_TIMEOUT)
        except TimeoutError:
            await self.transport.stop()
            raise ConfigEntryNotReady(
                f"no connection to the EW11 at {self.transport.endpoint}"
            ) from None

    async def async_shutdown(self) -> None:
        await self.master.close()  # queued acks first (ADR-0014)
        await self.transport.stop()
        await super().async_shutdown()

    async def async_command(self, room: int, mode: ThermoMode, target_temp: int | None = None) -> None:
        """Change a room; the state shown afterwards is what the thermo reports.

        Without a target temperature, heat and off use the room's last heating setpoint.
        """
        if target_temp is None and mode is not ThermoMode.AWAY:
            target_temp = self.data[room].heat_temp
        try:
            state = await self.master.command(room, mode, target_temp)
        except NoResponse as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"room": str(room)},
            ) from err
        self._apply(room, state)
        self.async_update_listeners()

    def _on_data(self, data: bytes) -> None:
        self.master.feed(data)

    def _on_connection_change(self, connected: bool) -> None:
        if connected:
            reconnected = self._ever_connected
            self._ever_connected = True
            self._connected.set()
            if reconnected:
                # reports may have been missed meanwhile: query everything now
                self.config_entry.async_create_background_task(
                    self.hass, self.async_refresh(), f"{DOMAIN} refresh after reconnect"
                )
            return
        self._connected.clear()
        self.master.connection_lost()
        for room_data in self.data.values():
            room_data.available = False
            room_data.reported_at = None  # the cache cannot be trusted across the gap
        self.async_update_listeners()

    def _on_report(self, room: int, state: ThermoState) -> None:
        if room not in self.data:
            return
        try:
            if state != self.data[room].state:
                # a change we did not poll for (e.g. on the thermostat); a resent
                # answer to our own query changes nothing and does not count
                self.data[room].reported_at = dt_util.utcnow()
            self._apply(room, state)
            # not async_set_updated_data(): that also postpones the next poll, and
            # frequent reports would then starve the current-temperature polling
            self.async_update_listeners()
        except Exception:  # must not break the Master's packet handling
            _LOGGER.exception("error applying report from room %s", room)

    def _apply(self, room: int, state: ThermoState) -> None:
        room_data = self.data[room]
        room_data.state = state
        if state.mode is ThermoMode.HEAT:
            room_data.heat_temp = state.target_temp
        room_data.available = True
        room_data.misses = 0
        if room_data.lost:
            room_data.lost = False
            _LOGGER.info("room %s (%s) available again", room, ROOM_KEYS[room])

    async def _async_update_data(self) -> dict[int, RoomData]:
        now = dt_util.utcnow()
        for room, room_data in self.data.items():
            if room_data.reported_at and now - room_data.reported_at < self.update_interval:
                continue  # reported on its own recently (ADR-0015)
            started = self.hass.loop.time()
            try:
                state = await self.master.query(room)
            except NoResponse as err:
                room_data.misses += 1
                _LOGGER.debug(
                    "room %s (%s) missed poll %s/%s: %s",
                    room, ROOM_KEYS[room], room_data.misses, MISSES_UNTIL_UNAVAILABLE, err,
                )
                if room_data.misses >= MISSES_UNTIL_UNAVAILABLE and not room_data.lost:
                    room_data.lost = True
                    room_data.available = False
                    _LOGGER.warning(
                        "room %s (%s) unavailable after %s missed polls: %s",
                        room, ROOM_KEYS[room], room_data.misses, err,
                    )
            else:
                waited = self.master.last_wait
                _LOGGER.debug(
                    "room %s (%s) answered in %.2fs (waited %.2fs for the controller)",
                    room, ROOM_KEYS[room], self.hass.loop.time() - started - waited, waited,
                )
                self._apply(room, state)
        return self.data
