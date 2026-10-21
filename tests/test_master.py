"""Tests for the Master request/ack/report engine, against a fake thermo."""
import asyncio

import pytest

from custom_components.kocom_rs485.master import Master, NoResponse
from custom_components.kocom_rs485.protocol import (
    MASTER,
    Cmd,
    Kind,
    Packet,
    ThermoMode,
    ThermoState,
    thermo,
)

from .fakes import STEP, FakeThermo

FAST = {"ack_timeout": 0.05, "report_timeout": 0.2}


@pytest.fixture
async def make_master():
    fakes: list[FakeThermo] = []

    def make(
        rooms: dict[int, str], reports: list | None = None, deaf_for: int = 0, **kwargs
    ) -> tuple[Master, FakeThermo]:
        fake = FakeThermo(rooms, deaf_for)
        master = Master(
            fake.write,
            on_report=lambda room, state: reports.append((room, state)) if reports is not None else None,
            **{**FAST, **kwargs},
        )
        fake.emit = master.feed
        fakes.append(fake)
        return master, fake

    yield make
    for fake in fakes:
        await fake.stop()
    await asyncio.sleep(0)  # let the Master's last ack writes finish


async def test_query_returns_reported_state_and_acks_the_report(make_master):
    master, fake = make_master({0: "1100180019000000"})

    state = await master.query(0)

    assert state == ThermoState(ThermoMode.HEAT, target_temp=24, current_temp=25)
    assert fake.sent[0] == Packet(Kind.SEND, 1, thermo(0), MASTER, Cmd.QUERY, bytes(8))
    await asyncio.sleep(STEP * 2)
    assert len(fake.acks_to(0)) == 1


@pytest.mark.parametrize(
    ("start", "mode", "target_temp", "sent_value", "expected"),
    [
        pytest.param(
            "00010a0019000000", ThermoMode.HEAT, 24, "1100180000000000",
            ThermoState(ThermoMode.HEAT, target_temp=24, current_temp=25), id="off -> heat 24",
        ),
        pytest.param(
            "1100180019000000", ThermoMode.AWAY, None, "11010a0000000000",
            ThermoState(ThermoMode.AWAY, target_temp=None, current_temp=25), id="heat -> away",
        ),
        pytest.param(
            "1100180019000000", ThermoMode.OFF, 24, "0100180000000000",
            ThermoState(ThermoMode.OFF, target_temp=None, current_temp=25), id="heat -> off",
        ),
    ],
)
async def test_command_sends_value_and_returns_reported_state(
    make_master, start, mode, target_temp, sent_value, expected
):
    master, fake = make_master({0: start})

    state = await master.command(0, mode, target_temp)

    assert state == expected
    assert fake.sent[0] == Packet(Kind.SEND, 1, thermo(0), MASTER, Cmd.STATE, bytes.fromhex(sent_value))


async def test_retries_with_next_seq_then_gives_up(make_master):
    master, fake = make_master({0: "1100180019000000"})  # room 1 does not exist

    with pytest.raises(NoResponse):
        await master.query(1)

    assert [(p.seq, p.dest) for p in fake.sent] == [(seq, thermo(1)) for seq in (1, 2, 3, 4)]


async def test_retry_succeeds_when_thermo_answers_second_try(make_master):
    master, fake = make_master({0: "1100180019000000"}, deaf_for=1)

    state = await master.query(0)

    assert state.target_temp == 24
    assert [p.seq for p in fake.sent if p.kind is Kind.SEND] == [1, 2]


async def test_spontaneous_report_is_acked_and_passed_on(make_master):
    reports = []
    master, fake = make_master({2: "11010a0019000000"}, reports)

    await fake.report(2)  # e.g. someone pressed away on the room thermostat

    assert reports == [(2, ThermoState(ThermoMode.AWAY, target_temp=None, current_temp=25))]
    assert len(fake.acks_to(2)) == 1


async def test_repeated_report_is_acked_every_time(make_master):
    master, fake = make_master({2: "11010a0019000000"})
    fake.lose_acks = True

    await fake.report(2)
    await asyncio.sleep(STEP)

    assert [p.seq for p in fake.acks_to(2)] == [1, 2, 3]


async def test_other_room_report_during_request_is_acked_first(make_master):
    reports = []
    master, fake = make_master(
        {0: "1100180019000000", 2: "11010a0019000000"}, reports, deaf_for=1
    )

    pending = asyncio.create_task(master.query(0))  # first try is ignored
    await asyncio.sleep(STEP)
    await fake.report(2)  # arrives while the Master waits for room 0's ack
    state = await pending

    assert state == ThermoState(ThermoMode.HEAT, target_temp=24, current_temp=25)
    ack_to_2 = fake.sent.index(fake.acks_to(2)[0])
    retry_to_0 = next(i for i, p in enumerate(fake.sent) if p.kind is Kind.SEND and p.seq == 2)
    assert ack_to_2 < retry_to_0
    assert (2, ThermoState(ThermoMode.AWAY, None, 25)) in reports


async def test_concurrent_requests_go_out_one_at_a_time(make_master):
    master, fake = make_master({0: "1100180019000000", 1: "11010a001a000000"})

    first, second = await asyncio.gather(master.query(0), master.query(1))

    assert first.target_temp == 24
    assert second.mode is ThermoMode.AWAY
    requests = [p for p in fake.sent if p.kind is Kind.SEND]
    assert [p.dest for p in requests] == [thermo(0), thermo(1)]
    # room 1's request only after room 0's report was acked
    assert fake.sent.index(requests[1]) > fake.sent.index(fake.acks_to(0)[0])


async def test_connection_lost_fails_waiting_request_at_once(make_master):
    master, fake = make_master({}, ack_timeout=5, report_timeout=5)  # nobody answers

    pending = asyncio.create_task(master.query(0))
    await asyncio.sleep(STEP)
    master.connection_lost()

    with pytest.raises(NoResponse):
        await asyncio.wait_for(pending, 0.5)


async def test_request_without_connection_raises_no_response(make_master):
    master, fake = make_master({0: "1100180019000000"})
    fake.connected = False

    with pytest.raises(NoResponse):
        await master.query(0)


async def test_unknown_report_value_is_acked_logged_and_skipped(make_master, caplog):
    reports = []
    master, fake = make_master({0: "2100180019000000", 1: "11010a001a000000"}, reports)
    odd = Packet(Kind.SEND, 1, MASTER, thermo(0), Cmd.STATE, fake.rooms[0])
    normal = Packet(Kind.SEND, 1, MASTER, thermo(1), Cmd.STATE, fake.rooms[1])

    master.feed(odd.to_bytes() + normal.to_bytes())  # same chunk
    await asyncio.sleep(STEP)

    assert reports == [(1, ThermoState(ThermoMode.AWAY, None, 26))]
    assert len(fake.acks_to(0)) == 1
    assert "2100180019000000" in caplog.text


async def test_close_waits_until_pending_acks_are_written(make_master):
    master, fake = make_master({0: "00010a0019000000"})
    fake.write_delay = 0.05

    await master.command(0, ThermoMode.HEAT, 24)  # returns as soon as the report arrives
    await master.close()

    # the report's ack must be on the bus before the caller can drop the
    # connection, or the thermo rolls the command back (ADR-0014); the slow
    # write means the thermo resent its report meanwhile, all get acked
    assert fake.acks_to(0)


async def test_stale_report_before_ack_is_not_taken_as_the_result(make_master):
    master, fake = make_master({0: "00010a0019000000"}, deaf_for=1)  # off; first try lost

    pending = asyncio.create_task(master.command(0, ThermoMode.HEAT, 24))
    await asyncio.sleep(STEP)
    # a resend of an earlier "off" report arrives before the thermo acked the command
    stale = Packet(Kind.SEND, 2, MASTER, thermo(0), Cmd.STATE, bytes.fromhex("00010a0019000000"))
    master.feed(stale.to_bytes())
    state = await pending

    assert state == ThermoState(ThermoMode.HEAT, target_temp=24, current_temp=25)
