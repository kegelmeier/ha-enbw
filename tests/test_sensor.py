"""Tests for EnBW sensor and binary sensor entities."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from custom_components.enbw.api import ChargePoint, Connector, StationData
from custom_components.enbw.binary_sensor import EnbwStationAvailableSensor
from custom_components.enbw.const import CONF_STATION_ID, DOMAIN
from custom_components.enbw.coordinator import EnbwCoordinator
from custom_components.enbw.sensor import (
    EnbwAvailableChargePointsSensor,
    EnbwChargePointPowerSensor,
    EnbwChargePointStatusSensor,
    EnbwTotalChargePointsSensor,
    EnbwUnknownChargePointsSensor,
)

from .conftest import MOCK_STATION_ID, make_station_data


def _make_coordinator(station_data: StationData | None = None) -> MagicMock:
    """Create a mock coordinator."""
    coordinator = MagicMock(spec=EnbwCoordinator)
    coordinator.data = station_data
    return coordinator


def _make_entry(station_id: str = MOCK_STATION_ID) -> MagicMock:
    """Create a mock config entry."""
    entry = MagicMock()
    entry.data = {CONF_STATION_ID: station_id}
    return entry


class TestAvailableChargePointsSensor:
    """Tests for available charge points sensor."""

    def test_native_value(self):
        data = make_station_data(available=3)
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwAvailableChargePointsSensor(coordinator, entry)

        assert sensor.native_value == 3

    def test_native_value_none_when_no_data(self):
        coordinator = _make_coordinator(None)
        entry = _make_entry()
        sensor = EnbwAvailableChargePointsSensor(coordinator, entry)

        assert sensor.native_value is None

    def test_unique_id(self):
        coordinator = _make_coordinator(make_station_data())
        entry = _make_entry()
        sensor = EnbwAvailableChargePointsSensor(coordinator, entry)

        assert sensor.unique_id == f"enbw_{MOCK_STATION_ID}_available"

    def test_icon(self):
        coordinator = _make_coordinator(make_station_data())
        entry = _make_entry()
        sensor = EnbwAvailableChargePointsSensor(coordinator, entry)

        assert sensor.icon == "mdi:ev-station"


class TestTotalChargePointsSensor:
    """Tests for total charge points sensor."""

    def test_native_value(self):
        data = make_station_data(total=6)
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwTotalChargePointsSensor(coordinator, entry)

        assert sensor.native_value == 6

    def test_native_value_none_when_no_data(self):
        coordinator = _make_coordinator(None)
        entry = _make_entry()
        sensor = EnbwTotalChargePointsSensor(coordinator, entry)

        assert sensor.native_value is None

    def test_unique_id(self):
        coordinator = _make_coordinator(make_station_data())
        entry = _make_entry()
        sensor = EnbwTotalChargePointsSensor(coordinator, entry)

        assert sensor.unique_id == f"enbw_{MOCK_STATION_ID}_total"


class TestUnknownChargePointsSensor:
    """Tests for unknown charge points sensor."""

    def test_native_value(self):
        data = make_station_data(unknown=1)
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwUnknownChargePointsSensor(coordinator, entry)

        assert sensor.native_value == 1

    def test_disabled_by_default(self):
        coordinator = _make_coordinator(make_station_data())
        entry = _make_entry()
        sensor = EnbwUnknownChargePointsSensor(coordinator, entry)

        assert sensor.entity_registry_enabled_default is False


class TestChargePointStatusSensor:
    """Tests for individual charge point status sensor."""

    def test_native_value_available(self):
        data = make_station_data()
        evse_id = data.charge_points[0].evse_id
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwChargePointStatusSensor(coordinator, entry, evse_id, 0)

        assert sensor.native_value == "AVAILABLE"

    def test_native_value_occupied(self):
        data = make_station_data()
        evse_id = data.charge_points[2].evse_id  # index 2 is OCCUPIED
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwChargePointStatusSensor(coordinator, entry, evse_id, 2)

        assert sensor.native_value == "OCCUPIED"

    def test_native_value_none_when_no_data(self):
        coordinator = _make_coordinator(None)
        entry = _make_entry()
        sensor = EnbwChargePointStatusSensor(coordinator, entry, "missing", 0)

        assert sensor.native_value is None

    def test_native_value_none_when_evse_not_found(self):
        data = make_station_data()
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwChargePointStatusSensor(coordinator, entry, "nonexistent", 0)

        assert sensor.native_value is None

    def test_unique_id(self):
        data = make_station_data()
        evse_id = data.charge_points[0].evse_id
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwChargePointStatusSensor(coordinator, entry, evse_id, 0)

        assert sensor.unique_id == f"enbw_{evse_id}_status"

    def test_translation_placeholders(self):
        coordinator = _make_coordinator(make_station_data())
        entry = _make_entry()
        sensor = EnbwChargePointStatusSensor(coordinator, entry, "E1", 2)

        assert sensor.translation_placeholders == {"index": "3"}

    def test_icon_available_typ2(self):
        data = make_station_data()
        evse_id = data.charge_points[0].evse_id  # Typ 2 connector
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwChargePointStatusSensor(coordinator, entry, evse_id, 0)

        assert sensor.icon == "mdi:ev-plug-type2"

    def test_icon_occupied(self):
        data = make_station_data()
        evse_id = data.charge_points[2].evse_id  # OCCUPIED
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwChargePointStatusSensor(coordinator, entry, evse_id, 2)

        assert sensor.icon == "mdi:car-electric-outline"

    def test_icon_out_of_service(self):
        data = make_station_data()
        evse_id = data.charge_points[3].evse_id  # OUT_OF_SERVICE
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwChargePointStatusSensor(coordinator, entry, evse_id, 3)

        assert sensor.icon == "mdi:ev-station-off"

    def test_icon_ccs(self):
        data = make_station_data()
        # CCS Typ 2 is charge_points[2], but it's OCCUPIED so icon is car.
        # Create a custom CP that is AVAILABLE with CCS
        data.charge_points[2] = ChargePoint(
            evse_id="CCS_TEST",
            status="AVAILABLE",
            connectors=[Connector("CCS Typ 2", 150.0, True)],
        )
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwChargePointStatusSensor(coordinator, entry, "CCS_TEST", 2)

        assert sensor.icon == "mdi:ev-plug-ccs2"

    def test_icon_chademo(self):
        data = make_station_data()
        data.charge_points[3] = ChargePoint(
            evse_id="CHADEMO_TEST",
            status="AVAILABLE",
            connectors=[Connector("CHAdeMO", 50.0, True)],
        )
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwChargePointStatusSensor(coordinator, entry, "CHADEMO_TEST", 3)

        assert sensor.icon == "mdi:ev-plug-chademo"

    def test_extra_state_attributes(self):
        data = make_station_data()
        evse_id = data.charge_points[0].evse_id
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwChargePointStatusSensor(coordinator, entry, evse_id, 0)

        attrs = sensor.extra_state_attributes
        assert attrs["evse_id"] == evse_id
        assert attrs["plug_types"] == ["Typ 2"]
        assert attrs["max_power_kw"] == 22.0
        assert attrs["cable_attached"] == [False]

    def test_extra_state_attributes_empty_when_no_data(self):
        coordinator = _make_coordinator(None)
        entry = _make_entry()
        sensor = EnbwChargePointStatusSensor(coordinator, entry, "missing", 0)

        assert sensor.extra_state_attributes == {}

    def test_native_value_blocked(self):
        data = make_station_data()
        data.charge_points[0] = ChargePoint(
            evse_id="BLOCKED_TEST",
            status="BLOCKED",
            connectors=[Connector("Typ 2", 22.0, False)],
        )
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwChargePointStatusSensor(coordinator, entry, "BLOCKED_TEST", 0)

        assert sensor.native_value == "BLOCKED"

    def test_icon_blocked(self):
        data = make_station_data()
        data.charge_points[0] = ChargePoint(
            evse_id="BLOCKED_TEST",
            status="BLOCKED",
            connectors=[Connector("Typ 2", 22.0, False)],
        )
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwChargePointStatusSensor(coordinator, entry, "BLOCKED_TEST", 0)

        assert sensor.icon == "mdi:lock"

    def test_options_list(self):
        coordinator = _make_coordinator(make_station_data())
        entry = _make_entry()
        sensor = EnbwChargePointStatusSensor(coordinator, entry, "E1", 0)

        assert "AVAILABLE" in sensor.options
        assert "BLOCKED" in sensor.options
        assert "OCCUPIED" in sensor.options
        assert "OUT_OF_SERVICE" in sensor.options


class TestChargePointPowerSensor:
    """Tests for charge point power sensor."""

    def test_native_value(self):
        data = make_station_data()
        evse_id = data.charge_points[0].evse_id
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwChargePointPowerSensor(coordinator, entry, evse_id, 0)

        assert sensor.native_value == 22.0

    def test_native_value_none_when_no_data(self):
        coordinator = _make_coordinator(None)
        entry = _make_entry()
        sensor = EnbwChargePointPowerSensor(coordinator, entry, "missing", 0)

        assert sensor.native_value is None

    def test_native_value_none_when_evse_not_found(self):
        data = make_station_data()
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwChargePointPowerSensor(coordinator, entry, "nonexistent", 0)

        assert sensor.native_value is None

    def test_disabled_by_default(self):
        coordinator = _make_coordinator(make_station_data())
        entry = _make_entry()
        sensor = EnbwChargePointPowerSensor(coordinator, entry, "E1", 0)

        assert sensor.entity_registry_enabled_default is False

    def test_unique_id(self):
        coordinator = _make_coordinator(make_station_data())
        entry = _make_entry()
        sensor = EnbwChargePointPowerSensor(coordinator, entry, "E1", 0)

        assert sensor.unique_id == "enbw_E1_power"


class TestStationAvailableBinarySensor:
    """Tests for the station available binary sensor."""

    def test_is_on_when_available(self):
        data = make_station_data(available=2)
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwStationAvailableSensor(coordinator, entry)

        assert sensor.is_on is True

    def test_is_off_when_none_available(self):
        data = make_station_data(available=0)
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwStationAvailableSensor(coordinator, entry)

        assert sensor.is_on is False

    def test_is_none_when_no_data(self):
        coordinator = _make_coordinator(None)
        entry = _make_entry()
        sensor = EnbwStationAvailableSensor(coordinator, entry)

        assert sensor.is_on is None

    def test_unique_id(self):
        coordinator = _make_coordinator(make_station_data())
        entry = _make_entry()
        sensor = EnbwStationAvailableSensor(coordinator, entry)

        assert sensor.unique_id == f"enbw_{MOCK_STATION_ID}_available_binary"

    def test_icon_available(self):
        data = make_station_data(available=1)
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwStationAvailableSensor(coordinator, entry)

        assert sensor.icon == "mdi:ev-station"

    def test_icon_unavailable(self):
        data = make_station_data(available=0)
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwStationAvailableSensor(coordinator, entry)

        assert sensor.icon == "mdi:ev-station-off"

    def test_extra_state_attributes(self):
        data = make_station_data(available=2, total=4)
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwStationAvailableSensor(coordinator, entry)

        attrs = sensor.extra_state_attributes
        assert attrs["available"] == 2
        assert attrs["total"] == 4
        assert attrs["address"] == "Teststraße 1, 12345 Berlin"
        assert attrs["latitude"] == 52.52
        assert attrs["longitude"] == 13.405
        assert attrs["max_power_kw"] == 150.0

    def test_extra_state_attributes_empty_when_no_data(self):
        coordinator = _make_coordinator(None)
        entry = _make_entry()
        sensor = EnbwStationAvailableSensor(coordinator, entry)

        assert sensor.extra_state_attributes == {}

    def test_device_info(self):
        data = make_station_data()
        coordinator = _make_coordinator(data)
        entry = _make_entry()
        sensor = EnbwStationAvailableSensor(coordinator, entry)

        info = sensor.device_info
        assert (DOMAIN, f"enbw_{MOCK_STATION_ID}") in info["identifiers"]
        assert info["manufacturer"] == "EnBW"
        assert info["model"] == "Charging Station"
