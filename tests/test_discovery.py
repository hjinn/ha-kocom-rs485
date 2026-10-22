"""Tests for room discovery over TCP, against a fake EW11 + controller."""
import pytest

from custom_components.kocom_rs485.discovery import CannotConnect, discover_rooms

pytestmark = pytest.mark.usefixtures("socket_enabled")

FAST = {"initial_quiet": 0, "ack_timeout": 0.05, "report_timeout": 0.2, "request_gap": 0.05}


async def test_finds_the_rooms_that_answer(controller):
    fake = await controller(
        {0: "1100180019000000", 1: "11010a001a000000", 3: "00010a0019000000"}
    )

    assert await discover_rooms("127.0.0.1", fake.port, **FAST) == [0, 1, 3]


async def test_raises_cannot_connect_when_nothing_listens(controller):
    fake = await controller({})
    await fake.stop()  # the port is now closed

    with pytest.raises(CannotConnect):
        await discover_rooms("127.0.0.1", fake.port, connect_timeout=0.3, **FAST)


async def test_finds_every_room_although_the_controller_is_busy_after_each_report(controller):
    fake = await controller({room: "1100180019000000" for room in (0, 1, 2, 3)})
    fake.thermo.busy_after_ack = 0.03

    assert await discover_rooms("127.0.0.1", fake.port, **FAST) == [0, 1, 2, 3]
