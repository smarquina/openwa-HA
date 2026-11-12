"""Binary availability of the configured OpenWA session."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import SESSION_READY


async def async_setup_entry(hass, entry, async_add_entities):
    """Add session availability."""
    async_add_entities([SessionAvailability(entry)])


class SessionAvailability(CoordinatorEntity, BinarySensorEntity):
    """Indicate whether the configured session is ready."""

    _attr_has_entity_name = True
    _attr_translation_key = "available"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry):
        super().__init__(entry.runtime_data.coordinator)
        self._attr_unique_id = f"{entry.entry_id}_available"

    @property
    def is_on(self):
        return self.coordinator.data == SESSION_READY
