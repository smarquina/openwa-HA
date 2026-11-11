"""Redacted diagnostics for OpenWA."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ALLOW_HTTP, DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return configuration characteristics without credentials or identifiers."""
    return {
        "integration": DOMAIN,
        "allow_http": entry.data.get(CONF_ALLOW_HTTP, False),
        "entry_state": entry.state.value,
    }
