"""Tests for the Kocom RS485 protocol module (docs/protocol.md)."""
import pytest

from custom_components.kocom_rs485.protocol import (
    MASTER,
    Address,
    Cmd,
    Framer,
    InvalidPacket,
    Kind,
    Packet,
    ThermoState,
    thermo_command,
    thermo,
)

# Real packet quoted in the reference implementation: master -> elevator, cmd on.
REAL = bytes.fromhex("aa5530bc0044000100010300000000000000350d0d")


def test_parses_real_packet():
    packet = Packet.from_bytes(REAL)

    assert packet.kind is Kind.SEND
    assert packet.seq == 1
    assert packet.dest == Address(0x44, 0x00)
    assert packet.src == MASTER
    assert packet.cmd == 0x01
    assert packet.value == bytes.fromhex("0300000000000000")


def test_encodes_real_packet():
    packet = Packet(
        kind=Kind.SEND,
        seq=1,
        dest=Address(0x44, 0x00),
        src=MASTER,
        cmd=0x01,
        value=bytes.fromhex("0300000000000000"),
    )

    assert packet.to_bytes() == REAL


def _with_byte(raw: bytes, index: int, value: int) -> bytes:
    changed = bytearray(raw)
    changed[index] = value
    return bytes(changed)


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(_with_byte(REAL, 18, 0x36), id="checksum"),
        pytest.param(_with_byte(REAL, 10, 0x04), id="value changed, checksum stale"),
        pytest.param(_with_byte(REAL, 1, 0x56), id="header"),
        pytest.param(_with_byte(REAL, 20, 0x0A), id="trailer"),
        pytest.param(REAL[:-1], id="too short"),
        pytest.param(REAL + b"\x0d", id="too long"),
        # checksums below recomputed by hand: 0x35 - 0x10, 0x35 - 0x0c
        pytest.param(bytes.fromhex("aa5530ac0044000100010300000000000000250d0d"), id="unknown type 30a"),
        pytest.param(bytes.fromhex("aa5530b00044000100010300000000000000290d0d"), id="seq nibble 0"),
    ],
)
def test_rejects_malformed_packet(raw):
    with pytest.raises(InvalidPacket):
        Packet.from_bytes(raw)


def test_framer_yields_whole_packet():
    assert Framer().feed(REAL) == [Packet.from_bytes(REAL)]


def test_framer_skips_leading_garbage():
    assert Framer().feed(b"\x00\xff\x55" + REAL) == [Packet.from_bytes(REAL)]


def test_framer_keeps_header_split_across_chunks():
    framer = Framer()

    assert framer.feed(b"\x00" + REAL[:1]) == []
    assert framer.feed(REAL[1:]) == [Packet.from_bytes(REAL)]


def test_framer_resyncs_after_truncated_frame():
    assert Framer().feed(REAL[:10] + REAL) == [Packet.from_bytes(REAL)]


def test_framer_reassembles_byte_by_byte():
    framer = Framer()
    received = [p for byte in REAL for p in framer.feed(bytes([byte]))]

    assert received == [Packet.from_bytes(REAL)]


def test_framer_splits_merged_packets():
    assert Framer().feed(REAL + REAL) == [Packet.from_bytes(REAL)] * 2


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(
            "1100180016000000",
            ThermoState(heating=True, away=False, target_temp=24, current_temp=22),
            id="heating 24, room 22",
        ),
        pytest.param(
            "0101140013000000",
            ThermoState(heating=False, away=True, target_temp=20, current_temp=19),
            id="off and away, room 19",
        ),
    ],
)
def test_decodes_thermo_state(value, expected):
    assert ThermoState.decode(bytes.fromhex(value)) == expected


@pytest.mark.parametrize(
    ("heating", "target_temp", "expected"),
    [
        pytest.param(True, 24, "1100180000000000", id="heat at 24"),
        pytest.param(False, 23, "0100170000000000", id="off keeping 23"),
    ],
)
def test_encodes_thermo_command(heating, target_temp, expected):
    assert thermo_command(heating, target_temp) == bytes.fromhex(expected)


def test_ack_of_master_query_comes_from_thermo():
    query = Packet(Kind.SEND, 1, thermo(0), MASTER, Cmd.QUERY, bytes(8))

    assert query.ack() == Packet(
        kind=Kind.ACK,
        seq=1,
        dest=Address(0x01, 0x00),
        src=Address(0x36, 0x00),
        cmd=0x3A,
        value=bytes(8),
    )


def test_ack_of_thermo_report_keeps_seq_and_value():
    report = Packet(Kind.SEND, 2, MASTER, thermo(1), Cmd.STATE, bytes.fromhex("0100140013000000"))

    assert report.ack() == Packet(
        kind=Kind.ACK,
        seq=2,
        dest=Address(0x36, 0x01),
        src=Address(0x01, 0x00),
        cmd=0x00,
        value=bytes.fromhex("0100140013000000"),
    )
