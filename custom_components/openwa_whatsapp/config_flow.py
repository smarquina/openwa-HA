"""Configure an external OpenWA API and validate its selected session."""

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .client import OpenWAClient, OpenWAError, OpenWAErrorCode, validate_endpoint
from .const import (
    CONF_ALLOW_HTTP,
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_SESSION_ID,
    DEFAULT_NAME,
    DOMAIN,
)


class OpenWAConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Set up and reconfigure OpenWA."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Add a ready OpenWA session."""
        return await self._async_form("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Update credentials, session or connection settings."""
        return await self._async_form("reconfigure", user_input, self._get_reconfigure_entry())

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        """Start a flow to replace invalid credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Validate replacement credentials."""
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            data = {**entry.data, CONF_API_KEY: user_input[CONF_API_KEY]}
            try:
                origin = validate_endpoint(
                    data[CONF_BASE_URL], data[CONF_API_KEY],
                    data[CONF_SESSION_ID], data.get(CONF_ALLOW_HTTP, False),
                )
                await OpenWAClient(
                    async_get_clientsession(self.hass), origin,
                    data[CONF_API_KEY], data[CONF_SESSION_ID],
                ).async_check_session()
            except OpenWAError as err:
                errors["base"] = str(err)
            else:
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                )
            }),
            errors=errors,
        )

    async def _async_form(
        self,
        step_id: str,
        user_input: dict[str, Any] | None,
        entry: config_entries.ConfigEntry | None = None,
    ) -> config_entries.ConfigFlowResult:
        errors = {}
        defaults = entry.data if entry else {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            session_id = user_input[CONF_SESSION_ID]
            try:
                origin = validate_endpoint(
                    user_input[CONF_BASE_URL], api_key, session_id, user_input[CONF_ALLOW_HTTP]
                )
                client = OpenWAClient(
                    async_get_clientsession(self.hass), origin, api_key, session_id
                )
                await client.async_check_session()
            except OpenWAError as err:
                errors["base"] = str(err)
            else:
                data = {**user_input, CONF_BASE_URL: str(origin)}
                unique_id = f"{origin}_{session_id}"
                if any(
                    other.unique_id == unique_id
                    and (entry is None or other.entry_id != entry.entry_id)
                    for other in self._async_current_entries()
                ):
                    return self.async_abort(reason="already_configured")
                if entry is not None:
                    return self.async_update_reload_and_abort(entry, data=data, unique_id=unique_id)
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=DEFAULT_NAME, data=data)

        schema = vol.Schema(
            {
                vol.Required(CONF_BASE_URL, default=defaults.get(CONF_BASE_URL, "https://")): str,
                vol.Required(CONF_API_KEY): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required(CONF_SESSION_ID, default=defaults.get(CONF_SESSION_ID, "")): str,
                vol.Required(CONF_ALLOW_HTTP, default=defaults.get(CONF_ALLOW_HTTP, False)): bool,
            }
        )
        return self.async_show_form(step_id=step_id, data_schema=schema, errors=errors)
