"""Adding a switch, logging in again, and giving it another address."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.netgear_switch.const import DOMAIN

from .conftest import GS105, GS105_SERIAL, GS308, PASSWORD

GOOD = {"host": GS105, "password": PASSWORD}


async def test_add(hass: HomeAssistant, fake_switch) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], GOOD)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    # Named after the switch, and known by its serial number: its address may change
    assert result["title"] == "Switch01"
    assert result["result"].unique_id == GS105_SERIAL
    assert result["data"] == GOOD
    # The check logged out again, and the entry that was set up is logged in
    assert fake_switch.logged_out == [GS105]


async def test_wrong_password_and_no_answer(hass: HomeAssistant, fake_switch) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**GOOD, "password": "wrong"})
    assert result["errors"] == {"base": "invalid_auth"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**GOOD, "host": "10.9.9.9"})
    assert result["errors"] == {"base": "cannot_connect"}
    assert result["description_placeholders"]["reason"]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], GOOD)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_added_once_and_follows_a_new_address(hass: HomeAssistant, fake_switch) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=GS105_SERIAL, data={**GOOD, "host": "192.168.1.99"})
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], GOOD)
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"
    assert entry.data["host"] == GS105


async def test_reauth(hass: HomeAssistant, fake_switch) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=GS105_SERIAL, data={**GOOD, "password": "old"})
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"password": "nope"})
    assert result["errors"] == {"base": "invalid_auth"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"password": PASSWORD})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reauth_successful"
    assert entry.data == GOOD
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_reconfigure(hass: HomeAssistant, fake_switch) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=GS105_SERIAL, data={**GOOD, "host": "192.168.1.99"})
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    # The address of the other switch
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": GS308, "password": PASSWORD})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "another_switch"
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], GOOD)
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reconfigure_successful"
    assert entry.data == GOOD
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
