"""The two switches in Home Assistant: their entities, commands, and what happens when one doesn't answer."""

from datetime import timedelta

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.netgear_switch.const import DOMAIN
from custom_components.netgear_switch.diagnostics import async_get_config_entry_diagnostics

from .conftest import GS105, GS105_SERIAL, GS308, GS308_SERIAL, PASSWORD, LoginFailedError, PageFetcherConnectionError


async def add(hass: HomeAssistant, host: str, serial: str) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=serial, title=host, data={"host": host, "password": PASSWORD})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
async def gs105(hass: HomeAssistant, fake_switch) -> MockConfigEntry:
    return await add(hass, GS105, GS105_SERIAL)


@pytest.fixture
async def gs308(hass: HomeAssistant, fake_switch) -> MockConfigEntry:
    return await add(hass, GS308, GS308_SERIAL)


def entity_id(hass: HomeAssistant, platform: str, serial: str, key: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{serial}_{key}")


def state(hass: HomeAssistant, platform: str, serial: str, key: str):
    found = entity_id(hass, platform, serial, key)
    assert found, key
    return hass.states.get(found)


async def next_read(hass: HomeAssistant, freezer) -> None:
    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_the_switch_as_a_device(hass: HomeAssistant, gs105) -> None:
    assert gs105.state is ConfigEntryState.LOADED
    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), gs105.entry_id)
    assert device.identifiers == {(DOMAIN, GS105_SERIAL)}
    assert device.name == "Switch01" and device.manufacturer == "NETGEAR" and device.model == "GS105Ev2"
    assert device.serial_number == GS105_SERIAL
    assert device.sw_version == "V1.6.0.15" and device.hw_version == "V1.4.0.5-VB"
    assert device.configuration_url == f"http://{GS105}"


async def test_ports_with_link_speed_and_traffic(hass: HomeAssistant, gs105) -> None:
    link = state(hass, "binary_sensor", GS105_SERIAL, "port_1_link")
    assert link.entity_id == "binary_sensor.switch01_port_1"
    assert link.state == "on"
    # For apps that draw the network: which port of which switch, and its speed
    assert link.attributes["switch_host"] == GS105
    assert link.attributes["port"] == 1
    assert link.attributes["speed_mbps"] == 1000
    assert link.attributes["name"] == "uplink"
    assert link.attributes["enabled"] is True
    empty = state(hass, "binary_sensor", GS105_SERIAL, "port_3_link")
    assert empty.state == "off" and "speed_mbps" not in empty.attributes and "name" not in empty.attributes
    assert [entity_id(hass, "binary_sensor", GS105_SERIAL, f"port_{n}_link") is not None for n in range(1, 7)] == [
        True,
        True,
        True,
        True,
        True,
        False,
    ]

    # The library reports MB/s; shown in Mbit/s
    rx = state(hass, "sensor", GS105_SERIAL, "port_1_rx")
    assert float(rx.state) == 4.0 and rx.attributes["unit_of_measurement"] == "Mbit/s"
    assert float(state(hass, "sensor", GS105_SERIAL, "port_1_tx").state) == 2.0
    assert float(state(hass, "sensor", GS105_SERIAL, "rx").state) == 6.0
    assert float(state(hass, "sensor", GS105_SERIAL, "tx").state) == 6.0
    assert float(state(hass, "sensor", GS105_SERIAL, "port_1_link_speed").state) == 1000


async def test_totals_and_errors_are_off_until_enabled(hass: HomeAssistant, gs105) -> None:
    registry = er.async_get(hass)
    for key in ("port_1_total_rx", "port_1_total_tx", "crc_errors"):
        entry = registry.async_get(entity_id(hass, "sensor", GS105_SERIAL, key))
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION, key
    for key in ("port_1_rx", "port_1_tx", "port_1_link_speed", "rx", "tx"):
        assert registry.async_get(entity_id(hass, "sensor", GS105_SERIAL, key)).disabled_by is None, key


async def test_a_switch_without_poe_or_leds_has_none_of_their_entities(hass: HomeAssistant, gs105) -> None:
    assert entity_id(hass, "switch", GS105_SERIAL, "port_1_poe") is None
    assert entity_id(hass, "sensor", GS105_SERIAL, "port_1_poe_power") is None
    assert entity_id(hass, "button", GS105_SERIAL, "port_1_poe_power_cycle") is None
    assert entity_id(hass, "switch", GS105_SERIAL, "leds") is None
    # This model can restart
    assert entity_id(hass, "button", GS105_SERIAL, "restart")


async def test_turning_a_port_off_only_on_models_that_can_and_only_when_enabled(
    hass: HomeAssistant, gs105, gs308
) -> None:
    registry = er.async_get(hass)
    port = registry.async_get(entity_id(hass, "switch", GS105_SERIAL, "port_1_enabled"))
    # Off by default: turning off the port to Home Assistant locks you out
    assert port.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert entity_id(hass, "switch", GS308_SERIAL, "port_1_enabled") is None


async def test_poe(hass: HomeAssistant, gs308, fake_switch) -> None:
    assert float(state(hass, "sensor", GS308_SERIAL, "port_1_poe_power").state) == 6.1
    assert state(hass, "sensor", GS308_SERIAL, "port_1_poe_status").state == "delivering_power"
    assert state(hass, "binary_sensor", GS308_SERIAL, "port_1_poe_delivering").state == "on"
    assert state(hass, "binary_sensor", GS308_SERIAL, "port_2_poe_delivering").state == "off"
    switch = state(hass, "switch", GS308_SERIAL, "port_1_poe")
    assert switch.state == "on"

    await hass.services.async_call("switch", "turn_off", {"entity_id": switch.entity_id}, blocking=True)
    await hass.async_block_till_done()
    assert fake_switch.commands == [(GS308, "poe_off", 1)]
    assert hass.states.get(switch.entity_id).state == "off"

    cycle = entity_id(hass, "button", GS308_SERIAL, "port_2_poe_power_cycle")
    await hass.services.async_call("button", "press", {"entity_id": cycle}, blocking=True)
    assert fake_switch.commands[-1] == (GS308, "poe_cycle", 2)


async def test_leds_and_restart(hass: HomeAssistant, gs308, fake_switch) -> None:
    leds = state(hass, "switch", GS308_SERIAL, "leds")
    assert leds.state == "on"
    await hass.services.async_call("switch", "turn_off", {"entity_id": leds.entity_id}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(leds.entity_id).state == "off"
    restart = entity_id(hass, "button", GS308_SERIAL, "restart")
    await hass.services.async_call("button", "press", {"entity_id": restart}, blocking=True)
    assert fake_switch.commands[-1] == (GS308, "reboot")


async def test_a_refused_command_is_an_error(hass: HomeAssistant, gs308, fake_switch) -> None:
    fake_switch.command_result = False
    switch = state(hass, "switch", GS308_SERIAL, "port_1_poe")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("switch", "turn_off", {"entity_id": switch.entity_id}, blocking=True)
    assert hass.states.get(switch.entity_id).state == "on"


async def test_no_answer_makes_the_entities_unavailable(hass: HomeAssistant, gs105, fake_switch, freezer) -> None:
    fake_switch.failing[GS105] = PageFetcherConnectionError
    await next_read(hass, freezer)
    assert state(hass, "binary_sensor", GS105_SERIAL, "port_1_link").state == "unavailable"
    fake_switch.failing.clear()
    await next_read(hass, freezer)
    assert state(hass, "binary_sensor", GS105_SERIAL, "port_1_link").state == "on"


async def test_a_refused_login_asks_for_the_password(hass: HomeAssistant, gs105, fake_switch, freezer) -> None:
    fake_switch.failing[GS105] = LoginFailedError
    await next_read(hass, freezer)
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]


async def test_setup_waits_for_a_switch_that_does_not_answer(hass: HomeAssistant, fake_switch) -> None:
    entry = await add(hass, "10.9.9.9", "NOBODY")
    assert entry.state is ConfigEntryState.SETUP_RETRY
    wrong = MockConfigEntry(domain=DOMAIN, unique_id=GS105_SERIAL, data={"host": GS105, "password": "wrong"})
    wrong.add_to_hass(hass)
    await hass.config_entries.async_setup(wrong.entry_id)
    await hass.async_block_till_done()
    assert wrong.state is ConfigEntryState.SETUP_ERROR


async def test_unloading_logs_out(hass: HomeAssistant, gs105, fake_switch) -> None:
    assert fake_switch.logged_out == []
    assert await hass.config_entries.async_unload(gs105.entry_id)
    await hass.async_block_till_done()
    assert fake_switch.logged_out == [GS105]


async def test_diagnostics_without_password_and_serial(hass: HomeAssistant, gs308) -> None:
    diagnostics = await async_get_config_entry_diagnostics(hass, gs308)
    assert diagnostics["model"] == {
        "name": "GS308EPP",
        "supported": True,
        "ports": 8,
        "poe_ports": [1, 2, 3, 4, 5, 6, 7, 8],
        "port_switch": bool(gs308.runtime_data.model.SWITCH_PORT_TEMPLATES),
        "led_switch": True,
        "restart": True,
    }
    assert diagnostics["data"]["port_1_poe_output_power"] == 6.1
    text = str(diagnostics)
    assert PASSWORD not in text and GS308_SERIAL not in text
