"""Tests for the EnBW API client."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientError, ClientSession

from custom_components.enbw.api import (
    ChargePoint,
    Connector,
    EnbwApiClient,
    EnbwApiError,
    EnbwAuthError,
    EnbwConnectionError,
    EnbwNotFoundError,
    StationData,
    _parse_charge_point,
    _parse_station,
)

from .conftest import MOCK_API_KEY, MOCK_API_RESPONSE, MOCK_STATION_ID


# --- Dataclass tests ---


class TestConnector:
    """Tests for Connector dataclass."""

    def test_create(self):
        c = Connector(plug_type_name="CCS", max_power_kw=150.0, cable_attached=True)
        assert c.plug_type_name == "CCS"
        assert c.max_power_kw == 150.0
        assert c.cable_attached is True


class TestChargePoint:
    """Tests for ChargePoint dataclass."""

    def test_max_power_kw(self):
        cp = ChargePoint(
            evse_id="E1",
            status="AVAILABLE",
            connectors=[
                Connector("Typ 2", 22.0, False),
                Connector("CCS", 150.0, True),
            ],
        )
        assert cp.max_power_kw == 150.0

    def test_max_power_kw_no_connectors(self):
        cp = ChargePoint(evse_id="E1", status="AVAILABLE")
        assert cp.max_power_kw == 0.0

    def test_plug_type_names(self):
        cp = ChargePoint(
            evse_id="E1",
            status="AVAILABLE",
            connectors=[
                Connector("Typ 2", 22.0, False),
                Connector("CCS", 150.0, True),
            ],
        )
        assert cp.plug_type_names == ["Typ 2", "CCS"]


# --- Parser tests ---


class TestParsers:
    """Tests for API response parsers."""

    def test_parse_charge_point(self):
        cp_data = {
            "evseId": "DE*ENB*E123*1",
            "status": "OCCUPIED",
            "chargePointLabel": "CP1",
            "handicappedAccessible": True,
            "connectors": [
                {"plugTypeName": "CCS", "maxPowerInKw": 150.0, "cableAttached": True}
            ],
        }
        cp = _parse_charge_point(cp_data)
        assert cp.evse_id == "DE*ENB*E123*1"
        assert cp.status == "OCCUPIED"
        assert cp.label == "CP1"
        assert cp.handicapped_accessible is True
        assert len(cp.connectors) == 1
        assert cp.connectors[0].plug_type_name == "CCS"

    def test_parse_charge_point_defaults(self):
        cp = _parse_charge_point({})
        assert cp.evse_id == ""
        assert cp.status == "UNKNOWN"
        assert cp.connectors == []
        assert cp.label is None
        assert cp.handicapped_accessible is False

    def test_parse_station(self):
        station = _parse_station(MOCK_API_RESPONSE)
        assert station.station_id == MOCK_STATION_ID
        assert station.name == "Test Station"
        assert station.short_address == "Teststraße 1, 12345 Berlin"
        assert station.latitude == 52.52
        assert station.longitude == 13.405
        assert station.operator == "EnBW"
        assert station.number_of_charge_points == 4
        assert station.available_charge_points == 2
        assert len(station.charge_points) == 4
        assert station.raw == MOCK_API_RESPONSE

    def test_parse_station_name_fallback(self):
        data = {"shortAddress": "Musterweg 5", "stationId": "999"}
        station = _parse_station(data)
        assert station.name == "Musterweg 5"

    def test_parse_station_defaults(self):
        station = _parse_station({})
        assert station.station_id == ""
        assert station.name == "Unknown Station"
        assert station.latitude == 0.0


# --- API Client tests ---


class TestEnbwApiClient:
    """Tests for the EnBW API client."""

    def _make_session(self, status=200, json_data=None, text="", raise_error=None):
        """Create a mock aiohttp session."""
        response = AsyncMock()
        response.status = status
        response.json = AsyncMock(return_value=json_data or {})
        response.text = AsyncMock(return_value=text)

        context_manager = AsyncMock()
        context_manager.__aenter__ = AsyncMock(return_value=response)
        context_manager.__aexit__ = AsyncMock(return_value=False)

        session = MagicMock(spec=ClientSession)
        if raise_error:
            session.get = MagicMock(side_effect=raise_error)
        else:
            session.get = MagicMock(return_value=context_manager)

        return session

    @pytest.mark.asyncio
    async def test_get_station_success(self):
        session = self._make_session(json_data=MOCK_API_RESPONSE)
        client = EnbwApiClient(session, MOCK_API_KEY)

        station = await client.get_station(MOCK_STATION_ID)

        assert isinstance(station, StationData)
        assert station.station_id == MOCK_STATION_ID
        assert station.available_charge_points == 2

    @pytest.mark.asyncio
    async def test_get_station_auth_error(self):
        session = self._make_session(status=401)
        client = EnbwApiClient(session, "bad-key")

        with pytest.raises(EnbwAuthError, match="Invalid API key"):
            await client.get_station(MOCK_STATION_ID)

    @pytest.mark.asyncio
    async def test_get_station_not_found(self):
        session = self._make_session(status=404)
        client = EnbwApiClient(session, MOCK_API_KEY)

        with pytest.raises(EnbwNotFoundError):
            await client.get_station("nonexistent")

    @pytest.mark.asyncio
    async def test_get_station_server_error(self):
        session = self._make_session(status=500, text="Internal Server Error")
        client = EnbwApiClient(session, MOCK_API_KEY)

        with pytest.raises(EnbwApiError, match="API error 500"):
            await client.get_station(MOCK_STATION_ID)

    @pytest.mark.asyncio
    async def test_get_station_connection_error(self):
        session = self._make_session(raise_error=ClientError("Connection refused"))
        client = EnbwApiClient(session, MOCK_API_KEY)

        with pytest.raises(EnbwConnectionError, match="Error communicating"):
            await client.get_station(MOCK_STATION_ID)

    @pytest.mark.asyncio
    async def test_get_station_timeout(self):
        session = self._make_session(raise_error=asyncio.TimeoutError())
        client = EnbwApiClient(session, MOCK_API_KEY)

        with pytest.raises(EnbwConnectionError):
            await client.get_station(MOCK_STATION_ID)

    @pytest.mark.asyncio
    async def test_search_stations(self):
        search_results = [MOCK_API_RESPONSE, {**MOCK_API_RESPONSE, "stationId": "999"}]
        session = self._make_session(json_data=search_results)
        client = EnbwApiClient(session, MOCK_API_KEY)

        stations = await client.search_stations(52.52, 13.405, 5.0)

        assert len(stations) == 2
        assert stations[0].station_id == MOCK_STATION_ID
        assert stations[1].station_id == "999"

    @pytest.mark.asyncio
    async def test_search_stations_skips_invalid(self):
        search_results = [MOCK_API_RESPONSE, "not a dict", {"no_station_id": True}]
        session = self._make_session(json_data=search_results)
        client = EnbwApiClient(session, MOCK_API_KEY)

        stations = await client.search_stations(52.52, 13.405)
        assert len(stations) == 1

    @pytest.mark.asyncio
    async def test_validate_api_key_success(self):
        session = self._make_session(json_data=MOCK_API_RESPONSE)
        client = EnbwApiClient(session, MOCK_API_KEY)

        assert await client.validate_api_key() is True

    @pytest.mark.asyncio
    async def test_validate_api_key_failure(self):
        session = self._make_session(status=401)
        client = EnbwApiClient(session, "bad-key")

        assert await client.validate_api_key() is False

    @pytest.mark.asyncio
    async def test_validate_api_key_not_found_is_ok(self):
        session = self._make_session(status=404)
        client = EnbwApiClient(session, MOCK_API_KEY)

        # Key works, station just doesn't exist
        assert await client.validate_api_key("nonexistent") is True

    @pytest.mark.asyncio
    async def test_headers_include_api_key(self):
        session = self._make_session(json_data=MOCK_API_RESPONSE)
        client = EnbwApiClient(session, MOCK_API_KEY)

        await client.get_station(MOCK_STATION_ID)

        call_kwargs = session.get.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        assert headers["Ocp-Apim-Subscription-Key"] == MOCK_API_KEY

    @pytest.mark.asyncio
    async def test_search_bounding_box_params(self):
        session = self._make_session(json_data=[])
        client = EnbwApiClient(session, MOCK_API_KEY)

        await client.search_stations(50.0, 10.0, 5.0)

        call_kwargs = session.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["grouping"] == "false"
        assert "fromLat" in params
        assert "toLat" in params
        assert "fromLon" in params
        assert "toLon" in params
