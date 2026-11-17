"""The switch as a device, and the base of its entities."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NetgearCoordinator


def device_info(coordinator: NetgearCoordinator) -> DeviceInfo:
    data = coordinator.data
    model = coordinator.model.MODEL_NAME
    bootloader = data.get("switch_bootloader")
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.unique_id)},
        name=data.get("switch_name") or model,
        manufacturer="NETGEAR",
        model=model or None,
        serial_number=data.get("switch_serial_number") or None,
        sw_version=data.get("switch_firmware") or None,
        hw_version=bootloader if bootloader and bootloader != "unknown" else None,
        configuration_url=f"http://{coordinator.host}",
    )


class NetgearEntity(CoordinatorEntity[NetgearCoordinator]):
    """An entity of the switch."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: NetgearCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_id}_{key}"
        self._attr_device_info = device_info(coordinator)


class PortEntity(NetgearEntity):
    """An entity of one port."""

    def __init__(self, coordinator: NetgearCoordinator, port: int, key: str) -> None:
        super().__init__(coordinator, f"port_{port}_{key}")
        self.port = port
        self._attr_translation_placeholders = {"port": str(port)}

    def port_value(self, key: str) -> Any:
        """What the library read for this port, such as status or poe_output_power."""
        return self.coordinator.data.get(f"port_{self.port}_{key}")
