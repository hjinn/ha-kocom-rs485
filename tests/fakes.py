"""Fakes shared by the tests.

FakeThermo reproduces what the real controller did in captures/02-07
(docs/protocol.md): it acks every request, then reports the room state,
and repeats an un-acked report with seq 2 and 3.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable

from custom_components.kocom_rs485.protocol import MASTER, Cmd, Framer, Kind, Packet, thermo
from custom_components.kocom_rs485.transport import TransportNotConnected

STEP = 0.005  # fake thermo reaction time


def report_value(command: bytes, current: bytes) -> bytes:
    """What the real controller reports after a STATE command (captures/05-07)."""
    if command[0] == 0x01:
        return bytes.fromhex("00010a") + current[3:]
    if command[1] == 0x01:
        return bytes.fromhex("11010a") + current[3:]
    return command[:3] + current[3:]


class FakeThermo:
    def __init__(self, rooms: dict[int, str], deaf_for: int = 0) -> None:
        self.rooms = {room: bytes.fromhex(value) for room, value in rooms.items()}
        self.deaf_for = deaf_for  # ignore this many requests, like a collision on the bus
        self.lose_acks = False  # pretend the Master's acks never arrive
        self.connected = True
        self.write_delay = 0.0  # like the transport waiting out the write gap
        self.sent: list[Packet] = []  # everything the Master wrote
        self.emit: Callable[[bytes], None] = lambda data: None  # bytes towards the Master
        self._unacked: dict[int, Packet] = {}
        self._tasks: set[asyncio.Task] = set()

    async def write(self, data: bytes) -> None:
        """Stands in for the transport's write: one packet from the Master."""
        if self.write_delay:
            await asyncio.sleep(self.write_delay)
        if not self.connected:
            raise TransportNotConnected("EW11 gone")
        self.receive(Packet.from_bytes(data))

    def receive(self, packet: Packet) -> None:
        self.sent.append(packet)
        if packet.kind is Kind.ACK:
            if not self.lose_acks:
                self._unacked.pop(packet.dest.sub, None)
            return
        room = packet.dest.sub
        if packet.dest.device != thermo(0).device or room not in self.rooms:
            return
        if self.deaf_for:
            self.deaf_for -= 1
            return
        if packet.cmd == Cmd.STATE:
            self.rooms[room] = report_value(packet.value, self.rooms[room])
        self._later(self._answer(packet, room))

    async def _answer(self, request: Packet, room: int) -> None:
        await asyncio.sleep(STEP)
        self.emit(request.ack().to_bytes())
        await asyncio.sleep(STEP)
        await self.report(room)

    async def report(self, room: int) -> None:
        """Send the room state like the real controller: seq 1, then 2 and 3 if not acked."""
        for seq in (1, 2, 3):
            if room not in self.rooms:  # removed by the test meanwhile
                return
            packet = Packet(Kind.SEND, seq, MASTER, thermo(room), Cmd.STATE, self.rooms[room])
            self._unacked[room] = packet
            self.emit(packet.to_bytes())
            await asyncio.sleep(STEP * 4)
            if room not in self._unacked:
                return

    def _later(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    def acks_to(self, room: int) -> list[Packet]:
        return [p for p in self.sent if p.kind is Kind.ACK and p.dest == thermo(room)]



class FakeEw11Controller:
    """A localhost TCP server that behaves like the EW11 with the controller behind it."""

    def __init__(self, rooms: dict[int, str]) -> None:
        self.thermo = FakeThermo(rooms)
        self.port = 0
        self._server: asyncio.Server | None = None
        self._writers: list[asyncio.StreamWriter] = []

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._writers.append(writer)
        self.thermo.emit = writer.write
        framer = Framer()
        while data := await reader.read(256):
            for packet in framer.feed(data):
                self.thermo.receive(packet)

    def drop_connection(self) -> None:
        """Close the client connection, like an EW11 restarting its TCP server."""
        for writer in self._writers:
            writer.close()

    async def stop(self) -> None:
        await self.thermo.stop()
        for writer in self._writers:
            writer.close()
        self._server.close()
        await self._server.wait_closed()
