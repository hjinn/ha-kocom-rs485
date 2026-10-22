"""Find which rooms answer on the bus (ADR-0004). No Home Assistant imports."""
from __future__ import annotations

import asyncio

from .master import Master, NoResponse
from .transport import TcpTransport

ROOMS = (0, 1, 2, 3)


class CannotConnect(Exception):
    """The EW11 could not be reached."""


async def discover_rooms(
    host: str,
    port: int,
    *,
    connect_timeout: float = 10,
    initial_quiet: float = 1.0,
    ack_timeout: float = 0.5,
    report_timeout: float = 1.2,
    request_gap: float = 1.0,
) -> list[int]:
    """Connect to the EW11, query every room once and return those that answered."""
    connected = asyncio.Event()
    master: Master | None = None

    def on_connection_change(is_connected: bool) -> None:
        if is_connected:
            connected.set()
        else:
            master.connection_lost()

    transport = TcpTransport(
        host,
        port,
        on_data=lambda data: master.feed(data),
        on_connection_change=on_connection_change,
        initial_quiet=initial_quiet,
        connect_timeout=connect_timeout,
    )
    master = Master(
        transport.write,
        on_report=lambda room, state: None,
        ack_timeout=ack_timeout,
        report_timeout=report_timeout,
        request_gap=request_gap,
    )
    await transport.start()
    try:
        try:
            await asyncio.wait_for(connected.wait(), connect_timeout)
        except TimeoutError:
            raise CannotConnect(f"no connection to {host}:{port} within {connect_timeout}s") from None
        found = []
        for room in ROOMS:
            try:
                await master.query(room)
            except NoResponse:
                continue
            found.append(room)
        return found
    finally:
        await master.close()  # let the last report's ack go out first
        await transport.stop()
