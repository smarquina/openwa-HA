"""Outgoing WhatsApp notifications for Home Assistant."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    ConfigEntryAuthFailed, ConfigEntryError, ConfigEntryNotReady, ServiceValidationError,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import config_validation as cv

from .application import SendNotification
from .client import OpenWAClient, OpenWAError, OpenWAErrorCode, valid_chat_id, validate_endpoint
from .const import (
    ATTR_CHAT_ID,
    ATTR_ENTRY_ID,
    ATTR_MESSAGE,
    CONF_ALLOW_HTTP,
    CONF_API_KEY,
    CONF_BASE_URL,
    CONF_SESSION_ID,
    DOMAIN,
    SERVICE_SEND_MESSAGE,
)


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CHAT_ID): str,
        vol.Required(ATTR_MESSAGE): str,
        vol.Optional(ATTR_ENTRY_ID): vol.All(str, vol.Length(min=1)),
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the outgoing action once, independent of entry reloads."""
    hass.data.setdefault(DOMAIN, {})

    async def async_send_message(call: ServiceCall) -> None:
        if not valid_chat_id(call.data[ATTR_CHAT_ID]):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_chat_id")
        if not call.data[ATTR_MESSAGE].strip() or len(call.data[ATTR_MESSAGE]) > 4096:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_message")
        clients = hass.data[DOMAIN]
        entry_id = call.data.get(ATTR_ENTRY_ID)
        if entry_id is None and len(clients) == 1:
            entry_id = next(iter(clients))
        if entry_id not in clients:
            error = (
                OpenWAErrorCode.SELECT_ENTRY if entry_id is None and clients
                else OpenWAErrorCode.ENTRY_UNAVAILABLE
            )
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key=error.value)

        try:
            await clients[entry_id].execute(
                call.data[ATTR_CHAT_ID], call.data[ATTR_MESSAGE]
            )
        except OpenWAError as err:
            if err.code == OpenWAErrorCode.INVALID_AUTH:
                entry = hass.config_entries.async_get_entry(entry_id)
                if entry is not None:
                    entry.async_start_reauth(hass)
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key=err.code.value
            ) from None

    hass.services.async_register(
        DOMAIN, SERVICE_SEND_MESSAGE, async_send_message, schema=SERVICE_SCHEMA
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Create the client. Check readiness on use, including after reconnects."""
    try:
        origin = validate_endpoint(
            entry.data[CONF_BASE_URL],
            entry.data[CONF_API_KEY],
            entry.data[CONF_SESSION_ID],
            entry.data.get(CONF_ALLOW_HTTP, False),
        )
    except OpenWAError as err:
        raise ConfigEntryError(translation_domain=DOMAIN, translation_key=err.code.value) from None

    client = OpenWAClient(
        async_get_clientsession(hass),
        origin,
        entry.data[CONF_API_KEY],
        entry.data[CONF_SESSION_ID],
    )
    try:
        await client.async_check_session()
    except OpenWAError as err:
        if err.code == OpenWAErrorCode.INVALID_AUTH:
            raise ConfigEntryAuthFailed from None
        if err.code in {OpenWAErrorCode.CANNOT_CONNECT, OpenWAErrorCode.SESSION_NOT_READY}:
            raise ConfigEntryNotReady from None
        raise ConfigEntryError(translation_domain=DOMAIN, translation_key=err.code.value) from None

    entry.runtime_data = SendNotification(client)
    hass.data[DOMAIN][entry.entry_id] = entry.runtime_data
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove the client when its configuration entry unloads."""
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True
