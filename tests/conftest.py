"""Shared fixtures."""
import pytest

from custom_components.kocom_rs485 import coordinator as coordinator_module

from .fakes import FakeEw11Controller


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/kocom_rs485 in every test."""


@pytest.fixture
def fast_bus(monkeypatch):
    """Test-sized bus timings; behaviour is unchanged."""
    monkeypatch.setattr(
        coordinator_module,
        "TRANSPORT_OPTIONS",
        {"initial_quiet": 0, "connect_timeout": 0.3, "delays": lambda attempt: 0.05},
    )
    monkeypatch.setattr(
        coordinator_module, "MASTER_OPTIONS", {"ack_timeout": 0.05, "report_timeout": 0.2, "request_gap": 0.05}
    )
    monkeypatch.setattr(coordinator_module, "CONNECT_TIMEOUT", 0.3)


@pytest.fixture
async def controller():
    fakes: list[FakeEw11Controller] = []

    async def start(rooms: dict[int, str]) -> FakeEw11Controller:
        fake = FakeEw11Controller(rooms)
        await fake.start()
        fakes.append(fake)
        return fake

    yield start
    for fake in fakes:
        await fake.stop()
