"""Two switches, read through a fake of the py-netgear-plus library.

Switch01 (GS105Ev2, 192.168.1.22): 5 ports, no PoE; ports 1 and 2 have a link
poe (GS308EPP, 192.168.1.23): 8 PoE ports and front panel LEDs; port 1 powers a camera

The values are what the library returns for the saved pages of these models.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from py_netgear_plus import (
    LoginFailedError,
    PageFetcherConnectionError,
    SwitchModelNotDetectedError,
    models,
)

GS105, GS308 = "192.168.1.22", "192.168.1.23"
GS105_SERIAL, GS308_SERIAL = "3MX8785Y02A60", "6XK1234567890"
PASSWORD = "secret"


def port(n: int, link: bool, rx: float = 0.0, tx: float = 0.0, **extra: Any) -> dict[str, Any]:
    values = {
        "status": "on" if link else "off",
        "modus_speed": True,
        "connection_speed": 1000 if link else 0,
        "speed_rx_mbytes": rx,
        "speed_tx_mbytes": tx,
        "speed_io_mbytes": rx + tx,
        "sum_rx_mbytes": 33006.57 if link else 0.0,
        "sum_tx_mbytes": 33000.49 if link else 0.0,
        "traffic_rx_mbytes": rx * 30,
        "traffic_tx_mbytes": tx * 30,
        **extra,
    }
    return {f"port_{n}_{key}": value for key, value in values.items()}


def poe(n: int, delivering: bool) -> dict[str, Any]:
    values = {
        "poe_power_active": "on",
        "poe_status": "delivering_power" if delivering else "searching",
        "poe_power_delivered": "on" if delivering else "off",
        "poe_output_power": 6.1 if delivering else 0.0,
        "poe_voltage": 53 if delivering else 0,
        "poe_current": 115 if delivering else 0,
        "poe_temperature": 40,
        "poe_class": 3 if delivering else None,
        "poe_fault": "No Error",
    }
    return {f"port_{n}_{key}": value for key, value in values.items()}


def switch_data(name: str, serial: str, firmware: str, bootloader: str, ports: list[dict[str, Any]]) -> dict[str, Any]:
    data: dict[str, Any] = {
        "switch_ip": "",
        "switch_name": name,
        "switch_serial_number": serial,
        "switch_firmware": firmware,
        "switch_bootloader": bootloader,
        "response_time_s": 30.0,
        "sum_port_crc_errors": 0,
        "sum_port_traffic_rx": 0.0,
        "sum_port_traffic_tx": 0.0,
    }
    for p in ports:
        data.update(p)
    rx = sum(v for k, v in data.items() if k.endswith("_speed_rx_mbytes"))
    tx = sum(v for k, v in data.items() if k.endswith("_speed_tx_mbytes"))
    data.update(sum_port_speed_rx=rx, sum_port_speed_tx=tx, sum_port_speed_io=rx + tx)
    return data


def fresh() -> dict[str, dict[str, Any]]:
    return {
        GS105: {
            "model": models.GS105Ev2,
            "data": switch_data(
                "Switch01",
                GS105_SERIAL,
                "V1.6.0.15",
                "V1.4.0.5-VB",
                [
                    port(1, True, rx=0.5, tx=0.25, description="uplink", flow_control="Disable"),
                    port(2, True, rx=0.25, tx=0.5, description="", flow_control="Disable"),
                    *(port(n, False, description="", flow_control="Disable") for n in (3, 4, 5)),
                ],
            ),
        },
        GS308: {
            "model": models.GS308EPP,
            "data": {
                **switch_data(
                    "poe",
                    GS308_SERIAL,
                    "V1.0.1.4",
                    "unknown",
                    [port(1, True, rx=0.1, tx=0.01), *(port(n, False) for n in range(2, 9))],
                ),
                "led_status": "on",
                **poe(1, True),
                **{k: v for n in range(2, 9) for k, v in poe(n, False).items()},
            },
        },
    }


class FakeSwitch:
    """Stands in for py_netgear_plus.NetgearSwitchConnector."""

    switches: dict[str, dict[str, Any]] = {}
    # Per host: an exception class the next read raises
    failing: dict[str, type[Exception]] = {}
    # What a command returns: False is the switch refusing it
    command_result = True
    commands: list[tuple[Any, ...]] = []
    logged_out: list[str] = []

    def __init__(self, host: str, password: str) -> None:
        self.host = host
        self._password = password
        self.switch_model: Any = models.AutodetectedSwitchModel
        self.ports = 0
        self.poe_ports: list[int] = []

    @property
    def _data(self) -> dict[str, Any]:
        return self.switches[self.host]["data"]

    def autodetect_model(self) -> Any:
        if self.host not in self.switches:
            raise SwitchModelNotDetectedError
        self.switch_model = self.switches[self.host]["model"]()
        self.ports = self.switch_model.PORTS
        self.poe_ports = list(self.switch_model.POE_PORTS)
        return self.switch_model

    def get_login_cookie(self) -> bool:
        return self._password == PASSWORD

    def delete_login_cookie(self) -> bool:
        self.logged_out.append(self.host)
        return True

    def get_unique_id(self) -> str:
        return f"{self.switch_model.MODEL_NAME.lower()}_{self.host.replace('.', '_')}"

    def get_switch_infos(self) -> dict[str, Any]:
        if error := self.failing.get(self.host):
            raise error("no answer")
        return {**self._data, "switch_ip": self.host}

    def _command(self, name: str, *args: Any, **changes: Any) -> bool:
        self.commands.append((self.host, name, *args))
        if self.command_result:
            self._data.update(changes)
        return self.command_result

    def turn_on_poe_port(self, n: int) -> bool:
        return self._command("poe_on", n, **{f"port_{n}_poe_power_active": "on"})

    def turn_off_poe_port(self, n: int) -> bool:
        return self._command("poe_off", n, **{f"port_{n}_poe_power_active": "off"})

    def power_cycle_poe_port(self, n: int) -> bool:
        return self._command("poe_cycle", n)

    def turn_on_port(self, n: int) -> bool:
        return self._command("port_on", n, **{f"port_{n}_modus_speed": True})

    def turn_off_port(self, n: int) -> bool:
        return self._command("port_off", n, **{f"port_{n}_modus_speed": False, f"port_{n}_status": "off"})

    def turn_on_leds(self) -> bool:
        return self._command("leds_on", led_status="on")

    def turn_off_leds(self) -> bool:
        return self._command("leds_off", led_status="off")

    def reboot(self) -> bool:
        return self._command("reboot")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    return


@pytest.fixture
def fake_switch():
    FakeSwitch.switches = fresh()
    FakeSwitch.failing = {}
    FakeSwitch.command_result = True
    FakeSwitch.commands = []
    FakeSwitch.logged_out = []
    with patch("custom_components.netgear_switch.coordinator.NetgearSwitchConnector", FakeSwitch):
        yield FakeSwitch


__all__ = ["LoginFailedError", "PageFetcherConnectionError"]
