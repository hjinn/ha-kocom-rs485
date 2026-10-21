"""Tests for the heater (climate) entities, through Home Assistant services."""
import pytest
from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_HVAC_MODE,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_PRESET_MODE,
    ATTR_TARGET_TEMP_STEP,
    DOMAIN as CLIMATE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    ATTR_TEMPERATURE,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.kocom_rs485.protocol import Cmd, Kind, thermo

from .helpers import eventually, setup_entry

pytestmark = pytest.mark.usefixtures("socket_enabled", "fast_bus")

LIVING, BEDROOM, ROOM1, ROOM2 = (
    "climate.heater_livingroom",
    "climate.heater_bedroom",
    "climate.heater_room1",
    "climate.heater_room2",
)


async def test_one_heater_per_room_showing_off_heat_and_away(hass: HomeAssistant, controller):
    fake = await controller(
        {0: "1100180019000000", 1: "11010a001a000000", 3: "00010a0019000000"}
    )  # heat 24 / away / off
    entry = await setup_entry(hass, fake.port, [0, 1, 3])

    living = hass.states.get(LIVING)
    assert living.state == HVACMode.HEAT
    assert living.attributes[ATTR_TEMPERATURE] == 24
    assert living.attributes[ATTR_CURRENT_TEMPERATURE] == 25
    assert living.attributes[ATTR_PRESET_MODE] == "none"
    assert living.attributes[ATTR_MIN_TEMP] == 5
    assert living.attributes[ATTR_MAX_TEMP] == 40
    assert living.attributes[ATTR_TARGET_TEMP_STEP] == 1
    assert living.attributes[ATTR_FRIENDLY_NAME] == "Heater Living room"

    bedroom = hass.states.get(BEDROOM)
    assert bedroom.state == HVACMode.HEAT
    assert bedroom.attributes[ATTR_PRESET_MODE] == "away"
    assert bedroom.attributes[ATTR_TEMPERATURE] is None
    assert bedroom.attributes[ATTR_CURRENT_TEMPERATURE] == 26

    room2 = hass.states.get(ROOM2)
    assert room2.state == HVACMode.OFF
    assert room2.attributes[ATTR_TEMPERATURE] is None

    assert hass.states.get(ROOM1) is None  # not configured
    await hass.config_entries.async_unload(entry.entry_id)


def sent_values(fake, room: int) -> list[str]:
    return [
        p.value.hex() for p in fake.thermo.sent
        if p.kind is Kind.SEND and p.cmd == Cmd.STATE and p.seq == 1 and p.dest == thermo(room)
    ]


async def test_set_temperature_heats_at_that_temperature_even_from_off(hass: HomeAssistant, controller):
    fake = await controller({3: "00010a0019000000"})  # off
    entry = await setup_entry(hass, fake.port, [3])

    await hass.services.async_call(
        CLIMATE, SERVICE_SET_TEMPERATURE, {ATTR_ENTITY_ID: ROOM2, ATTR_TEMPERATURE: 22}, blocking=True
    )

    assert sent_values(fake, 3) == ["1100160000000000"]
    state = hass.states.get(ROOM2)
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_TEMPERATURE] == 22
    await hass.config_entries.async_unload(entry.entry_id)


async def test_hvac_mode_off_then_heat_returns_to_last_setpoint(hass: HomeAssistant, controller):
    fake = await controller({0: "1100180019000000"})  # heat 24
    entry = await setup_entry(hass, fake.port, [0])

    await hass.services.async_call(
        CLIMATE, SERVICE_SET_HVAC_MODE, {ATTR_ENTITY_ID: LIVING, ATTR_HVAC_MODE: HVACMode.OFF}, blocking=True
    )
    assert hass.states.get(LIVING).state == HVACMode.OFF

    await hass.services.async_call(
        CLIMATE, SERVICE_SET_HVAC_MODE, {ATTR_ENTITY_ID: LIVING, ATTR_HVAC_MODE: HVACMode.HEAT}, blocking=True
    )
    state = hass.states.get(LIVING)
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_TEMPERATURE] == 24
    assert sent_values(fake, 0) == ["0100180000000000", "1100180000000000"]
    await hass.config_entries.async_unload(entry.entry_id)


async def test_away_preset_on_and_off(hass: HomeAssistant, controller):
    fake = await controller({0: "1100180019000000"})  # heat 24
    entry = await setup_entry(hass, fake.port, [0])

    await hass.services.async_call(
        CLIMATE, SERVICE_SET_PRESET_MODE, {ATTR_ENTITY_ID: LIVING, ATTR_PRESET_MODE: "away"}, blocking=True
    )
    assert hass.states.get(LIVING).attributes[ATTR_PRESET_MODE] == "away"

    await hass.services.async_call(
        CLIMATE, SERVICE_SET_PRESET_MODE, {ATTR_ENTITY_ID: LIVING, ATTR_PRESET_MODE: "none"}, blocking=True
    )
    state = hass.states.get(LIVING)
    assert state.attributes[ATTR_PRESET_MODE] == "none"
    assert state.attributes[ATTR_TEMPERATURE] == 24
    assert sent_values(fake, 0) == ["11010a0000000000", "1100180000000000"]
    await hass.config_entries.async_unload(entry.entry_id)


async def test_thermostat_change_and_connection_loss_show_on_the_entity(hass: HomeAssistant, controller):
    fake = await controller({0: "1100180019000000"})
    entry = await setup_entry(hass, fake.port, [0])

    fake.thermo.rooms[0] = bytes.fromhex("11010a0019000000")
    await fake.thermo.report(0)  # away pressed on the thermostat
    await eventually(lambda: hass.states.get(LIVING).attributes.get(ATTR_PRESET_MODE) == "away")

    fake.drop_connection()
    await eventually(lambda: hass.states.get(LIVING).state == STATE_UNAVAILABLE)
    await eventually(lambda: hass.states.get(LIVING).state == HVACMode.HEAT)  # reconnected
    await hass.config_entries.async_unload(entry.entry_id)


async def test_failed_command_raises_error_from_the_service(hass: HomeAssistant, controller):
    fake = await controller({0: "1100180019000000"})
    entry = await setup_entry(hass, fake.port, [0])
    del fake.thermo.rooms[0]  # the room stops answering

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            CLIMATE, SERVICE_SET_TEMPERATURE, {ATTR_ENTITY_ID: LIVING, ATTR_TEMPERATURE: 22}, blocking=True
        )

    assert err.value.translation_key == "command_failed"
    assert str(err.value) == "Living room did not respond to the command"  # HA drops the final "."
    await hass.config_entries.async_unload(entry.entry_id)


async def test_names_in_korean(hass: HomeAssistant, controller):
    hass.config.language = "ko"
    fake = await controller({0: "1100180019000000", 1: "11010a001a000000"})
    entry = await setup_entry(hass, fake.port, [0, 1])

    assert hass.states.get(LIVING).attributes[ATTR_FRIENDLY_NAME] == "난방 거실"
    assert hass.states.get(BEDROOM).attributes[ATTR_FRIENDLY_NAME] == "난방 안방"
    await hass.config_entries.async_unload(entry.entry_id)
