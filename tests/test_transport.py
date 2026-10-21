"""Tests for the EW11 TCP transport, against a real localhost server."""
import asyncio
import logging
import time

import pytest

from custom_components.kocom_rs485.transport import (
    TcpTransport,
    TransportNotConnected,
    reconnect_delay,
)


class FakeEw11:
    """A localhost TCP server standing in for the EW11."""

    def __init__(self) -> None:
        self._clients: asyncio.Queue = asyncio.Queue()
        self._server: asyncio.Server | None = None
        self._writers: list[asyncio.StreamWriter] = []
        self.port = 0

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._accept, "127.0.0.1", self.port)
        self.port = self._server.sockets[0].getsockname()[1]

    async def _accept(self, reader, writer) -> None:
        self._writers.append(writer)
        await self._clients.put((reader, writer))

    async def next_client(self):
        return await asyncio.wait_for(self._clients.get(), 2)

    async def close(self) -> None:
        # wait_closed() waits for every accepted connection, so close them here
        # rather than relying on garbage collection (a failing test keeps them alive)
        for writer in self._writers:
            writer.close()
        self._server.close()
        await self._server.wait_closed()


@pytest.fixture
async def ew11():
    server = FakeEw11()
    await server.start()
    yield server
    await server.close()


class Recorder:
    """Collects transport callbacks."""

    def __init__(self) -> None:
        self.data = bytearray()
        self.states: list[bool] = []

    def on_data(self, data: bytes) -> None:
        self.data += data

    def on_connection_change(self, connected: bool) -> None:
        self.states.append(connected)


async def eventually(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.01)


@pytest.fixture
async def make_transport(ew11):
    """Builds transports to the fake EW11 and always stops them before it closes."""
    transports: list[TcpTransport] = []

    def make(recorder: Recorder, **kwargs) -> TcpTransport:
        transport = TcpTransport(
            "127.0.0.1",
            ew11.port,
            on_data=recorder.on_data,
            on_connection_change=recorder.on_connection_change,
            **kwargs,
        )
        transports.append(transport)
        return transport

    yield make
    for transport in transports:
        await transport.stop()


@pytest.mark.parametrize(
    ("attempt", "seconds"),
    [(0, 5), (1, 10), (2, 30), (3, 60), (4, 60), (100, 60)],
)
def test_reconnect_backoff_follows_adr_0007(attempt, seconds):
    assert reconnect_delay(attempt) == seconds


async def test_delivers_received_bytes_in_order(ew11, make_transport):
    recorder = Recorder()
    transport = make_transport(recorder)
    await transport.start()
    _, writer = await ew11.next_client()

    writer.write(b"\xaa\x55\x30")
    await writer.drain()
    writer.write(b"\xbc\x00")
    await writer.drain()

    await eventually(lambda: recorder.data == b"\xaa\x55\x30\xbc\x00")


async def test_write_reaches_ew11(ew11, make_transport):
    transport = make_transport(Recorder(), initial_quiet=0)
    await transport.start()
    reader, _ = await ew11.next_client()
    await eventually(lambda: transport.connected)

    await transport.write(b"\xaa\x55\x30\xbc")

    assert await asyncio.wait_for(reader.readexactly(4), 2) == b"\xaa\x55\x30\xbc"


async def test_reconnects_after_ew11_drops_connection(ew11, make_transport):
    recorder = Recorder()
    transport = make_transport(recorder, delays=lambda attempt: 0.05)
    await transport.start()
    _, first = await ew11.next_client()
    await eventually(lambda: recorder.states == [True])

    first.close()

    await eventually(lambda: recorder.states == [True, False, True])
    _, second = await ew11.next_client()
    second.write(b"\x0d\x0d")
    await second.drain()
    await eventually(lambda: recorder.data == b"\x0d\x0d")


async def test_write_without_connection_raises(ew11, make_transport):
    await ew11.close()  # nothing listening on the port any more
    transport = make_transport(Recorder(), delays=lambda attempt: 0.05)
    await transport.start()

    with pytest.raises(TransportNotConnected):
        await transport.write(b"\xaa\x55")


async def test_write_waits_gap_after_last_received_byte(ew11, make_transport):
    recorder = Recorder()
    transport = make_transport(recorder, write_gap=0.2, initial_quiet=0)
    await transport.start()
    reader, writer = await ew11.next_client()

    sent_at = time.monotonic()  # the transport cannot read the byte before this
    writer.write(b"\x0d")
    await writer.drain()
    await eventually(lambda: recorder.data == b"\x0d")
    await transport.write(b"\xaa")
    await asyncio.wait_for(reader.readexactly(1), 2)

    assert time.monotonic() - sent_at >= 0.2


async def test_first_write_waits_quiet_time_when_nothing_received(ew11, make_transport):
    transport = make_transport(Recorder(), write_gap=0, initial_quiet=0.2)
    started_at = time.monotonic()  # the connection cannot exist before this
    await transport.start()
    reader, _ = await ew11.next_client()
    await eventually(lambda: transport.connected)

    await transport.write(b"\xaa")
    await asyncio.wait_for(reader.readexactly(1), 2)

    assert time.monotonic() - started_at >= 0.2


async def test_stop_closes_connection_and_does_not_reconnect(ew11, make_transport):
    transport = make_transport(Recorder(), delays=lambda attempt: 0.05)
    await transport.start()
    reader, _ = await ew11.next_client()
    await eventually(lambda: transport.connected)

    await transport.stop()

    assert await asyncio.wait_for(reader.read(), 2) == b""  # EW11 sees the close
    assert not transport.connected
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(ew11.next_client(), 0.3)


async def test_write_raises_if_connection_drops_while_waiting(ew11, make_transport):
    transport = make_transport(Recorder(), initial_quiet=0.3, delays=lambda attempt: 10)
    await transport.start()
    _, server_side = await ew11.next_client()
    await eventually(lambda: transport.connected)

    pending = asyncio.create_task(transport.write(b"\xaa"))
    await asyncio.sleep(0.05)  # write is now waiting out the quiet time
    server_side.close()

    with pytest.raises(TransportNotConnected):
        await asyncio.wait_for(pending, 2)


async def test_reconnects_when_nothing_received_within_idle_timeout(ew11, make_transport):
    recorder = Recorder()
    transport = make_transport(recorder, idle_timeout=0.2, delays=lambda attempt: 0.05)
    await transport.start()
    await ew11.next_client()

    # the EW11 stays silent, as a powered-off one would

    await eventually(lambda: recorder.states == [True, False, True])
    await ew11.next_client()


async def test_idle_timeout_counts_silence_not_connection_age(ew11, make_transport):
    recorder = Recorder()
    transport = make_transport(recorder, idle_timeout=0.2, delays=lambda attempt: 0.05)
    await transport.start()
    _, writer = await ew11.next_client()

    for _ in range(6):  # 0.6s in total, never silent for 0.2s
        writer.write(b"\x00")
        await writer.drain()
        await asyncio.sleep(0.1)

    assert recorder.states == [True]


async def test_callback_error_is_logged_and_receiving_continues(ew11, make_transport, caplog):
    recorder = Recorder()
    calls = 0

    def flaky_on_data(data: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("bug in the layer above")
        recorder.on_data(data)

    transport = TcpTransport(
        "127.0.0.1", ew11.port,
        on_data=flaky_on_data, on_connection_change=recorder.on_connection_change,
    )
    await transport.start()
    _, writer = await ew11.next_client()
    writer.write(b"\x01")
    await writer.drain()
    await eventually(lambda: calls == 1)
    writer.write(b"\x02")
    await writer.drain()

    await eventually(lambda: recorder.data == b"\x02")
    assert recorder.states == [True]
    assert "bug in the layer above" in caplog.text
    await transport.stop()


async def test_connection_callback_error_is_logged_and_receiving_continues(ew11, caplog):
    recorder = Recorder()

    def broken_on_connection_change(connected: bool) -> None:
        raise RuntimeError("bug in connection handler")

    transport = TcpTransport(
        "127.0.0.1", ew11.port,
        on_data=recorder.on_data, on_connection_change=broken_on_connection_change,
    )
    await transport.start()
    _, writer = await ew11.next_client()
    writer.write(b"\x03")
    await writer.drain()

    await eventually(lambda: recorder.data == b"\x03")
    assert "bug in connection handler" in caplog.text
    await transport.stop()


async def test_logs_connect_once_and_loss_once_despite_retries(ew11, make_transport, caplog):
    caplog.set_level(logging.DEBUG, logger="custom_components.kocom_rs485.transport")
    recorder = Recorder()
    transport = make_transport(recorder, delays=lambda attempt: 0.05)
    await transport.start()
    await ew11.next_client()
    await eventually(lambda: recorder.states == [True])

    await ew11.close()  # EW11 goes away and stays away: retries keep failing
    await eventually(lambda: recorder.states == [True, False])
    await asyncio.sleep(0.3)

    endpoint = f"127.0.0.1:{ew11.port}"
    infos = [r for r in caplog.records if r.levelno == logging.INFO and endpoint in r.getMessage()]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and endpoint in r.getMessage()]
    assert len(infos) == 1
    assert len(warnings) == 1
