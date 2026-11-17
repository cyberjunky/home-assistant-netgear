"""Switches: PoE per port, a port itself (on models that can turn one off), and the front panel LEDs."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NetgearConfigEntry, NetgearCoordinator, is_on
from .entity import NetgearEntity, PortEntity

# One command at a time: the switch handles them one by one
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: NetgearConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [PoeSwitch(coordinator, port) for port in coordinator.poe_ports]
    if coordinator.model.SWITCH_PORT_TEMPLATES:
        entities += [PortSwitch(coordinator, port) for port in coordinator.ports]
    if coordinator.model.has_led_switch():
        entities.append(LedSwitch(coordinator))
    async_add_entities(entities)


class PoeSwitch(PortEntity, SwitchEntity):
    """Power over Ethernet on a port."""

    _attr_device_class = SwitchDeviceClass.OUTLET
    _attr_translation_key = "poe"

    def __init__(self, coordinator: NetgearCoordinator, port: int) -> None:
        super().__init__(coordinator, port, "poe")

    @property
    def is_on(self) -> bool | None:
        return is_on(self.port_value("poe_power_active"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self.coordinator.api.turn_on_poe_port, self.port)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self.coordinator.api.turn_off_poe_port, self.port)


class PortSwitch(PortEntity, SwitchEntity):
    """A port: off takes its link down. Disabled by default, so the port to Home Assistant isn't turned off by accident."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "port_enabled"

    def __init__(self, coordinator: NetgearCoordinator, port: int) -> None:
        super().__init__(coordinator, port, "enabled")

    @property
    def is_on(self) -> bool | None:
        return is_on(self.port_value("modus_speed"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self.coordinator.api.turn_on_port, self.port)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self.coordinator.api.turn_off_port, self.port)


class LedSwitch(NetgearEntity, SwitchEntity):
    """The LEDs on the front of the switch."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "leds"

    def __init__(self, coordinator: NetgearCoordinator) -> None:
        super().__init__(coordinator, "leds")

    @property
    def is_on(self) -> bool | None:
        return is_on(self.coordinator.data.get("led_status"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self.coordinator.api.turn_on_leds)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self.coordinator.api.turn_off_leds)
