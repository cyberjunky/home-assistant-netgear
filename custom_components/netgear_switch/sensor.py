"""Sensors: the traffic through the switch, and per port its traffic, totals, link speed and PoE."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfDataRate,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfInformation,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import NetgearConfigEntry, NetgearCoordinator
from .entity import NetgearEntity, PortEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class NetgearSensorDescription(SensorEntityDescription):
    """A sensor, with the name the library has for its value (per port: without port_<n>_)."""

    value_key: str


def _rate(key: str, value_key: str, **kwargs) -> NetgearSensorDescription:
    return NetgearSensorDescription(
        key=key,
        translation_key=key,
        value_key=value_key,
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABYTES_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        **kwargs,
    )


def _total(key: str, value_key: str) -> NetgearSensorDescription:
    # Off by default: two more per port. The switch counts from its last restart.
    return NetgearSensorDescription(
        key=key,
        translation_key=key,
        value_key=value_key,
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    )


def _errors(key: str, value_key: str) -> NetgearSensorDescription:
    # CRC errors since the previous read
    return NetgearSensorDescription(
        key=key,
        translation_key=key,
        value_key=value_key,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    )


SWITCH_SENSORS = (
    _rate("rx", "sum_port_speed_rx"),
    _rate("tx", "sum_port_speed_tx"),
    _errors("crc_errors", "sum_port_crc_errors"),
)

PORT_SENSORS = (
    _rate("port_rx", "speed_rx_mbytes"),
    _rate("port_tx", "speed_tx_mbytes"),
    _total("port_total_rx", "sum_rx_mbytes"),
    _total("port_total_tx", "sum_tx_mbytes"),
    NetgearSensorDescription(
        key="port_link_speed",
        translation_key="port_link_speed",
        value_key="connection_speed",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

# Which of these a PoE port has depends on the model: only what the switch reports is added
POE_SENSORS = (
    NetgearSensorDescription(
        key="poe_power",
        translation_key="poe_power",
        value_key="poe_output_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    NetgearSensorDescription(key="poe_status", translation_key="poe_status", value_key="poe_status"),
    NetgearSensorDescription(
        key="poe_voltage",
        translation_key="poe_voltage",
        value_key="poe_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    NetgearSensorDescription(
        key="poe_current",
        translation_key="poe_current",
        value_key="poe_current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.MILLIAMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    NetgearSensorDescription(
        key="poe_temperature",
        translation_key="poe_temperature",
        value_key="poe_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    NetgearSensorDescription(
        key="poe_class",
        translation_key="poe_class",
        value_key="poe_class",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    NetgearSensorDescription(
        key="poe_fault",
        translation_key="poe_fault",
        value_key="poe_fault",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: NetgearConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    data = coordinator.data
    entities: list[SensorEntity] = [
        SwitchSensor(coordinator, description) for description in SWITCH_SENSORS if description.value_key in data
    ]
    entities += [
        PortSensor(coordinator, port, description)
        for port in coordinator.ports
        for description in PORT_SENSORS
        if f"port_{port}_{description.value_key}" in data
    ]
    entities += [
        PortSensor(coordinator, port, description)
        for port in coordinator.poe_ports
        for description in POE_SENSORS
        if f"port_{port}_{description.value_key}" in data
    ]
    async_add_entities(entities)


class SwitchSensor(NetgearEntity, SensorEntity):
    """A value of the whole switch."""

    entity_description: NetgearSensorDescription

    def __init__(self, coordinator: NetgearCoordinator, description: NetgearSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        return self.coordinator.data.get(self.entity_description.value_key)


class PortSensor(PortEntity, SensorEntity):
    """A value of one port."""

    entity_description: NetgearSensorDescription

    def __init__(self, coordinator: NetgearCoordinator, port: int, description: NetgearSensorDescription) -> None:
        super().__init__(coordinator, port, description.key.removeprefix("port_"))
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        value = self.port_value(self.entity_description.value_key)
        # An empty fault text is no fault
        return None if value == "" else value
