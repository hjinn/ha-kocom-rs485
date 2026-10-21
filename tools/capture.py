#!/usr/bin/env python3
"""Kocom RS485 bus capture tool (read-only).

Connects to an EW11 TCP server, reassembles Kocom packets and logs them
with a decoded summary. It never writes to the socket, so it cannot
disturb the bus.

Usage:
    python3 capture.py <EW11_IP> 8899 [-o capture.log] [--thermo-only]

While running, type a note and press Enter to insert a marker line
(e.g. "거실 24도로 변경") so captured packets can be matched to actions.
"""
from __future__ import annotations

import argparse
import datetime as dt
import socket
import sys
import threading
import time

HEADER = bytes.fromhex("aa55")
TRAILER = bytes.fromhex("0d0d")
PACKET_SIZE = 21
CHECKSUM_POS = 18  # index of the checksum byte

TYPE = {"30b": "send", "30d": "ack"}
DEVICE = {
    "01": "wallpad", "0e": "light", "2c": "gas", "36": "thermo",
    "3b": "plug", "44": "elevator", "48": "fan",
}
CMD = {"00": "state", "01": "on", "02": "off", "3a": "query"}
ROOM = {0: "livingroom", 1: "bedroom", 2: "room1", 3: "room2"}

RECONNECT_DELAYS = (5, 10, 30, 60)


def checksum(body: bytes) -> int:
    """Sum of the bytes after the header, mod 256."""
    return sum(body) % 256


def is_valid(packet: bytes) -> bool:
    return (
        len(packet) == PACKET_SIZE
        and packet.startswith(HEADER)
        and packet.endswith(TRAILER)
        and checksum(packet[len(HEADER):CHECKSUM_POS]) == packet[CHECKSUM_POS]
    )


class Framer:
    """Reassembles packets from an arbitrarily chunked byte stream."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[tuple[str, bytes]]:
        """Return a list of ("packet" | "garbage", bytes) in stream order."""
        self._buf += data
        out: list[tuple[str, bytes]] = []
        while True:
            start = self._buf.find(HEADER)
            if start < 0:
                # keep a trailing 0xaa: it may be the first half of a header
                keep = 1 if self._buf.endswith(HEADER[:1]) else 0
                if len(self._buf) > keep:
                    out.append(("garbage", bytes(self._buf[: len(self._buf) - keep])))
                    del self._buf[: len(self._buf) - keep]
                return out
            if start > 0:
                out.append(("garbage", bytes(self._buf[:start])))
                del self._buf[:start]
            if len(self._buf) < PACKET_SIZE:
                return out
            candidate = bytes(self._buf[:PACKET_SIZE])
            if is_valid(candidate):
                out.append(("packet", candidate))
                del self._buf[:PACKET_SIZE]
            else:
                # resync on the next header after this one
                nxt = self._buf.find(HEADER, 1)
                cut = nxt if 0 < nxt < PACKET_SIZE else PACKET_SIZE
                out.append(("garbage", bytes(self._buf[:cut])))
                del self._buf[:cut]


def describe(packet: bytes) -> str:
    h = packet.hex()
    type_ = TYPE.get(h[4:7], h[4:7])
    seq = h[7:8]
    dest, src, cmd, value = h[10:14], h[14:18], h[18:20], h[20:36]

    def addr(a: str) -> str:
        return f"{DEVICE.get(a[:2], a[:2])}{int(a[2:4], 16)}"

    text = f"{type_:<4} seq={seq} {addr(src)}->{addr(dest)} cmd={CMD.get(cmd, cmd)} value={value}"

    thermo = dest if dest[:2] == "36" else src if src[:2] == "36" else None
    if thermo and cmd == "00":
        room = ROOM.get(int(thermo[2:4], 16), thermo[2:4])
        mode = {"11": "heat", "01": "off"}.get(value[0:2], value[0:2])
        away = "away" if value[2:4] == "01" else "home"
        text += (
            f" | {room} mode={mode} {away}"
            f" set={int(value[4:6], 16)} cur={int(value[8:10], 16)}"
        )
    return text


class Logger:
    def __init__(self, path: str | None) -> None:
        self._file = open(path, "a", encoding="utf-8") if path else None
        self._lock = threading.Lock()

    def line(self, kind: str, text: str) -> None:
        stamp = dt.datetime.now().isoformat(timespec="milliseconds")
        row = f"{stamp} {kind:<7} {text}"
        with self._lock:
            print(row, flush=True)
            if self._file:
                self._file.write(row + "\n")
                self._file.flush()


def read_notes(log: Logger) -> None:
    for raw in sys.stdin:
        note = raw.strip()
        if note:
            log.line("NOTE", f"# {note}")


def capture(host: str, port: int, log: Logger, thermo_only: bool) -> None:
    attempt = 0
    while True:
        try:
            with socket.create_connection((host, port), timeout=10) as sock:
                sock.settimeout(None)
                log.line("INFO", f"connected to {host}:{port}")
                attempt = 0
                framer = Framer()
                while True:
                    data = sock.recv(256)
                    if not data:
                        raise ConnectionError("closed by peer")
                    for kind, chunk in framer.feed(data):
                        if kind == "garbage":
                            log.line("GARBAGE", chunk.hex())
                            continue
                        if thermo_only and b"\x36" not in (chunk[5:6] + chunk[7:8]):
                            continue
                        log.line("PACKET", f"{chunk.hex()}  {describe(chunk)}")
        except OSError as err:
            delay = RECONNECT_DELAYS[min(attempt, len(RECONNECT_DELAYS) - 1)]
            attempt += 1
            log.line("ERROR", f"{err}; reconnecting in {delay}s")
            time.sleep(delay)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("host", help="EW11 IP address")
    parser.add_argument("port", type=int, nargs="?", default=8899, help="EW11 TCP port (default 8899)")
    parser.add_argument("-o", "--output", help="append log lines to this file")
    parser.add_argument("--thermo-only", action="store_true", help="only log packets to/from a thermo")
    args = parser.parse_args()

    log = Logger(args.output)
    threading.Thread(target=read_notes, args=(log,), daemon=True).start()
    try:
        capture(args.host, args.port, log, args.thermo_only)
    except KeyboardInterrupt:
        log.line("INFO", "stopped")


if __name__ == "__main__":
    main()
