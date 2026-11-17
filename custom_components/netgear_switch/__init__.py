"""NETGEAR Switch: your NETGEAR Plus (smart managed) switches in Home Assistant.

Every port with its link, speed and traffic, PoE per port (power, on/off, power cycle), the
front panel LEDs and a restart button, for the models the py-netgear-plus library knows.
"""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .coordinator import CannotConnectError, InvalidAuthError, NetgearConfigEntry, NetgearCoordinator, connect

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: NetgearConfigEntry) -> bool:
    host = entry.data[CONF_HOST]
    try:
        api = await hass.async_add_executor_job(connect, host, entry.data[CONF_PASSWORD])
    except InvalidAuthError as err:
        raise ConfigEntryAuthFailed from err
    except CannotConnectError as err:
        raise ConfigEntryNotReady(f"{host}: {err}") from err
    coordinator = NetgearCoordinator(hass, entry, api)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await coordinator.async_close()
        raise
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NetgearConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_close()
    return unloaded
