from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import Messdienst24AuthError, Messdienst24Client, Messdienst24Error
from .const import CONF_MD, DEFAULT_MD, DOMAIN

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_MD, default=DEFAULT_MD): str,
    }
)
REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): str})


class Messdienst24ConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _validate(self, data: Mapping[str, Any]) -> str | None:
        client = Messdienst24Client(
            async_create_clientsession(self.hass),
            data[CONF_USERNAME],
            data[CONF_PASSWORD],
            data.get(CONF_MD, DEFAULT_MD),
        )
        try:
            meters = await client.async_get_meters()
        except Messdienst24AuthError:
            return "invalid_auth"
        except Messdienst24Error:
            return "cannot_connect"
        if not meters:
            return "no_meters"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()
            if (error := await self._validate(user_input)) is None:
                return self.async_create_entry(
                    title=f"Messdienst24 ({user_input[CONF_USERNAME]})", data=user_input
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            data = {**entry.data, **user_input}
            if (error := await self._validate(data)) is None:
                return self.async_update_reload_and_abort(entry, data=data)
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=REAUTH_SCHEMA, errors=errors
        )
