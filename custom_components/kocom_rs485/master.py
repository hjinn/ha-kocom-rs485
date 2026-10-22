"""Master side of the Kocom bus: requests, acks and reports (ADR-0014).

Pure asyncio, no Home Assistant imports. Timings and the message flow are
from the real controller, see docs/protocol.md.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from .protocol import (
    MASTER,
    THERMO_DEVICE,
    Cmd,
    Framer,
    Kind,
    Packet,
    ThermoMode,
    ThermoState,
    UnknownThermoValue,
    thermo,
    thermo_command,
)
from .transport import TransportNotConnected

_LOGGER = logging.getLogger(__name__)

SEQS = (1, 2, 3, 4)


class NoResponse(Exception):
    """The thermo did not ack or report in time."""


class Master:
    def __init__(
        self,
        write: Callable[[bytes], Awaitable[None]],
        on_report: Callable[[int, ThermoState], None],
        *,
        ack_timeout: float = 0.5,
        report_timeout: float = 1.2,
        request_gap: float = 1.0,
    ) -> None:
        self._write = write
        self._on_report = on_report
        self._ack_timeout = ack_timeout
        self._report_timeout = report_timeout
        self._request_gap = request_gap
        self._ready_at = 0.0  # loop time when the thermo takes requests again
        self.last_wait = 0.0  # seconds the last request was held back (ADR-0018)
        self._framer = Framer()
        self._report: asyncio.Future[ThermoState] | None = None
        self._room: int | None = None
        self._expected_ack: Packet | None = None
        self._acked = asyncio.Event()
        self._busy = asyncio.Lock()  # one request on the bus at a time
        self._tasks: set[asyncio.Task] = set()

    def feed(self, data: bytes) -> None:
        for packet in self._framer.feed(data):
            if packet == self._expected_ack:
                self._acked.set()
            elif _is_report(packet):
                self._handle_report(packet)

    def connection_lost(self) -> None:
        """Fail the waiting request now and drop partial bytes of the old connection."""
        self._framer = Framer()
        if self._report is not None and not self._report.done():
            self._report.set_exception(NoResponse("connection to the EW11 lost"))
            self._acked.set()  # wake the ack wait; the report wait then raises

    async def close(self) -> None:
        """Wait until acks already queued are written; call before dropping the connection."""
        while self._tasks:  # a resent report may queue another ack meanwhile
            await asyncio.gather(*self._tasks, return_exceptions=True)

    def _handle_report(self, packet: Packet) -> None:
        self._send_soon(packet.ack())
        self._hold_requests()  # also keeps a request from going out before the ack
        room = packet.src.sub
        # only a report after the thermo acked our request is its answer; one
        # before it is a resend of something older (the real thermo always
        # acks at ~125ms and reports at ~300ms, docs/protocol.md)
        answers_request = (
            self._report is not None
            and not self._report.done()
            and room == self._room
            and self._acked.is_set()
        )
        try:
            state = ThermoState.decode(packet.value)
        except UnknownThermoValue:
            _LOGGER.warning("ignoring report from room %s: unobserved value %s", room, packet.value.hex())
            if answers_request:  # fail now with the reason instead of timing out
                self._report.set_exception(
                    NoResponse(f"room {room} reported unobserved value {packet.value.hex()}")
                )
            return
        self._on_report(room, state)
        if answers_request:
            self._report.set_result(state)

    def _hold_requests(self) -> None:
        # right after a report was acked the controller acks new requests but
        # does not report them (captures/ha.log); give it time, as kocom.py's 1s did
        self._ready_at = asyncio.get_running_loop().time() + self._request_gap

    def _send_soon(self, packet: Packet) -> None:
        task = asyncio.get_running_loop().create_task(self._send_ack(packet))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _send_ack(self, packet: Packet) -> None:
        try:
            await self._write(packet.to_bytes())
            # the controller's busy time starts when it gets our ack
            self._hold_requests()
        except TransportNotConnected:
            _LOGGER.debug("could not ack report from room %s: not connected", packet.dest.sub)

    async def query(self, room: int) -> ThermoState:
        return await self._request(room, Cmd.QUERY, bytes(8))

    async def command(self, room: int, mode: ThermoMode, target_temp: int | None = None) -> ThermoState:
        """Change a room and return the state the thermo reports afterwards.

        The reported state is returned even if it differs from the request.
        """
        return await self._request(room, Cmd.STATE, thermo_command(mode, target_temp))

    async def _request(self, room: int, cmd: int, value: bytes) -> ThermoState:
        async with self._busy:
            return await self._exchange(room, cmd, value)

    async def _exchange(self, room: int, cmd: int, value: bytes) -> ThermoState:
        self._acked.clear()  # still set from the previous exchange otherwise
        self.last_wait = 0.0
        self._room = room
        self._report = asyncio.get_running_loop().create_future()
        try:
            for seq in SEQS:
                # re-check: an ack written meanwhile moves the hold further out
                while (wait := self._ready_at - asyncio.get_running_loop().time()) > 0:
                    self.last_wait += wait
                    await asyncio.sleep(wait)
                request = Packet(Kind.SEND, seq, thermo(room), MASTER, cmd, value)
                self._expected_ack = request.ack()
                self._acked.clear()
                try:
                    await self._write(request.to_bytes())
                except TransportNotConnected as err:
                    raise NoResponse(f"room {room}: {err}") from err
                try:
                    await asyncio.wait_for(self._acked.wait(), self._ack_timeout)
                    break
                except TimeoutError:
                    _LOGGER.debug("no ack from room %s for seq %s", room, seq)
            else:
                raise NoResponse(f"room {room} did not ack {len(SEQS)} tries")
            try:
                return await asyncio.wait_for(self._report, self._report_timeout)
            except TimeoutError:
                raise NoResponse(f"room {room} acked but did not report") from None
        finally:
            self._expected_ack = None
            self._acked.clear()
            self._report = None
            self._room = None


def _is_report(packet: Packet) -> bool:
    return (
        packet.kind is Kind.SEND
        and packet.dest == MASTER
        and packet.src.device == THERMO_DEVICE
        and packet.cmd == Cmd.STATE
    )
