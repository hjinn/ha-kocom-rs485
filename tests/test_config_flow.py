"""Tests for the config flow, with real discovery against a fake EW11 + controller."""
from functools import partial

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.kocom_rs485 as kocom_rs485
from custom_components.kocom_rs485 import config_flow, discovery
from custom_components.kocom_rs485.const import DOMAIN

pytestmark = pytest.mark.usefixtures("socket_enabled")

FAST = {"connect_timeout": 0.3, "initial_quiet": 0, "ack_timeout": 0.05, "report_timeout": 0.2}


@pytest.fixture(autouse=True)
def fast_discovery(monkeypatch):
    """Real discovery over TCP, only with test-sized timeouts."""
    monkeypatch.setattr(config_flow, "discover_rooms", partial(discovery.discover_rooms, **FAST))


@pytest.fixture(autouse=True)
def skip_entry_setup(monkeypatch):
    """The flow is under test here, not what happens after the entry exists."""

    async def setup_entry(hass, entry):
        return True

    monkeypatch.setattr(kocom_rs485, "async_setup_entry", setup_entry)


def defaults(result) -> dict:
    return {str(key): key.default() for key in result["data_schema"].schema}


async def test_discovered_rooms_are_preselected_and_saved(hass: HomeAssistant, controller):
    fake = await controller({0: "1100180019000000", 1: "11010a001a000000", 3: "00010a0019000000"})

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "127.0.0.1", "port": fake.port}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "rooms"
    assert defaults(result)["rooms"] == ["0", "1", "3"]

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"rooms": ["0", "1", "3"]})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Kocom RS485 (127.0.0.1)"
    assert result["data"] == {"host": "127.0.0.1", "port": fake.port, "rooms": [0, 1, 3]}


async def test_no_rooms_found_falls_back_to_manual_choice(hass: HomeAssistant, controller):
    fake = await controller({})  # EW11 reachable, controller silent

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "127.0.0.1", "port": fake.port}
    )
    assert result["step_id"] == "rooms"
    assert defaults(result)["rooms"] == []

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"rooms": ["2", "0"]})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["rooms"] == [0, 2]


async def test_unreachable_ew11_shows_cannot_connect(hass: HomeAssistant, controller):
    fake = await controller({})
    await fake.stop()  # nothing listens on the port any more

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "127.0.0.1", "port": fake.port}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_choosing_no_room_is_an_error(hass: HomeAssistant, controller):
    fake = await controller({0: "1100180019000000"})

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "127.0.0.1", "port": fake.port}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"rooms": []})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "rooms"
    assert result["errors"] == {"base": "no_rooms"}


async def test_same_ew11_twice_aborts_without_touching_the_bus(hass: HomeAssistant, controller):
    fake = await controller({0: "1100180019000000"})
    MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"127.0.0.1:{fake.port}",
        data={"host": "127.0.0.1", "port": fake.port, "rooms": [0]},
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "127.0.0.1", "port": fake.port}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    # the running integration owns the bus; a second master must not query it
    assert fake.thermo.sent == []
