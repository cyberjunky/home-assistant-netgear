"""A link entity per port (on when a cable is in and the link is up), and whether a PoE port delivers power."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ATTR_PORT, ATTR_SPEED, ATTR_SWITCH_HOST
from .coordinator import NetgearConfigEntry, NetgearCoordinator, is_on
from .entity import PortEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: NetgearConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [PortLink(coordinator, port) for port in coordinator.ports]
    entities += [
        PoeDelivering(coordinator, port)
        for port in coordinator.poe_ports
        if f"port_{port}_poe_power_delivered" in coordinator.data
    ]
    async_add_entities(entities)


class PortLink(PortEntity, BinarySensorEntity):
    """A port's link."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "port"

    def __init__(self, coordinator: NetgearCoordinator, port: int) -> None:
        super().__init__(coordinator, port, "link")

    @property
    def is_on(self) -> bool | None:
        return is_on(self.port_value("status"))

    @property
    def icon(self) -> str:
        if is_on(self.port_value("modus_speed")) is False:
            return "mdi:ethernet-off"
        return "mdi:ethernet" if self.is_on else "mdi:ethernet-cable-off"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            # For other integrations and apps: which port of which switch this is
            ATTR_SWITCH_HOST: self.coordinator.host,
            ATTR_PORT: self.port,
        }
        if speed := self.port_value("connection_speed"):
            attrs[ATTR_SPEED] = speed
        if (enabled := is_on(self.port_value("modus_speed"))) is not None:
            attrs["enabled"] = enabled
        if name := self.port_value("description"):
            attrs["name"] = name
        if (flow_control := self.port_value("flow_control")) is not None:
            attrs["flow_control"] = flow_control
        return attrs


class PoeDelivering(PortEntity, BinarySensorEntity):
    """On while the port powers a device."""

    _attr_device_class = BinarySensorDeviceClass.POWER
    _attr_translation_key = "poe_delivering"

    def __init__(self, coordinator: NetgearCoordinator, port: int) -> None:
        super().__init__(coordinator, port, "poe_delivering")

    @property
    def is_on(self) -> bool | None:
        return is_on(self.port_value("poe_power_delivered"))
