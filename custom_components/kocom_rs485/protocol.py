"""Kocom RS485 protocol: packets, framing and thermo values.

Pure Python, no Home Assistant imports. See docs/protocol.md.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum, IntEnum

HEADER = b"\xaa\x55"
TRAILER = b"\x0d\x0d"
PACKET_SIZE = 21
CHECKSUM_INDEX = 18


class InvalidPacket(ValueError):
    """Raised when bytes are not a well-formed Kocom packet."""


class Kind(Enum):
    SEND = 0x30B
    ACK = 0x30D


@dataclass(frozen=True)
class Address:
    device: int
    sub: int


MASTER = Address(0x01, 0x00)
THERMO_DEVICE = 0x36


def thermo(room: int) -> Address:
    return Address(THERMO_DEVICE, room)


class Cmd(IntEnum):
    STATE = 0x00
    QUERY = 0x3A


SEQ_BASE = 0xB  # seq 1..4 is encoded as the nibble c..f


def _checksum(body: bytes) -> int:
    """Sum of the bytes between header and checksum, mod 256."""
    return sum(body) % 256


@dataclass(frozen=True)
class Packet:
    kind: Kind
    seq: int
    dest: Address
    src: Address
    cmd: int
    value: bytes

    def ack(self) -> Packet:
        """The packet acknowledging this one: same seq, cmd and value, addresses swapped."""
        return replace(self, kind=Kind.ACK, dest=self.src, src=self.dest)

    def to_bytes(self) -> bytes:
        type_seq = (self.kind.value << 4) | (self.seq + SEQ_BASE)
        body = (
            type_seq.to_bytes(2)
            + b"\x00"  # monitor
            + bytes([self.dest.device, self.dest.sub, self.src.device, self.src.sub, self.cmd])
            + self.value
        )
        return HEADER + body + bytes([_checksum(body)]) + TRAILER

    @classmethod
    def from_bytes(cls, raw: bytes) -> Packet:
        if len(raw) != PACKET_SIZE:
            raise InvalidPacket(f"length {len(raw)}, expected {PACKET_SIZE}")
        if not raw.startswith(HEADER) or not raw.endswith(TRAILER):
            raise InvalidPacket(f"bad header or trailer: {raw.hex()}")
        if _checksum(raw[len(HEADER):CHECKSUM_INDEX]) != raw[CHECKSUM_INDEX]:
            raise InvalidPacket(f"bad checksum: {raw.hex()}")
        type_seq = int.from_bytes(raw[2:4])
        try:
            kind = Kind(type_seq >> 4)
        except ValueError:
            raise InvalidPacket(f"unknown type {type_seq >> 4:03x}") from None
        seq = (type_seq & 0xF) - SEQ_BASE
        if not 1 <= seq <= 4:
            raise InvalidPacket(f"bad seq nibble {type_seq & 0xF:x}")
        return cls(
            kind=kind,
            seq=seq,
            dest=Address(raw[5], raw[6]),
            src=Address(raw[7], raw[8]),
            cmd=raw[9],
            value=bytes(raw[10:18]),
        )


class Framer:
    """Reassembles packets from an arbitrarily chunked byte stream."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[Packet]:
        self._buf += data
        packets = []
        while True:
            start = self._buf.find(HEADER)
            if start < 0:
                # a trailing 0xaa may be the first half of the next header
                keep = 1 if self._buf.endswith(HEADER[:1]) else 0
                del self._buf[: len(self._buf) - keep]
                return packets
            del self._buf[:start]
            if len(self._buf) < PACKET_SIZE:
                return packets
            try:
                packets.append(Packet.from_bytes(bytes(self._buf[:PACKET_SIZE])))
                del self._buf[:PACKET_SIZE]
            except InvalidPacket:
                del self._buf[:1]  # drop this header, look for the next one


HEAT = 0x11
OFF = 0x01  # sent to switch off; the controller then reports byte 0 as 0x00
AWAY = 0x01


class UnknownThermoValue(ValueError):
    """Raised for thermo values never observed on the real controller."""


class ThermoMode(Enum):
    OFF = "off"
    HEAT = "heat"
    AWAY = "away"


@dataclass(frozen=True)
class ThermoState:
    mode: ThermoMode
    target_temp: int | None  # only while heating; off/away report a fixed 10
    current_temp: int

    @classmethod
    def decode(cls, value: bytes) -> ThermoState:
        if value[0] not in (0x00, HEAT) or value[1] not in (0x00, AWAY):
            raise UnknownThermoValue(f"unobserved thermo value {value.hex()}")
        if value[0] == 0x00:
            mode = ThermoMode.OFF
        elif value[1] == AWAY:
            mode = ThermoMode.AWAY
        else:
            mode = ThermoMode.HEAT
        return cls(
            mode=mode,
            target_temp=value[2] if mode is ThermoMode.HEAT else None,
            current_temp=value[4],
        )


AWAY_TEMP = 0x0A  # what the controller reports and accepts for away


def thermo_command(mode: ThermoMode, target_temp: int | None = None) -> bytes:
    """Value for a STATE command to a thermo (formats verified on hardware).

    HEAT and OFF carry the target temperature; AWAY uses the fixed away value.
    """
    if mode is ThermoMode.AWAY:
        return bytes([HEAT, AWAY, AWAY_TEMP]) + bytes(5)
    if target_temp is None:
        raise ValueError(f"{mode.value} needs a target temperature")
    return bytes([HEAT if mode is ThermoMode.HEAT else OFF, 0x00, target_temp]) + bytes(5)
