"""Shared fixtures for EnBW Charging Stations tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.enbw.api import (
    ChargePoint,
    Connector,
    EnbwApiClient,
    StationData,
)
from custom_components.enbw.const import (
    CONF_API_KEY,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    DOMAIN,
)
from custom_components.enbw.coordinator import EnbwCoordinator

MOCK_STATION_ID = "123456"
MOCK_API_KEY = "test-api-key-12345"


def make_station_data(
    station_id: str = MOCK_STATION_ID,
    available: int = 2,
    total: int = 4,
    unknown: int = 0,
) -> StationData:
    """Create a StationData fixture with sensible defaults."""
    charge_points = [
        ChargePoint(
            evse_id=f"DE*ENB*E{station_id}*1",
            status="AVAILABLE",
            connectors=[
                Connector(plug_type_name="Typ 2", max_power_kw=22.0, cable_attached=False),
            ],
        ),
        ChargePoint(
            evse_id=f"DE*ENB*E{station_id}*2",
            status="AVAILABLE",
            connectors=[
                Connector(plug_type_name="Typ 2", max_power_kw=22.0, cable_attached=False),
            ],
        ),
        ChargePoint(
            evse_id=f"DE*ENB*E{station_id}*3",
            status="OCCUPIED",
            connectors=[
                Connector(plug_type_name="CCS Typ 2", max_power_kw=150.0, cable_attached=True),
            ],
        ),
        ChargePoint(
            evse_id=f"DE*ENB*E{station_id}*4",
            status="OUT_OF_SERVICE",
            connectors=[
                Connector(plug_type_name="CHAdeMO", max_power_kw=50.0, cable_attached=True),
            ],
        ),
    ]
    return StationData(
        station_id=station_id,
        name="Test Station",
        short_address="Teststraße 1, 12345 Berlin",
        latitude=52.52,
        longitude=13.405,
        operator="EnBW",
        operator_code="ENB",
        max_power_kw=150.0,
        plug_type_names=["Typ 2", "CCS Typ 2", "CHAdeMO"],
        number_of_charge_points=total,
        available_charge_points=available,
        unknown_state_charge_points=unknown,
        charge_points=charge_points[:total],
        raw={},
    )


MOCK_STATION_DATA = make_station_data()

MOCK_API_RESPONSE = {
    "stationId": MOCK_STATION_ID,
    "name": "Test Station",
    "shortAddress": "Teststraße 1, 12345 Berlin",
    "lat": 52.52,
    "lon": 13.405,
    "operator": "EnBW",
    "operatorCode": "ENB",
    "maxPowerInKw": 150.0,
    "plugTypeNames": ["Typ 2", "CCS Typ 2", "CHAdeMO"],
    "numberOfChargePoints": 4,
    "availableChargePoints": 2,
    "unknownStateChargePoints": 0,
    "chargePoints": [
        {
            "evseId": f"DE*ENB*E{MOCK_STATION_ID}*1",
            "status": "AVAILABLE",
            "chargePointLabel": "CP1",
            "handicappedAccessible": False,
            "connectors": [
                {
                    "plugTypeName": "Typ 2",
                    "maxPowerInKw": 22.0,
                    "cableAttached": False,
                }
            ],
        },
        {
            "evseId": f"DE*ENB*E{MOCK_STATION_ID}*2",
            "status": "AVAILABLE",
            "chargePointLabel": "CP2",
            "handicappedAccessible": False,
            "connectors": [
                {
                    "plugTypeName": "Typ 2",
                    "maxPowerInKw": 22.0,
                    "cableAttached": False,
                }
            ],
        },
        {
            "evseId": f"DE*ENB*E{MOCK_STATION_ID}*3",
            "status": "OCCUPIED",
            "chargePointLabel": "CP3",
            "handicappedAccessible": False,
            "connectors": [
                {
                    "plugTypeName": "CCS Typ 2",
                    "maxPowerInKw": 150.0,
                    "cableAttached": True,
                }
            ],
        },
        {
            "evseId": f"DE*ENB*E{MOCK_STATION_ID}*4",
            "status": "OUT_OF_SERVICE",
            "chargePointLabel": "CP4",
            "handicappedAccessible": True,
            "connectors": [
                {
                    "plugTypeName": "CHAdeMO",
                    "maxPowerInKw": 50.0,
                    "cableAttached": True,
                }
            ],
        },
    ],
}


@pytest.fixture
def mock_station_data() -> StationData:
    """Return mock station data."""
    return make_station_data()


@pytest.fixture
def mock_api_response() -> dict:
    """Return mock API response dict."""
    return MOCK_API_RESPONSE.copy()


@pytest.fixture
def mock_config_entry_data() -> dict:
    """Return mock config entry data."""
    return {
        CONF_STATION_ID: MOCK_STATION_ID,
        CONF_API_KEY: MOCK_API_KEY,
        CONF_STATION_NAME: "Test Station",
    }
