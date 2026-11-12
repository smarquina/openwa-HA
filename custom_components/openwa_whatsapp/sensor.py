"""Diagnostic state of the configured OpenWA session."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import SESSION_READY
from .errors import OpenWAErrorCode


async def async_setup_entry(hass, entry, async_add_entities):
    """Add the translated session state."""
    async_add_entities([SessionStatus(entry)])


class SessionStatus(CoordinatorEntity, SensorEntity):
    """Explain the current session availability."""

    _attr_has_entity_name = True
    _attr_translation_key = "session"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_options = [SESSION_READY, *(code.value for code in (
        OpenWAErrorCode.INVALID_AUTH, OpenWAErrorCode.FORBIDDEN,
        OpenWAErrorCode.SESSION_NOT_FOUND, OpenWAErrorCode.SESSION_NOT_READY,
        OpenWAErrorCode.CANNOT_CONNECT, OpenWAErrorCode.INVALID_TLS,
        OpenWAErrorCode.INVALID_RESPONSE,
    ))]

    def __init__(self, entry):
        super().__init__(entry.runtime_data.coordinator)
        self._attr_unique_id = f"{entry.entry_id}_session"

    @property
    def native_value(self):
        return self.coordinator.data
