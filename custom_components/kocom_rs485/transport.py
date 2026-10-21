"""Byte-stream transport to the EW11 over TCP (ADR-0002).

Pure asyncio, no Home Assistant imports. Framing and the request/ack
flow live above this layer; this module only owns the connection,
reconnecting (ADR-0007) and write timing (docs/protocol.md).
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)

READ_SIZE = 256
RECONNECT_DELAYS = (5, 10, 30, 60)


def reconnect_delay(attempt: int) -> float:
    """Seconds to wait before reconnect attempt number `attempt` (0-based)."""
    return RECONNECT_DELAYS[min(attempt, len(RECONNECT_DELAYS) - 1)]


class TransportNotConnected(Exception):
    """Raised when writing while there is no connection to the EW11."""


class TcpTransport:
    """TCP client to the EW11 that keeps itself connected."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        on_data: Callable[[bytes], None],
        on_connection_change: Callable[[bool], None],
        write_gap: float = 0.03,
        initial_quiet: float = 1.0,
        delays: Callable[[int], float] = reconnect_delay,
        idle_timeout: float | None = None,
        connect_timeout: float = 10,
    ) -> None:
        self._host = host
        self._port = port
        self._on_data = on_data
        self._on_connection_change = on_connection_change
        self._write_gap = write_gap
        self._initial_quiet = initial_quiet
        self._connected_at = 0.0
        self._last_read: float | None = None
        self._delays = delays
        self._idle_timeout = idle_timeout
        self._connect_timeout = connect_timeout
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task | None = None

    @property
    def connected(self) -> bool:
        return self._writer is not None

    async def write(self, data: bytes) -> None:
        writer = self._writer
        if writer is None:
            raise TransportNotConnected(f"not connected to {self._host}:{self._port}")
        # let the bus go quiet after the last received byte (avoids collisions);
        # with nothing received yet on this connection, wait the longer quiet time
        if self._last_read is None:
            ready_at = self._connected_at + self._initial_quiet
        else:
            ready_at = self._last_read + self._write_gap
        wait = ready_at - asyncio.get_running_loop().time()
        if wait > 0:
            await asyncio.sleep(wait)
            if self._writer is not writer:  # dropped (or replaced) while waiting
                raise TransportNotConnected(f"connection to {self._host}:{self._port} lost")
        writer.write(data)
        await writer.drain()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._writer:
            self._writer.close()
            self._writer = None

    def _notify(self, connected: bool) -> None:
        try:
            self._on_connection_change(connected)
        except Exception:  # a bug above must not kill the connection loop
            _LOGGER.exception("error handling connection change for %s:%s", self._host, self._port)

    async def _run(self) -> None:
        attempt = 0
        while True:
            try:
                # an unreachable EW11 (e.g. Wi-Fi down) would otherwise wait for
                # the OS TCP timeout; TimeoutError is an OSError, counted as a failed try
                reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self._host, self._port), self._connect_timeout
                )
            except OSError as err:
                _LOGGER.debug("connecting to %s:%s failed: %r", self._host, self._port, err)
            else:
                _LOGGER.info("connected to %s:%s", self._host, self._port)
                attempt = 0
                self._connected_at = asyncio.get_running_loop().time()
                self._last_read = None
                self._notify(True)
                # no bytes within idle_timeout: peer presumed dead (ADR-0013)
                try:
                    while data := await asyncio.wait_for(reader.read(READ_SIZE), self._idle_timeout):
                        self._last_read = asyncio.get_running_loop().time()
                        try:
                            self._on_data(data)
                        except Exception:  # a bug above must not kill the connection
                            _LOGGER.exception("error handling data from %s:%s", self._host, self._port)
                    reason = "closed by EW11"
                except TimeoutError:
                    reason = f"nothing received for {self._idle_timeout}s"
                except OSError as err:
                    reason = str(err)
                _LOGGER.warning("connection to %s:%s lost (%s), reconnecting", self._host, self._port, reason)
                self._writer.close()
                self._writer = None
                self._notify(False)
            await asyncio.sleep(self._delays(attempt))
            attempt += 1
