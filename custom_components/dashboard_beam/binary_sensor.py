"""Expose the replication problem state for an optional badge."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.loader import async_get_loaded_integration

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ReplicationProblem(entry)])


class ReplicationProblem(BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_has_entity_name = True
    _attr_name = "Replication problem"
    _attr_should_poll = False

    def __init__(self, entry):
        self.rule = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_problem"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name=entry.title,
            entry_type=DeviceEntryType.SERVICE, manufacturer="Jefferies Tube Solutions",
            model="JTS - Dashboard Beam",
            sw_version=str(async_get_loaded_integration(self.rule.hass, DOMAIN).version),
        )

    @property
    def available(self):
        return self.rule.checked

    @property
    def is_on(self):
        return self.rule.error is not None

    @property
    def extra_state_attributes(self):
        return {"reason": self.rule.error} if self.rule.error else {}

    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(
            self.hass, self.rule.signal, self.async_write_ha_state
        ))
