#!/usr/bin/env python3
"""Kocom RS485 active probe: acts as the Master (0100) and talks to thermos.

Unlike capture.py this WRITES to the bus. Every packet sent and received is
logged so the real request/ack/state/ack flow can be observed.

Usage:
    python3 probe.py HOST [-p PORT] [--ack] [--listen SEC] [-o FILE] ACTION ...

Actions:
    scan                 query rooms 0..3 one by one (read-only, no state change)
    query ROOM           query one room (read-only)
    heat ROOM TEMP       turn heating on at TEMP ℃   (changes boiler state)
    off ROOM TEMP        turn heating off, keeping TEMP (changes boiler state)
    away ROOM            switch to away (11 01 0a, as the thermostat reports it)

ROOM is the thermo sub id: 0 livingroom, 1 bedroom, 2 room1, 3 room2.
--ack makes the probe acknowledge state reports sent by a thermo to the
Master, as a real wallpad would (see docs/protocol.md).
"""
from __future__ import annotations

import argparse
import socket
import threading
import time

from capture import HEADER, TRAILER, Framer, Logger, checksum, describe

MASTER = "0100"
THERMO = "36"
SEND, ACK = "30b", "30d"
SEQS = "cdef"
CMD_STATE, CMD_QUERY = "00", "3a"

WRITE_GAP = 0.03  # wait after the last received byte before writing
ACK_TIMEOUT = 1.5


def build(type_: str, seq: str, dest: str, src: str, cmd: str, value: str) -> bytes:
    body = bytes.fromhex(type_ + seq + "00" + dest + src + cmd + value)
    return HEADER + body + bytes([checksum(body)]) + TRAILER


class Probe:
    def __init__(self, host: str, port: int, log: Logger, auto_ack: bool) -> None:
        self._sock = socket.create_connection((host, port), timeout=10)
        self._sock.settimeout(None)
        self._log = log
        self._auto_ack = auto_ack
        self._write_lock = threading.Lock()
        self._last_read = 0.0
        self._expected_ack: bytes | None = None
        self._ack_event = threading.Event()
        log.line("INFO", f"connected to {host}:{port} (auto-ack={'on' if auto_ack else 'off'})")
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self) -> None:
        framer = Framer()
        while True:
            data = self._sock.recv(256)
            if not data:
                self._log.line("ERROR", "closed by peer")
                return
            self._last_read = time.monotonic()
            for kind, chunk in framer.feed(data):
                if kind == "garbage":
                    self._log.line("GARBAGE", chunk.hex())
                    continue
                self._log.line("RECV", f"{chunk.hex()}  {describe(chunk)}")
                self._on_packet(chunk)

    def _on_packet(self, packet: bytes) -> None:
        h = packet.hex()
        if self._expected_ack is not None and packet[2:18] == self._expected_ack:
            self._ack_event.set()
        # a thermo reporting to the Master expects an ack back
        if self._auto_ack and h[4:7] == SEND and h[10:14] == MASTER and h[14:16] == THERMO:
            seq, dest, src, cmd, value = h[7], h[10:14], h[14:18], h[18:20], h[20:36]
            self._write(build(ACK, seq, src, dest, cmd, value), "ACK")

    def _write(self, packet: bytes, kind: str) -> None:
        with self._write_lock:
            if self._last_read == 0.0:
                time.sleep(1)
            wait = WRITE_GAP - (time.monotonic() - self._last_read)
            if wait > 0:
                time.sleep(wait)
            self._sock.sendall(packet)
        self._log.line(kind, f"{packet.hex()}  {describe(packet)}")

    def request(self, room: int, cmd: str, value: str) -> bool:
        """Send with seq c→d→e→f until the thermo acks. Returns True on ack."""
        dest = f"{THERMO}{room:02x}"
        for seq in SEQS:
            packet = build(SEND, seq, dest, MASTER, cmd, value)
            # expected ack: same seq, addresses swapped, same cmd/value
            self._expected_ack = bytes.fromhex(ACK + seq + "00" + MASTER + dest + cmd + value)
            self._ack_event.clear()
            self._write(packet, "SEND")
            if self._ack_event.wait(ACK_TIMEOUT):
                self._log.line("INFO", f"ack received for seq={seq}")
                self._expected_ack = None
                return True
            self._log.line("INFO", f"no ack for seq={seq}")
        self._expected_ack = None
        self._log.line("INFO", f"room {room}: no ack after {len(SEQS)} tries")
        return False


def value_for(mode: str, temp: int | None) -> str:
    if mode == "away":
        return "11010a" + "00" * 5  # same bytes the thermostat reports when away
    return {"heat": "11", "off": "01"}[mode] + "00" + f"{temp:02x}" + "00" * 5


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("host", help="EW11 IP address")
    parser.add_argument("-p", "--port", type=int, default=8899, help="EW11 TCP port (default 8899)")
    parser.add_argument("--ack", action="store_true", help="acknowledge thermo state reports as the Master")
    parser.add_argument("--listen", type=float, default=10, help="seconds to keep listening after the action (default 10)")
    parser.add_argument("-o", "--output", help="append log lines to this file")
    parser.add_argument("action", choices=["scan", "query", "heat", "off", "away"])
    parser.add_argument("room", type=int, nargs="?", choices=range(4))
    parser.add_argument("temp", type=int, nargs="?")
    args = parser.parse_args()

    if args.action != "scan" and args.room is None:
        parser.error(f"{args.action} needs ROOM")
    if args.action in ("heat", "off") and args.temp is None:
        parser.error(f"{args.action} needs TEMP")
    if args.temp is not None and not 5 <= args.temp <= 40:
        parser.error("TEMP must be 5..40")

    log = Logger(args.output)
    probe = Probe(args.host, args.port, log, args.ack)
    log.line("NOTE", f"# probe {args.action} room={args.room} temp={args.temp} ack={args.ack}")

    time.sleep(2)  # observe the bus before talking
    if args.action == "scan":
        for room in range(4):
            probe.request(room, CMD_QUERY, "00" * 8)
            time.sleep(1)
    elif args.action == "query":
        probe.request(args.room, CMD_QUERY, "00" * 8)
    else:
        probe.request(args.room, CMD_STATE, value_for(args.action, args.temp))

    time.sleep(args.listen)
    log.line("INFO", "done")


if __name__ == "__main__":
    main()
