"""Diagnostics: what the integration reads, without the password and the serial number."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant
from py_netgear_plus import __version__ as library_version

from .coordinator import NetgearConfigEntry

TO_REDACT = {CONF_PASSWORD, "switch_serial_number", "unique_id"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: NetgearConfigEntry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    model = coordinator.model
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "library": library_version,
        "model": {
            "name": model.MODEL_NAME,
            "supported": model.SUPPORTED,
            "ports": len(coordinator.ports),
            "poe_ports": coordinator.poe_ports,
            "port_switch": bool(model.SWITCH_PORT_TEMPLATES),
            "led_switch": model.has_led_switch(),
            "restart": model.has_reboot_button(),
        },
        "data": async_redact_data(coordinator.data, TO_REDACT),
    }
