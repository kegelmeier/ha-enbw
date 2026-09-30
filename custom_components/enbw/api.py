"""API client for EnBW charging stations."""

from __future__ import annotations

import asyncio
import logging
import math
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import (
    API_HEADER_KEY,
    API_HEADERS_BASE,
    API_TIMEOUT,
    DEFAULT_PUBLIC_API_KEY,
    DEFAULT_SERVICE_URL,
    DEG_PER_KM,
    DISCOVERY_COOLDOWN,
    MAP_PAGE_URL,
    MAX_SEARCH_DEPTH,
    MAX_SEARCH_REQUESTS,
    SEARCH_CONCURRENCY,
)

_LOGGER = logging.getLogger(__name__)

_SERVICE_URL_RE = re.compile(r'data-service-url="([^"]+)"')
_SUBSCRIPTION_KEY_RE = re.compile(r'data-subscription-key="([^"]+)"')
_HOUSE_NUMBER_SUFFIX_RE = re.compile(r"(\d+)\s*[a-z]\b")


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
    status_updated_at: datetime | None = None

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


def _parse_timestamp_ms(value: Any) -> datetime | None:
    """Parse an epoch-milliseconds timestamp."""
    if not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


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
    state = cp_data.get("state")
    if not isinstance(state, dict):
        state = {}
    return ChargePoint(
        evse_id=cp_data.get("evseId", ""),
        status=cp_data.get("status") or state.get("value") or "UNKNOWN",
        connectors=connectors,
        label=cp_data.get("chargePointLabel"),
        handicapped_accessible=cp_data.get("handicappedAccessible", False),
        status_updated_at=_parse_timestamp_ms(state.get("updatedAt")),
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


def _street(address: str) -> str:
    """Return the lower-cased street and house number of an address."""
    street = address.split(",", 1)[0].strip().lower()
    street = street.replace("str.", "straße").replace("strasse", "straße")
    return re.sub(r"(\d+)\s+([a-z])\b", r"\1\2", street)


def normalize_street(address: str) -> str:
    """Return the street part of an address without a house-number suffix.

    Operators re-register stations with slightly different addresses
    ("Clemensstraße 12" becomes "Clemensstraße 12A"), so compare on this.
    """
    return _HOUSE_NUMBER_SUFFIX_RE.sub(r"\1", _street(address))


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the approximate distance between two points in metres."""
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    return 6_371_000 * math.hypot(dlat, dlon)


class EnbwApiClient:
    """Async API client for EnBW charging stations.

    Without an explicit key the public key of the EnBW map page is used. When
    the API answers 401 or 404, the current service URL and key are read from
    the map page once and the request is retried, so a moved API or a rotated
    key heals without user action.
    """

    def __init__(
        self,
        session: ClientSession,
        api_key: str | None = None,
        service_url: str | None = None,
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._api_key = api_key or DEFAULT_PUBLIC_API_KEY
        self._service_url = (service_url or DEFAULT_SERVICE_URL).rstrip("/")
        self._timeout = ClientTimeout(total=API_TIMEOUT)
        self._last_discovery: float | None = None

    @property
    def api_key(self) -> str:
        """Return the API key currently in use."""
        return self._api_key

    @property
    def service_url(self) -> str:
        """Return the service URL currently in use."""
        return self._service_url

    @property
    def _headers(self) -> dict[str, str]:
        """Return request headers."""
        return {
            **API_HEADERS_BASE,
            API_HEADER_KEY: self._api_key,
        }

    async def async_discover(self) -> bool:
        """Read service URL and key from the EnBW map page.

        Returns True if either value changed.
        """
        now = time.monotonic()
        if (
            self._last_discovery is not None
            and now - self._last_discovery < DISCOVERY_COOLDOWN.total_seconds()
        ):
            return False
        self._last_discovery = now

        try:
            async with self._session.get(
                MAP_PAGE_URL,
                headers={"User-Agent": API_HEADERS_BASE["User-Agent"]},
                timeout=self._timeout,
            ) as response:
                if response.status != 200:
                    _LOGGER.debug("Map page returned %s", response.status)
                    return False
                page = await response.text()
        except (ClientError, asyncio.TimeoutError) as err:
            _LOGGER.debug("Could not load EnBW map page: %s", err)
            return False

        if not isinstance(page, str):
            return False

        changed = False
        if (match := _SERVICE_URL_RE.search(page)) and (
            url := match.group(1).rstrip("/")
        ) != self._service_url:
            _LOGGER.warning("EnBW API moved from %s to %s", self._service_url, url)
            self._service_url = url
            changed = True
        if (match := _SUBSCRIPTION_KEY_RE.search(page)) and (
            key := match.group(1)
        ) != self._api_key:
            _LOGGER.info("Using updated EnBW public API key")
            self._api_key = key
            changed = True
        return changed

    async def _request_once(
        self, url: str, params: dict[str, str] | None = None
    ) -> Any:
        """Make a single API request."""
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

    async def _request(
        self, path: str = "", params: dict[str, str] | None = None
    ) -> Any:
        """Make an API request, rediscovering URL and key once on 401/404."""
        try:
            return await self._request_once(self._service_url + path, params)
        except (EnbwAuthError, EnbwNotFoundError):
            if not await self.async_discover():
                raise
        return await self._request_once(self._service_url + path, params)

    async def get_station(self, station_id: str) -> StationData:
        """Fetch data for a single charging station."""
        data = await self._request(f"/{station_id}")
        return _parse_station(data)

    async def search_stations(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 5.0,
    ) -> list[StationData]:
        """Search for charging stations in a geographic area.

        The API returns clusters instead of stations for large boxes, so a
        box that contains clusters is split into quadrants and searched again.
        """
        lat_offset = radius_km * DEG_PER_KM
        lon_offset = lat_offset / max(math.cos(math.radians(latitude)), 0.1)

        stations: dict[str, StationData] = {}
        semaphore = asyncio.Semaphore(SEARCH_CONCURRENCY)
        budget = [MAX_SEARCH_REQUESTS]

        async def search_box(
            from_lat: float, to_lat: float, from_lon: float, to_lon: float, depth: int
        ) -> None:
            if budget[0] <= 0:
                return
            budget[0] -= 1
            params = {
                "fromLat": str(from_lat),
                "toLat": str(to_lat),
                "fromLon": str(from_lon),
                "toLon": str(to_lon),
                "grouping": "false",
            }
            async with semaphore:
                data = await self._request(params=params)

            clustered = False
            for item in data if isinstance(data, list) else []:
                if not isinstance(item, dict):
                    continue
                if item.get("grouped") and not item.get("stationId"):
                    clustered = True
                    continue
                if "stationId" not in item:
                    continue
                try:
                    station = _parse_station(item)
                except (KeyError, TypeError):
                    _LOGGER.debug("Skipping invalid station data: %s", item)
                    continue
                stations[station.station_id] = station

            if clustered and depth < MAX_SEARCH_DEPTH:
                mid_lat = (from_lat + to_lat) / 2
                mid_lon = (from_lon + to_lon) / 2
                await asyncio.gather(
                    search_box(from_lat, mid_lat, from_lon, mid_lon, depth + 1),
                    search_box(from_lat, mid_lat, mid_lon, to_lon, depth + 1),
                    search_box(mid_lat, to_lat, from_lon, mid_lon, depth + 1),
                    search_box(mid_lat, to_lat, mid_lon, to_lon, depth + 1),
                )

        await search_box(
            latitude - lat_offset,
            latitude + lat_offset,
            longitude - lon_offset,
            longitude + lon_offset,
            0,
        )
        if budget[0] <= 0:
            _LOGGER.debug("Search budget exhausted; results may be incomplete")
        return list(stations.values())

    async def find_relocated_station(
        self,
        latitude: float,
        longitude: float,
        address: str,
        operator: str | None = None,
        radius_km: float = 0.3,
        exclude_ids: set[str] | None = None,
    ) -> StationData | None:
        """Find a station that was re-registered under a new ID.

        Matches on street and house number and, when known, the operator. An
        exact street match beats one that only agrees without the house-number
        suffix ("10A" vs "10"), so neighbouring stations are not confused.
        Stations in ``exclude_ids`` (already followed elsewhere) are skipped.
        """
        wanted = normalize_street(address) if address else ""
        if not wanted:
            return None
        exact = _street(address)
        exclude_ids = exclude_ids or set()
        candidates = [
            s
            for s in await self.search_stations(latitude, longitude, radius_km)
            if s.station_id not in exclude_ids
            and normalize_street(s.short_address) == wanted
            and (not operator or s.operator == operator)
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda s: (
                _street(s.short_address) != exact,
                distance_m(latitude, longitude, s.latitude, s.longitude),
            ),
        )

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
