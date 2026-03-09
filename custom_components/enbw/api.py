"""API client for EnBW charging stations."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import (
    API_HEADER_KEY,
    API_HEADERS_BASE,
    API_SEARCH_URL,
    API_STATION_URL,
    API_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


class EnbwApiError(Exception):
    """Base exception for EnBW API errors."""


class EnbwAuthError(EnbwApiError):
    """Authentication error (invalid API key)."""


class EnbwConnectionError(EnbwApiError):
    """Connection error."""


class EnbwNotFoundError(EnbwApiError):
    """Station not found."""


@dataclass
class Connector:
    """A single connector on a charge point."""

    plug_type_name: str
    max_power_kw: float
    cable_attached: bool


@dataclass
class ChargePoint:
    """A single charge point at a station."""

    evse_id: str
    status: str
    connectors: list[Connector] = field(default_factory=list)
    label: str | None = None
    handicapped_accessible: bool = False

    @property
    def max_power_kw(self) -> float:
        """Return max power across all connectors."""
        if not self.connectors:
            return 0.0
        return max(c.max_power_kw for c in self.connectors)

    @property
    def plug_type_names(self) -> list[str]:
        """Return plug type names from all connectors."""
        return [c.plug_type_name for c in self.connectors]


@dataclass
class StationData:
    """Parsed station data from the API."""

    station_id: str
    name: str
    short_address: str
    latitude: float
    longitude: float
    operator: str
    operator_code: str
    max_power_kw: float
    plug_type_names: list[str]
    number_of_charge_points: int
    available_charge_points: int
    unknown_state_charge_points: int
    charge_points: list[ChargePoint] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


def _parse_charge_point(cp_data: dict[str, Any]) -> ChargePoint:
    """Parse a charge point from API response."""
    connectors = [
        Connector(
            plug_type_name=c.get("plugTypeName", "Unknown"),
            max_power_kw=c.get("maxPowerInKw", 0.0),
            cable_attached=c.get("cableAttached", False),
        )
        for c in cp_data.get("connectors", [])
    ]
    return ChargePoint(
        evse_id=cp_data.get("evseId", ""),
        status=cp_data.get("status", "UNKNOWN"),
        connectors=connectors,
        label=cp_data.get("chargePointLabel"),
        handicapped_accessible=cp_data.get("handicappedAccessible", False),
    )


def _parse_station(data: dict[str, Any]) -> StationData:
    """Parse station data from API response."""
    charge_points = [
        _parse_charge_point(cp) for cp in data.get("chargePoints", [])
    ]
    return StationData(
        station_id=str(data.get("stationId", "")),
        name=data.get("name", data.get("shortAddress", "Unknown Station")),
        short_address=data.get("shortAddress", ""),
        latitude=data.get("lat", 0.0),
        longitude=data.get("lon", 0.0),
        operator=data.get("operator", "EnBW"),
        operator_code=data.get("operatorCode", ""),
        max_power_kw=data.get("maxPowerInKw", 0.0),
        plug_type_names=data.get("plugTypeNames", []),
        number_of_charge_points=data.get("numberOfChargePoints", 0),
        available_charge_points=data.get("availableChargePoints", 0),
        unknown_state_charge_points=data.get("unknownStateChargePoints", 0),
        charge_points=charge_points,
        raw=data,
    )


class EnbwApiClient:
    """Async API client for EnBW charging stations."""

    def __init__(self, session: ClientSession, api_key: str) -> None:
        """Initialize the API client."""
        self._session = session
        self._api_key = api_key
        self._timeout = ClientTimeout(total=API_TIMEOUT)

    @property
    def _headers(self) -> dict[str, str]:
        """Return request headers."""
        return {
            **API_HEADERS_BASE,
            API_HEADER_KEY: self._api_key,
        }

    async def _request(self, url: str, params: dict[str, str] | None = None) -> Any:
        """Make an API request."""
        try:
            async with self._session.get(
                url, headers=self._headers, timeout=self._timeout, params=params
            ) as response:
                if response.status == 401:
                    raise EnbwAuthError("Invalid API key")
                if response.status == 404:
                    raise EnbwNotFoundError(f"Not found: {url}")
                if response.status >= 400:
                    text = await response.text()
                    raise EnbwApiError(
                        f"API error {response.status}: {text}"
                    )
                return await response.json()
        except (ClientError, asyncio.TimeoutError) as err:
            raise EnbwConnectionError(
                f"Error communicating with EnBW API: {err}"
            ) from err

    async def get_station(self, station_id: str) -> StationData:
        """Fetch data for a single charging station."""
        url = API_STATION_URL.format(station_id=station_id)
        data = await self._request(url)
        return _parse_station(data)

    async def search_stations(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 5.0,
    ) -> list[StationData]:
        """Search for charging stations in a geographic area."""
        deg_offset = radius_km / 111  # approximate degrees per km

        params = {
            "fromLat": str(latitude - deg_offset),
            "toLat": str(latitude + deg_offset),
            "fromLon": str(longitude - deg_offset),
            "toLon": str(longitude + deg_offset),
            "grouping": "false",
        }

        data = await self._request(API_SEARCH_URL, params=params)

        stations: list[StationData] = []
        for item in data:
            if isinstance(item, dict) and "stationId" in item:
                try:
                    stations.append(_parse_station(item))
                except (KeyError, TypeError):
                    _LOGGER.debug("Skipping invalid station data: %s", item)

        return stations

    async def validate_api_key(self, station_id: str | None = None) -> bool:
        """Validate the API key by making a test request."""
        test_id = station_id or "393894"  # known public station
        try:
            await self.get_station(test_id)
            return True
        except EnbwAuthError:
            return False
        except EnbwNotFoundError:
            # Key works but station doesn't exist - that's fine
            return True
