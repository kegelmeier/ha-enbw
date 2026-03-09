"""Sensor platform for EnBW Charging Stations."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_STATION_ID, DOMAIN, STATUS_AVAILABLE, STATUS_OCCUPIED, STATUS_OUT_OF_SERVICE
from .coordinator import EnbwCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EnBW sensors from a config entry."""
    coordinator: EnbwCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = [
        EnbwAvailableChargePointsSensor(coordinator, entry),
        EnbwTotalChargePointsSensor(coordinator, entry),
        EnbwUnknownChargePointsSensor(coordinator, entry),
    ]

    # Create per-charge-point sensors
    if coordinator.data and coordinator.data.charge_points:
        for i, cp in enumerate(coordinator.data.charge_points):
            entities.append(
                EnbwChargePointStatusSensor(coordinator, entry, cp.evse_id, i)
            )
            entities.append(
                EnbwChargePointPowerSensor(coordinator, entry, cp.evse_id, i)
            )

    async_add_entities(entities)


class EnbwBaseSensor(CoordinatorEntity[EnbwCoordinator], SensorEntity):
    """Base class for EnBW sensors."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: EnbwCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._station_id = entry.data[CONF_STATION_ID]

    @property
    def device_info(self):
        """Return device info."""
        data = self.coordinator.data
        return {
            "identifiers": {(DOMAIN, f"enbw_{self._station_id}")},
            "name": data.short_address if data else self._station_id,
            "manufacturer": data.operator if data else "EnBW",
            "model": "Charging Station",
            "configuration_url": f"https://www.enbw.com/elektromobilitaet/produkte/mobilityplus-app/ladestation-finden/map",
        }


class EnbwAvailableChargePointsSensor(EnbwBaseSensor):
    """Sensor for available charge points."""

    _attr_icon = "mdi:ev-station"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "available_charge_points"

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"enbw_{self._station_id}_available"

    @property
    def native_value(self) -> int | None:
        """Return the number of available charge points."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.available_charge_points


class EnbwTotalChargePointsSensor(EnbwBaseSensor):
    """Sensor for total charge points."""

    _attr_icon = "mdi:ev-station"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "total_charge_points"

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"enbw_{self._station_id}_total"

    @property
    def native_value(self) -> int | None:
        """Return the total number of charge points."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.number_of_charge_points


class EnbwUnknownChargePointsSensor(EnbwBaseSensor):
    """Sensor for charge points with unknown state."""

    _attr_icon = "mdi:ev-station"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "unknown_charge_points"

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"enbw_{self._station_id}_unknown"

    @property
    def native_value(self) -> int | None:
        """Return the number of charge points with unknown state."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.unknown_state_charge_points


class EnbwChargePointStatusSensor(EnbwBaseSensor):
    """Sensor for individual charge point status."""

    _attr_translation_key = "charge_point_status"
    _attr_device_class = "enum"

    def __init__(
        self,
        coordinator: EnbwCoordinator,
        entry: ConfigEntry,
        evse_id: str,
        index: int,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._evse_id = evse_id
        self._index = index
        self._attr_options = [STATUS_AVAILABLE, STATUS_OCCUPIED, STATUS_OUT_OF_SERVICE]

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"enbw_{self._evse_id}_status"

    @property
    def translation_placeholders(self) -> dict[str, str]:
        """Return translation placeholders."""
        return {"index": str(self._index + 1)}

    @property
    def icon(self) -> str:
        """Return icon based on status."""
        cp = self._get_charge_point()
        if cp is None:
            return "mdi:ev-station"
        if cp.status == STATUS_OCCUPIED:
            return "mdi:car-electric-outline"
        if cp.status == STATUS_OUT_OF_SERVICE:
            return "mdi:ev-station-off"
        # Available - show connector-specific icon
        if cp.plug_type_names:
            name = cp.plug_type_names[0]
            if "Typ 2" in name or "Type 2" in name:
                if "CCS" in name:
                    return "mdi:ev-plug-ccs2"
                return "mdi:ev-plug-type2"
            if "CHAdeMO" in name:
                return "mdi:ev-plug-chademo"
        return "mdi:ev-station"

    @property
    def native_value(self) -> str | None:
        """Return the charge point status."""
        cp = self._get_charge_point()
        return cp.status if cp else None

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        cp = self._get_charge_point()
        if cp is None:
            return {}
        return {
            "evse_id": cp.evse_id,
            "plug_types": cp.plug_type_names,
            "max_power_kw": cp.max_power_kw,
            "cable_attached": [c.cable_attached for c in cp.connectors],
            "handicapped_accessible": cp.handicapped_accessible,
        }

    def _get_charge_point(self):
        """Get charge point data by EVSE ID."""
        if self.coordinator.data is None:
            return None
        for cp in self.coordinator.data.charge_points:
            if cp.evse_id == self._evse_id:
                return cp
        return None


class EnbwChargePointPowerSensor(EnbwBaseSensor):
    """Sensor for charge point max power."""

    _attr_device_class = "power"
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "charge_point_power"

    def __init__(
        self,
        coordinator: EnbwCoordinator,
        entry: ConfigEntry,
        evse_id: str,
        index: int,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._evse_id = evse_id
        self._index = index

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return f"enbw_{self._evse_id}_power"

    @property
    def translation_placeholders(self) -> dict[str, str]:
        """Return translation placeholders."""
        return {"index": str(self._index + 1)}

    @property
    def native_value(self) -> float | None:
        """Return the max power of the charge point."""
        if self.coordinator.data is None:
            return None
        for cp in self.coordinator.data.charge_points:
            if cp.evse_id == self._evse_id:
                return cp.max_power_kw
        return None
