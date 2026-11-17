"""Buttons: restart the switch, and power cycle a PoE port (off and on again, to restart what it powers)."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NetgearConfigEntry, NetgearCoordinator
from .entity import NetgearEntity, PortEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: NetgearConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[ButtonEntity] = [PoePowerCycle(coordinator, port) for port in coordinator.poe_ports]
    if coordinator.model.has_reboot_button():
        entities.append(Restart(coordinator))
    async_add_entities(entities)


class Restart(NetgearEntity, ButtonEntity):
    """Restarts the switch: every link goes down for a moment."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: NetgearCoordinator) -> None:
        super().__init__(coordinator, "restart")

    async def async_press(self) -> None:
        await self.coordinator.async_command(self.coordinator.api.reboot)


class PoePowerCycle(PortEntity, ButtonEntity):
    """Takes the power off a PoE port and puts it back."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_translation_key = "poe_power_cycle"

    def __init__(self, coordinator: NetgearCoordinator, port: int) -> None:
        super().__init__(coordinator, port, "poe_power_cycle")

    async def async_press(self) -> None:
        await self.coordinator.async_command(self.coordinator.api.power_cycle_poe_port, self.port)
