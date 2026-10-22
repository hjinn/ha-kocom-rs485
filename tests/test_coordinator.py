"""Tests for the coordinator, set up through Home Assistant against a fake EW11."""
import asyncio
import logging
import re

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.exceptions import HomeAssistantError
from datetime import timedelta

from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.kocom_rs485.protocol import Cmd, Kind, ThermoMode, ThermoState, thermo

from .fakes import FakeEw11Controller
from .helpers import eventually, setup_entry

pytestmark = pytest.mark.usefixtures("socket_enabled", "fast_bus")


def queried_rooms(fake: FakeEw11Controller, since: int = 0) -> list[int]:
    return [
        p.dest.sub
        for p in fake.thermo.sent[since:]
        if p.kind is Kind.SEND and p.cmd == Cmd.QUERY and p.seq == 1
    ]


async def advance(hass: HomeAssistant, freezer, seconds: float) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_setup_queries_rooms_and_fills_state(hass: HomeAssistant, controller):
    fake = await controller({0: "1100180019000000", 1: "11010a001a000000"})

    entry = await setup_entry(hass, fake.port, [0, 1])

    assert entry.state is ConfigEntryState.LOADED
    coordinator = entry.runtime_data
    assert coordinator.data[0].state == ThermoState(ThermoMode.HEAT, 24, 25)
    assert coordinator.data[1].state == ThermoState(ThermoMode.AWAY, None, 26)
    assert coordinator.data[0].available and coordinator.data[1].available
    await hass.config_entries.async_unload(entry.entry_id)


async def test_setup_is_retried_later_when_ew11_is_unreachable(hass: HomeAssistant, controller):
    fake = await controller({})
    await fake.stop()

    entry = await setup_entry(hass, fake.port, [0])

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_spontaneous_report_updates_room_and_notifies(hass: HomeAssistant, controller):
    fake = await controller({0: "1100180019000000", 1: "1100170019000000"})
    entry = await setup_entry(hass, fake.port, [0, 1])
    coordinator = entry.runtime_data
    updates = []
    coordinator.async_add_listener(lambda: updates.append(coordinator.data[1].state))

    fake.thermo.rooms[1] = bytes.fromhex("11010a0019000000")  # away pressed on the thermostat
    await fake.thermo.report(1)

    await eventually(lambda: updates and updates[-1] == ThermoState(ThermoMode.AWAY, None, 25))
    await hass.config_entries.async_unload(entry.entry_id)


# the fake EW11 is real TCP with real timeouts, so the clock must keep running;
# tick=True still lets the test jump ahead
@pytest.mark.freeze_time("2026-10-22 12:00:00", tick=True)
async def test_polls_on_schedule_and_skips_rooms_that_just_reported(
    hass: HomeAssistant, controller, freezer
):
    fake = await controller({0: "1100180019000000", 1: "1100170019000000"})
    entry = await setup_entry(hass, fake.port, [0, 1])
    coordinator = entry.runtime_data
    # polling only runs while something listens; climate entities will
    unsubscribe = coordinator.async_add_listener(lambda: None)
    assert queried_rooms(fake) == [0, 1]  # first refresh

    await advance(hass, freezer, 30)
    fake.thermo.rooms[0] = bytes.fromhex("1100170019000000")  # 24 -> 23 on the thermostat
    await fake.thermo.report(0)  # room 0 is fresh now
    await eventually(lambda: fake.thermo.acks_to(0))
    mark = len(fake.thermo.sent)

    await advance(hass, freezer, 31)  # 61s after setup: next poll is due
    await eventually(lambda: 1 in queried_rooms(fake, mark))  # rooms are polled in order

    assert queried_rooms(fake, mark) == [1]
    assert coordinator.data[1].available
    unsubscribe()
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.freeze_time("2026-10-22 12:00:00", tick=True)
async def test_room_unavailable_after_two_missed_polls_until_it_reports(
    hass: HomeAssistant, controller, freezer
):
    fake = await controller({0: "1100180019000000", 1: "1100170019000000"})
    entry = await setup_entry(hass, fake.port, [0, 1])
    coordinator = entry.runtime_data
    unsubscribe = coordinator.async_add_listener(lambda: None)
    room1 = fake.thermo.rooms.pop(1)  # room 1 stops answering

    await advance(hass, freezer, 61)
    await eventually(lambda: coordinator.data[1].misses == 1)
    assert coordinator.data[1].available  # one miss can be a collision

    await advance(hass, freezer, 61)
    await eventually(lambda: coordinator.data[1].misses == 2)
    assert not coordinator.data[1].available
    assert coordinator.data[0].available

    fake.thermo.rooms[1] = room1
    await fake.thermo.report(1)
    await eventually(lambda: coordinator.data[1].available)
    assert coordinator.data[1].misses == 0
    unsubscribe()
    await hass.config_entries.async_unload(entry.entry_id)


async def test_connection_loss_marks_all_unavailable_and_reconnect_requeries_all(
    hass: HomeAssistant, controller
):
    fake = await controller({0: "1100180019000000", 1: "1100170019000000"})
    entry = await setup_entry(hass, fake.port, [0, 1])
    coordinator = entry.runtime_data
    unsubscribe = coordinator.async_add_listener(lambda: None)
    fake.thermo.rooms[0] = bytes.fromhex("11010a0019000000")
    await fake.thermo.report(0)  # room 0 is fresh: a normal poll would skip it
    await eventually(lambda: coordinator.data[0].state.mode is ThermoMode.AWAY)
    mark = len(fake.thermo.sent)

    fake.drop_connection()  # e.g. the EW11 restarts its TCP server

    await eventually(lambda: not any(room.available for room in coordinator.data.values()))
    await eventually(lambda: all(room.available for room in coordinator.data.values()))
    assert queried_rooms(fake, mark) == [0, 1]  # everything, no skipping
    unsubscribe()
    await hass.config_entries.async_unload(entry.entry_id)


async def test_command_updates_room_and_notifies(hass: HomeAssistant, controller):
    fake = await controller({0: "00010a0019000000"})  # off
    entry = await setup_entry(hass, fake.port, [0])
    coordinator = entry.runtime_data
    updates = []
    coordinator.async_add_listener(lambda: updates.append(coordinator.data[0].state))

    await coordinator.async_command(0, ThermoMode.HEAT, 25)

    assert coordinator.data[0].state == ThermoState(ThermoMode.HEAT, 25, 25)
    assert updates[-1] == ThermoState(ThermoMode.HEAT, 25, 25)
    await hass.config_entries.async_unload(entry.entry_id)


async def test_command_without_answer_raises_home_assistant_error(hass: HomeAssistant, controller):
    fake = await controller({0: "1100180019000000", 1: "1100170019000000"})
    entry = await setup_entry(hass, fake.port, [0, 1])
    coordinator = entry.runtime_data
    del fake.thermo.rooms[1]  # room 1 went silent

    with pytest.raises(HomeAssistantError):
        await coordinator.async_command(1, ThermoMode.HEAT, 25)
    await hass.config_entries.async_unload(entry.entry_id)


def last_command_value(fake: FakeEw11Controller, room: int) -> str:
    return [
        p.value.hex() for p in fake.thermo.sent
        if p.kind is Kind.SEND and p.cmd == Cmd.STATE and p.dest == thermo(room)
    ][-1]


async def test_heat_without_temperature_uses_the_last_heating_setpoint(hass: HomeAssistant, controller):
    fake = await controller({0: "1100180019000000", 1: "11010a001a000000"})  # heat 24 / away
    entry = await setup_entry(hass, fake.port, [0, 1])
    coordinator = entry.runtime_data

    await coordinator.async_command(0, ThermoMode.AWAY)
    await coordinator.async_command(0, ThermoMode.HEAT)  # e.g. away preset turned off
    assert coordinator.data[0].state == ThermoState(ThermoMode.HEAT, 24, 25)

    await coordinator.async_command(0, ThermoMode.OFF)
    assert last_command_value(fake, 0) == "0100180000000000"  # off carries 24 too

    await coordinator.async_command(1, ThermoMode.HEAT)  # never seen heating
    assert coordinator.data[1].state == ThermoState(ThermoMode.HEAT, 23, 26)
    await hass.config_entries.async_unload(entry.entry_id)


async def test_options_set_polling_interval_and_reload(hass: HomeAssistant, controller):
    fake = await controller({0: "1100180019000000"})
    entry = await setup_entry(hass, fake.port, [0])

    result = await hass.config_entries.options.async_init(entry.entry_id)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(result["flow_id"], {"scan_interval": 10})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"scan_interval": 120})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"scan_interval": 120}
    assert entry.runtime_data.update_interval == timedelta(seconds=120)  # reloaded
    await hass.config_entries.async_unload(entry.entry_id)


async def test_unload_flushes_acks_and_closes_the_connection(hass: HomeAssistant, controller):
    fake = await controller({0: "00010a0019000000"})
    entry = await setup_entry(hass, fake.port, [0])
    coordinator = entry.runtime_data
    await coordinator.async_command(0, ThermoMode.HEAT, 24)
    acks_before = len(fake.thermo.acks_to(0))

    await hass.config_entries.async_unload(entry.entry_id)

    assert len(fake.thermo.acks_to(0)) > acks_before  # the command's report was acked
    assert not coordinator.transport.connected


def coordinator_logs(caplog, level: int) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if r.name == "custom_components.kocom_rs485.coordinator" and r.levelno == level
    ]


@pytest.mark.freeze_time("2026-10-22 12:00:00", tick=True)
async def test_logs_room_going_unavailable_once_with_reason_and_recovery(
    hass: HomeAssistant, controller, freezer, caplog
):
    caplog.set_level(logging.DEBUG, logger="custom_components.kocom_rs485")
    fake = await controller({0: "1100180019000000", 2: "1100170019000000"})
    entry = await setup_entry(hass, fake.port, [0, 2])
    coordinator = entry.runtime_data
    unsubscribe = coordinator.async_add_listener(lambda: None)
    room2 = fake.thermo.rooms.pop(2)

    for misses in (1, 2, 3):  # the third miss must not warn again
        await advance(hass, freezer, 61)
        await eventually(lambda: coordinator.data[2].misses == misses)

    warnings = coordinator_logs(caplog, logging.WARNING)
    assert warnings == ["room 2 (room1) unavailable after 2 missed polls: room 2 did not ack 4 tries"]

    fake.thermo.rooms[2] = room2
    await fake.thermo.report(2)
    await eventually(lambda: coordinator.data[2].available)
    assert coordinator_logs(caplog, logging.INFO) == ["room 2 (room1) available again"]
    unsubscribe()
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.freeze_time("2026-10-22 12:00:00", tick=True)
async def test_debug_log_per_poll_shows_answer_time_or_miss_reason(
    hass: HomeAssistant, controller, freezer, caplog
):
    caplog.set_level(logging.DEBUG, logger="custom_components.kocom_rs485")
    fake = await controller({0: "1100180019000000", 1: "1100170019000000", 2: "1100170019000000"})
    entry = await setup_entry(hass, fake.port, [0, 1, 2])
    coordinator = entry.runtime_data
    unsubscribe = coordinator.async_add_listener(lambda: None)
    del fake.thermo.rooms[2]
    caplog.clear()

    await advance(hass, freezer, 61)
    await eventually(lambda: coordinator.data[2].misses == 1)

    debug = coordinator_logs(caplog, logging.DEBUG)
    answered = {
        int(m["room"]): (float(m["answer"]), float(m["wait"]))
        for line in debug
        if (m := re.fullmatch(
            r"room (?P<room>\d) \(\w+\) answered in (?P<answer>\d+\.\d\d)s"
            r" \(waited (?P<wait>\d+\.\d\d)s for the controller\)",
            line,
        ))
    }
    assert answered[0][1] == 0  # first of the poll: nothing to wait for
    assert answered[1][1] >= 0.04  # held back after room 0's report (request_gap 0.05)
    assert answered[1][0] < 0.04  # the answer itself is as quick as room 0's
    assert "room 2 (room1) missed poll 1/2: room 2 did not ack 4 tries" in debug
    unsubscribe()
    await hass.config_entries.async_unload(entry.entry_id)


async def test_all_rooms_answer_although_the_controller_is_busy_after_each_report(
    hass: HomeAssistant, controller
):
    # captures/ha.log: polled back to back, rooms 1 and 3 never reported
    fake = await controller({room: "1100180019000000" for room in (0, 1, 2, 3)})
    fake.thermo.busy_after_ack = 0.03

    entry = await setup_entry(hass, fake.port, [0, 1, 2, 3])

    coordinator = entry.runtime_data
    assert {room: data.misses for room, data in coordinator.data.items()} == {0: 0, 1: 0, 2: 0, 3: 0}
    await hass.config_entries.async_unload(entry.entry_id)
