"""Adding a switch: its address and the password of its web interface. The model is found by itself."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType
from py_netgear_plus import LoginFailedError

from .const import DOMAIN
from .coordinator import READ_ERRORS, CannotConnectError, InvalidAuthError, connect

_LOGGER = logging.getLogger(__name__)

PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _probe(host: str, password: str) -> tuple[str, str]:
    """Log in, read the switch's name and serial number, and log out again. Blocking."""
    api = connect(host, password)
    try:
        data = api.get_switch_infos()
    except LoginFailedError as err:
        raise InvalidAuthError(str(err)) from err
    except READ_ERRORS as err:
        raise CannotConnectError(str(err) or type(err).__name__) from err
    finally:
        try:
            # The switch has only a few login sessions
            api.delete_login_cookie()
        except (LoginFailedError, *READ_ERRORS):
            _LOGGER.debug("Logging out of %s failed", host)
    model = api.switch_model.MODEL_NAME
    # A model whose serial number can't be read: the library's id, of the model and the address
    return str(data.get("switch_name") or model), str(data.get("switch_serial_number") or api.get_unique_id())


class NetgearConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1
    # Why the last try failed, shown with the error
    _reason = ""

    async def _check(self, host: str, password: str, errors: dict[str, str]) -> tuple[str, str] | None:
        try:
            return await self.hass.async_add_executor_job(_probe, host, password)
        except InvalidAuthError:
            errors["base"] = "invalid_auth"
        except CannotConnectError as err:
            errors["base"] = "cannot_connect"
            self._reason = str(err) or "no supported switch answers"
            _LOGGER.warning("Cannot connect to %s: %s", host, self._reason)
        except Exception as err:
            errors["base"] = "unknown"
            self._reason = f"{type(err).__name__}: {err}"
            _LOGGER.exception("Unexpected error connecting to %s", host)
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if found := await self._check(user_input[CONF_HOST], user_input[CONF_PASSWORD], errors):
                name, serial = found
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured(updates={CONF_HOST: user_input[CONF_HOST]})
                return self.async_create_entry(title=name, data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=(user_input or {}).get(CONF_HOST, "")): str,
                    vol.Required(CONF_PASSWORD): PASSWORD,
                }
            ),
            errors=errors,
            description_placeholders={"reason": self._reason},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            if await self._check(entry.data[CONF_HOST], user_input[CONF_PASSWORD], errors):
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD}),
            description_placeholders={"host": entry.data[CONF_HOST], "reason": self._reason},
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The switch got another address, or another password."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            if found := await self._check(user_input[CONF_HOST], user_input[CONF_PASSWORD], errors):
                await self.async_set_unique_id(found[1])
                self._abort_if_unique_id_mismatch(reason="another_switch")
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=(user_input or entry.data)[CONF_HOST]): str,
                    vol.Required(CONF_PASSWORD): PASSWORD,
                }
            ),
            errors=errors,
            description_placeholders={"reason": self._reason},
        )
