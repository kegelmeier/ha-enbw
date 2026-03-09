"""Binary sensor platform for EnBW Charging Stations."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_STATION_ID, DOMAIN
from .coordinator import EnbwCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EnBW binary sensors from a config entry."""
    coordinator: EnbwCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EnbwStationAvailableSensor(coordinator, entry)])


class EnbwStationAvailableSensor(
    CoordinatorEntity[EnbwCoordinator], BinarySensorEntity
):
    """Binary sensor indicating if any charger is available."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PLUG
    _attr_translation_key = "station_available"

    def __init__(
        self, coordinator: EnbwCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._station_id = entry.data[CONF_STATION_ID]

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"enbw_{self._station_id}_available_binary"

    @property
    def device_info(self):
        """Return device info."""
        data = self.coordinator.data
        return {
            "identifiers": {(DOMAIN, f"enbw_{self._station_id}")},
            "name": data.short_address if data else self._station_id,
            "manufacturer": data.operator if data else "EnBW",
            "model": "Charging Station",
        }

    @property
    def is_on(self) -> bool | None:
        """Return True if any charger is available."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.available_charge_points > 0

    @property
    def icon(self) -> str:
        """Return icon based on availability."""
        if self.is_on:
            return "mdi:ev-station"
        return "mdi:ev-station-off"

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra attributes."""
        if self.coordinator.data is None:
            return {}
        data = self.coordinator.data
        return {
            "available": data.available_charge_points,
            "total": data.number_of_charge_points,
            "address": data.short_address,
            "latitude": data.latitude,
            "longitude": data.longitude,
            "max_power_kw": data.max_power_kw,
            "plug_types": data.plug_type_names,
        }
