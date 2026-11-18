"""Reading a NETGEAR Plus switch every 30 seconds, and sending it commands.

The switch is read by the py-netgear-plus library, which logs in to its web interface. The library
is blocking and keeps the previous read to work out the traffic, so everything goes through one lock.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from py_netgear_plus import (
    InvalidPortStatusError,
    LoginFailedError,
    MultipleModelsDetectedError,
    NetgearPlusPageParserError,
    NetgearSwitchConnector,
    NotLoggedInError,
    PageFetcherConnectionError,
    PageNotLoadedError,
    SwitchModelNotDetectedError,
)

from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

# The switch ends a login session now and then, and can refuse a new login for a while (it has only
# a few sessions, and the library reports that the same way as a wrong password). So a refused login
# is tried again with every read, and the password is asked for only after this many in a row.
ASK_PASSWORD_AFTER: Final = 10

type NetgearConfigEntry = ConfigEntry[NetgearCoordinator]

# What the library raises when the switch doesn't answer, or answers something it can't read
READ_ERRORS = (
    PageFetcherConnectionError,
    PageNotLoadedError,
    NotLoggedInError,
    NetgearPlusPageParserError,
    InvalidPortStatusError,
)


class CannotConnectError(Exception):
    """No answer from the address, or what answers is not a switch the library knows."""


class InvalidAuthError(Exception):
    """The switch refuses the login: a wrong password, or no free login session."""


def connect(host: str, password: str) -> NetgearSwitchConnector:
    """Find out which model answers at host and log in. Blocking."""
    api = NetgearSwitchConnector(host, password)
    try:
        api.autodetect_model()
        logged_in = api.get_login_cookie()
    except (SwitchModelNotDetectedError, MultipleModelsDetectedError, *READ_ERRORS) as err:
        raise CannotConnectError(str(err) or type(err).__name__) from err
    except LoginFailedError as err:
        raise InvalidAuthError(str(err)) from err
    if not logged_in:
        raise InvalidAuthError
    return api


def is_on(value: Any) -> bool | None:
    """The library reports a state as "on"/"off" or as a boolean."""
    if value is None:
        return None
    return value in ("on", True)


class NetgearCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """One switch. Its data is what the library reads: a flat dict such as port_1_status."""

    config_entry: NetgearConfigEntry

    def __init__(self, hass: HomeAssistant, entry: NetgearConfigEntry, api: NetgearSwitchConnector) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=entry.data[CONF_HOST], update_interval=SCAN_INTERVAL)
        self.api = api
        self.host: str = entry.data[CONF_HOST]
        self.unique_id: str = entry.unique_id or entry.entry_id
        self._lock = asyncio.Lock()
        self._refused = 0

    @property
    def model(self) -> Any:
        """What this model can do, from the library."""
        return self.api.switch_model

    @property
    def ports(self) -> range:
        return range(1, self.api.ports + 1)

    @property
    def poe_ports(self) -> list[int]:
        return list(self.api.poe_ports or [])

    def _read(self) -> dict[str, Any]:
        """Read the switch; when it no longer accepts our session, log in anew and read again. Blocking."""
        try:
            return self.api.get_switch_infos()
        except LoginFailedError as err:
            _LOGGER.debug("%s ended the session (%s), logging in again", self.host, err)
        try:
            self.api.delete_login_cookie()
        except (LoginFailedError, *READ_ERRORS) as err:
            _LOGGER.debug("Logging out of %s failed: %s", self.host, err)
        self.api = connect(self.host, self.config_entry.data[CONF_PASSWORD])
        return self.api.get_switch_infos()

    async def _async_update_data(self) -> dict[str, Any]:
        async with self._lock:
            try:
                data = await self.hass.async_add_executor_job(self._read)
            except (InvalidAuthError, LoginFailedError) as err:
                self._refused += 1
                if self._refused >= ASK_PASSWORD_AFTER:
                    raise ConfigEntryAuthFailed(str(err)) from err
                raise UpdateFailed(
                    f"{self.host} refuses the login ({self._refused} in a row), trying again: {err}"
                ) from err
            except (CannotConnectError, *READ_ERRORS) as err:
                raise UpdateFailed(f"{self.host}: {err or type(err).__name__}") from err
        self._refused = 0
        return data

    async def async_command(self, command: Callable[..., bool], *args: Any) -> None:
        """Send the switch a command, and read it again."""
        async with self._lock:
            try:
                done = await self.hass.async_add_executor_job(command, *args)
            except (LoginFailedError, *READ_ERRORS) as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="command_error",
                    translation_placeholders={"host": self.host, "reason": str(err) or type(err).__name__},
                ) from err
        if not done:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_refused",
                translation_placeholders={"host": self.host},
            )
        await self.async_request_refresh()

    async def async_close(self) -> None:
        """Log out: the switch has only a few login sessions."""
        async with self._lock:
            try:
                await self.hass.async_add_executor_job(self.api.delete_login_cookie)
            except (LoginFailedError, *READ_ERRORS) as err:
                _LOGGER.debug("Logging out of %s failed: %s", self.host, err)
