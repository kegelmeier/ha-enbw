"""Tests for recovering from API moves, key changes and station re-registration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import ClientSession
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.enbw.api import (
    EnbwApiClient,
    EnbwAuthError,
    EnbwNotFoundError,
    _parse_charge_point,
    _parse_station,
    normalize_street,
)
from custom_components.enbw.const import (
    CONF_ADDRESS,
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_OPERATOR,
    CONF_STATION_ID,
    DEFAULT_PUBLIC_API_KEY,
    DEFAULT_SERVICE_URL,
    DOMAIN,
    MAP_PAGE_URL,
)
from custom_components.enbw.coordinator import EnbwCoordinator

from .conftest import MOCK_API_RESPONSE, make_station_data

NEW_URL = "https://api.example.test/emobility-public-api/api/v1/chargestations"
MAP_PAGE = (
    '<script id="charging-station-loader" '
    f'data-service-url="{NEW_URL}" data-subscription-key="new-key"></script>'
)


def _response(status: int = 200, json_data=None, text: str = ""):
    response = AsyncMock()
    response.status = status
    response.json = AsyncMock(return_value=json_data)
    response.text = AsyncMock(return_value=text)
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _routing_session(routes):
    """Session whose GET answers by URL via ``routes(url, headers, params)``."""
    session = MagicMock(spec=ClientSession)
    session.get = MagicMock(
        side_effect=lambda url, headers=None, timeout=None, params=None: routes(
            url, headers or {}, params
        )
    )
    return session


class TestParsing:
    def test_status_falls_back_to_state_value(self):
        cp = _parse_charge_point({"state": {"value": "OCCUPIED", "updatedAt": 1790772966901}})
        assert cp.status == "OCCUPIED"
        assert cp.status_updated_at == datetime.fromtimestamp(1790772966.901, tz=UTC)

    def test_missing_state_is_tolerated(self):
        cp = _parse_charge_point({"status": "AVAILABLE", "state": None})
        assert cp.status == "AVAILABLE"
        assert cp.status_updated_at is None

    @pytest.mark.parametrize(
        ("old", "new"),
        [
            ("Clemensstraße 12, 80803 München, DE", "Clemensstraße 12A, 80803 München, DE"),
            ("Leopoldstr. 19, 80802 München", "Leopoldstraße 19 a, 80802 München, DE"),
            ("Prinzregentenplatz 10A, 81675 München", "Prinzregentenplatz 10, 81675 München"),
        ],
    )
    def test_normalize_street_ignores_suffixes(self, old, new):
        assert normalize_street(old) == normalize_street(new)

    def test_normalize_street_keeps_house_number(self):
        assert normalize_street("Leopoldstraße 19") != normalize_street("Leopoldstraße 193")
        assert normalize_street("Leopoldstraße 19") != normalize_street("Leopoldstraße 191A")


class TestDiscovery:
    async def test_defaults(self):
        client = EnbwApiClient(MagicMock(spec=ClientSession))
        assert client.api_key == DEFAULT_PUBLIC_API_KEY
        assert client.service_url == DEFAULT_SERVICE_URL

    async def test_moved_api_is_rediscovered_on_404(self):
        def routes(url, headers, params):
            if url == MAP_PAGE_URL:
                return _response(text=MAP_PAGE)
            if url.startswith(NEW_URL) and headers["Ocp-Apim-Subscription-Key"] == "new-key":
                return _response(json_data=MOCK_API_RESPONSE)
            return _response(status=404)

        client = EnbwApiClient(_routing_session(routes))
        station = await client.get_station("123456")

        assert station.station_id == "123456"
        assert client.service_url == NEW_URL
        assert client.api_key == "new-key"

    async def test_rotated_key_is_rediscovered_on_401(self):
        def routes(url, headers, params):
            if url == MAP_PAGE_URL:
                return _response(
                    text=f'data-service-url="{DEFAULT_SERVICE_URL}" data-subscription-key="new-key"'
                )
            if headers["Ocp-Apim-Subscription-Key"] == "new-key":
                return _response(json_data=MOCK_API_RESPONSE)
            return _response(status=401)

        client = EnbwApiClient(_routing_session(routes), "old-key")
        await client.get_station("123456")
        assert client.api_key == "new-key"

    async def test_unchanged_map_page_raises_original_error(self):
        def routes(url, headers, params):
            if url == MAP_PAGE_URL:
                return _response(
                    text=f'data-service-url="{DEFAULT_SERVICE_URL}" '
                    f'data-subscription-key="{DEFAULT_PUBLIC_API_KEY}"'
                )
            return _response(status=404)

        session = _routing_session(routes)
        client = EnbwApiClient(session)
        with pytest.raises(EnbwNotFoundError):
            await client.get_station("1")
        # Second failure within the cooldown does not fetch the map page again.
        with pytest.raises(EnbwNotFoundError):
            await client.get_station("1")
        map_calls = [c for c in session.get.call_args_list if c.args[0] == MAP_PAGE_URL]
        assert len(map_calls) == 1

    async def test_unreachable_map_page_raises_auth_error(self):
        def routes(url, headers, params):
            return _response(status=503 if url == MAP_PAGE_URL else 401)

        client = EnbwApiClient(_routing_session(routes), "bad")
        with pytest.raises(EnbwAuthError):
            await client.get_station("1")


class TestSearch:
    async def test_clusters_are_split(self):
        """A box with a cluster is searched again in quadrants."""
        calls = []

        def routes(url, headers, params):
            calls.append(params)
            span = float(params["toLat"]) - float(params["fromLat"])
            if span > 0.01:
                return _response(json_data=[{"grouped": True, "stationId": None}])
            station_id = f'{float(params["fromLat"]):.5f}_{float(params["fromLon"]):.5f}'
            return _response(json_data=[{**MOCK_API_RESPONSE, "stationId": station_id}])

        client = EnbwApiClient(_routing_session(routes))
        stations = await client.search_stations(48.16, 11.58, 1.0)

        # 0.018° box -> one split -> four 0.009° boxes with one station each
        assert len(calls) == 5
        assert len(stations) == 4

    async def test_request_budget_is_respected(self):
        calls = []

        def routes(url, headers, params):
            calls.append(params)
            return _response(json_data=[{"grouped": True}])

        client = EnbwApiClient(_routing_session(routes))
        await client.search_stations(48.16, 11.58, 5.0)
        assert len(calls) <= 150

    async def test_find_relocated_station_matches_address_and_operator(self):
        results = [
            {**MOCK_API_RESPONSE, "stationId": "3006640", "operator": "SWM",
             "shortAddress": "Clemensstraße 12A, 80803 München, DE", "lat": 48.1635, "lon": 11.5836},
            {**MOCK_API_RESPONSE, "stationId": "999", "operator": "Other",
             "shortAddress": "Clemensstraße 12, 80803 München, DE", "lat": 48.1635, "lon": 11.5836},
            {**MOCK_API_RESPONSE, "stationId": "888", "operator": "SWM",
             "shortAddress": "Clemensstraße 14, 80803 München, DE", "lat": 48.1635, "lon": 11.5837},
        ]
        client = EnbwApiClient(_routing_session(lambda *a: _response(json_data=results)))

        station = await client.find_relocated_station(
            48.1634, 11.5835, "Clemensstraße 12, 80803 München, DE", "SWM"
        )
        assert station is not None and station.station_id == "3006640"

    async def test_find_relocated_station_prefers_exact_suffix(self):
        """10A must not be mistaken for its neighbour 10."""
        results = [
            {**MOCK_API_RESPONSE, "stationId": "2026327", "operator": "SWM",
             "shortAddress": "Prinzregentenplatz 10, 81675 München, DE", "lat": 48.13892, "lon": 11.60478},
            {**MOCK_API_RESPONSE, "stationId": "3013837", "operator": "SWM",
             "shortAddress": "Prinzregentenplatz 10A, 81675 München, DE", "lat": 48.13950, "lon": 11.60560},
        ]
        client = EnbwApiClient(_routing_session(lambda *a: _response(json_data=results)))

        station = await client.find_relocated_station(
            48.13892, 11.60478, "Prinzregentenplatz 10A, 81675 München, DE", "SWM"
        )
        assert station.station_id == "3013837"

        station = await client.find_relocated_station(
            48.13950, 11.60560, "Prinzregentenplatz 10, 81675 München, DE", "SWM"
        )
        assert station.station_id == "2026327"

    async def test_find_relocated_station_skips_excluded(self):
        results = [
            {**MOCK_API_RESPONSE, "stationId": "2026327", "operator": "SWM",
             "shortAddress": "Prinzregentenplatz 10, 81675 München, DE"},
        ]
        client = EnbwApiClient(_routing_session(lambda *a: _response(json_data=results)))
        assert await client.find_relocated_station(
            48.1, 11.6, "Prinzregentenplatz 10A, 81675 München", exclude_ids={"2026327"}
        ) is None

    async def test_find_relocated_station_without_match(self):
        client = EnbwApiClient(_routing_session(lambda *a: _response(json_data=[])))
        assert await client.find_relocated_station(48.0, 11.0, "Nowhere 1") is None


# --- Coordinator ---


def _entry(hass: HomeAssistant, **data) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="enbw_2019593",
        title="Clemensstraße 12, 80803 München, DE",
        data={CONF_STATION_ID: "2019593", CONF_API_KEY: "", **data},
    )
    entry.add_to_hass(hass)
    return entry


def _coordinator(hass, entry, client) -> EnbwCoordinator:
    return EnbwCoordinator(hass, entry, client, timedelta(seconds=60))


async def test_coordinator_follows_relocated_station(hass: HomeAssistant):
    entry = _entry(
        hass,
        **{
            CONF_LATITUDE: 48.1634,
            CONF_LONGITUDE: 11.5835,
            CONF_ADDRESS: "Clemensstraße 12, 80803 München, DE",
            CONF_OPERATOR: "EnBW",
        },
    )
    relocated = make_station_data(station_id="3006640")
    relocated.short_address = "Clemensstraße 12A, 80803 München, DE"
    client = MagicMock(spec=EnbwApiClient)
    client.get_station = AsyncMock(side_effect=EnbwNotFoundError("gone"))
    client.find_relocated_station = AsyncMock(return_value=relocated)

    coordinator = _coordinator(hass, entry, client)
    data = await coordinator._async_update_data()

    assert data.station_id == "3006640"
    assert coordinator.station_id == "3006640"
    assert entry.data[CONF_STATION_ID] == "3006640"
    assert entry.title == "Clemensstraße 12A, 80803 München, DE"
    # Unique ID stays; entity IDs are anchored separately (see base_id tests).
    assert entry.unique_id == "enbw_2019593"


async def test_coordinator_excludes_stations_of_other_entries(hass: HomeAssistant):
    MockConfigEntry(
        domain=DOMAIN, unique_id="enbw_2026327", data={CONF_STATION_ID: "2026327"}
    ).add_to_hass(hass)
    entry = _entry(
        hass, **{CONF_LATITUDE: 48.1389, CONF_LONGITUDE: 11.6047, CONF_ADDRESS: "Prinzregentenplatz 10A"}
    )
    client = MagicMock(spec=EnbwApiClient)
    client.get_station = AsyncMock(side_effect=EnbwNotFoundError("gone"))
    client.find_relocated_station = AsyncMock(return_value=None)

    with pytest.raises(UpdateFailed):
        await _coordinator(hass, entry, client)._async_update_data()
    assert client.find_relocated_station.call_args.kwargs["exclude_ids"] == {"2026327"}


async def test_coordinator_creates_issue_when_station_is_gone(hass: HomeAssistant):
    entry = _entry(hass)  # legacy entry without stored location
    client = MagicMock(spec=EnbwApiClient)
    client.get_station = AsyncMock(side_effect=EnbwNotFoundError("gone"))

    coordinator = _coordinator(hass, entry, client)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    issue_id = f"station_not_found_{entry.entry_id}"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

    # The issue disappears once the station answers again.
    client.get_station = AsyncMock(return_value=make_station_data(station_id="2019593"))
    await coordinator._async_update_data()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_coordinator_stores_location_for_legacy_entries(hass: HomeAssistant):
    entry = _entry(hass)
    client = MagicMock(spec=EnbwApiClient)
    client.get_station = AsyncMock(return_value=make_station_data(station_id="2019593"))

    await _coordinator(hass, entry, client)._async_update_data()

    assert entry.data[CONF_LATITUDE] == 52.52
    assert entry.data[CONF_ADDRESS] == "Teststraße 1, 12345 Berlin"
    assert entry.data[CONF_OPERATOR] == "EnBW"


async def test_coordinator_auth_error_starts_reauth(hass: HomeAssistant):
    entry = _entry(hass)
    client = MagicMock(spec=EnbwApiClient)
    client.get_station = AsyncMock(side_effect=EnbwAuthError("nope"))

    with pytest.raises(ConfigEntryAuthFailed):
        await _coordinator(hass, entry, client)._async_update_data()


# --- Full setup ---


async def test_full_setup_and_relocation_keeps_entity_ids(
    hass: HomeAssistant, enable_custom_integrations
):
    from unittest.mock import patch

    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import entity_registry as er

    from custom_components.enbw.diagnostics import async_get_config_entry_diagnostics

    entry = _entry(
        hass,
        **{
            CONF_API_KEY: "secret",
            CONF_LATITUDE: 52.52,
            CONF_LONGITUDE: 13.405,
            CONF_ADDRESS: "Teststraße 1, 12345 Berlin",
        },
    )
    old = make_station_data(station_id="2019593")
    new = make_station_data(station_id="3006640", total=2)
    get_station = AsyncMock(return_value=old)

    with (
        patch("custom_components.enbw.EnbwApiClient.get_station", get_station),
        patch(
            "custom_components.enbw.EnbwApiClient.find_relocated_station",
            AsyncMock(return_value=new),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED

        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id("binary_sensor", DOMAIN, "enbw_2019593_available_binary")
        assert entity_id is not None
        assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 3 + 4 * 2 + 1

        diag = await async_get_config_entry_diagnostics(hass, entry)
        assert diag["entry"]["data"][CONF_API_KEY] == "**REDACTED**"

        # Station disappears and is found again under a new ID with 2 chargers.
        get_station.side_effect = EnbwNotFoundError("gone")
        coordinator = hass.data[DOMAIN][entry.entry_id]
        await coordinator.async_refresh()
        get_station.side_effect = None
        get_station.return_value = new
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        assert entry.data[CONF_STATION_ID] == "3006640"
        # Station-level entity keeps its ID; stale charger entities are gone.
        assert registry.async_get_entity_id("binary_sensor", DOMAIN, "enbw_2019593_available_binary") == entity_id
        assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 3 + 2 * 2 + 1
        assert hass.states.get(entity_id).attributes["station_id"] == "3006640"


async def test_base_id_pins_prefix_used_by_1_1_0(
    hass: HomeAssistant, enable_custom_integrations
):
    """An entry reconfigured under 1.1.0 keeps the entity IDs 1.1.0 created.

    Its unique_id still names the very first station ID, but 1.1.0 built
    entity IDs from the station ID in the entry data.
    """
    from unittest.mock import patch

    from homeassistant.helpers import entity_registry as er

    from custom_components.enbw.const import CONF_BASE_ID

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="enbw_1250038",
        title="Clemensstraße 12, 80803 München, DE",
        data={CONF_STATION_ID: "2019593", CONF_API_KEY: ""},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.enbw.EnbwApiClient.get_station",
        AsyncMock(return_value=make_station_data(station_id="3006640")),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.data[CONF_BASE_ID] == "enbw_2019593"
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("sensor", DOMAIN, "enbw_2019593_available")
    assert not registry.async_get_entity_id("sensor", DOMAIN, "enbw_1250038_available")


async def test_reconfigure_keeps_base_id(hass: HomeAssistant, enable_custom_integrations):
    from unittest.mock import patch

    from homeassistant.config_entries import SOURCE_RECONFIGURE

    from custom_components.enbw.const import CONF_BASE_ID

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="enbw_1250038",
        data={CONF_STATION_ID: "2019593", CONF_API_KEY: "", CONF_BASE_ID: "enbw_2019593"},
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.enbw.config_flow.EnbwApiClient.get_station",
            AsyncMock(return_value=make_station_data(station_id="3006640")),
        ),
        patch("custom_components.enbw.async_setup_entry", AsyncMock(return_value=True)),
    ):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_STATION_ID: "3006640", CONF_API_KEY: ""}
        )

    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_STATION_ID] == "3006640"
    assert entry.data[CONF_BASE_ID] == "enbw_2019593"


async def test_stale_devices_are_removed_on_setup(
    hass: HomeAssistant, enable_custom_integrations
):
    from unittest.mock import patch

    from homeassistant.helpers import device_registry as dr, entity_registry as er

    from custom_components.enbw import async_remove_config_entry_device
    from custom_components.enbw.const import CONF_BASE_ID

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="enbw_1250038",
        data={CONF_STATION_ID: "3006640", CONF_API_KEY: "", CONF_BASE_ID: "enbw_2019593"},
    )
    entry.add_to_hass(hass)
    devices = dr.async_get(hass)
    entities = er.async_get(hass)
    stale = devices.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "enbw_1250038")}
    )
    entities.async_get_or_create(
        "sensor", DOMAIN, "enbw_1250038_available",
        config_entry=entry, device_id=stale.id,
    )

    with patch(
        "custom_components.enbw.EnbwApiClient.get_station",
        AsyncMock(return_value=make_station_data(station_id="3006640")),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert devices.async_get(stale.id) is None
    assert not entities.async_get_entity_id("sensor", DOMAIN, "enbw_1250038_available")
    remaining = dr.async_entries_for_config_entry(devices, entry.entry_id)
    assert [d.identifiers for d in remaining] == [{(DOMAIN, "enbw_2019593")}]
    current = remaining[0]
    assert entities.async_get_entity_id("sensor", DOMAIN, "enbw_2019593_available")

    # The current device can't be deleted from the UI; a stale one could.
    assert await async_remove_config_entry_device(hass, entry, current) is False
    other = MagicMock(identifiers={(DOMAIN, "enbw_999")})
    assert await async_remove_config_entry_device(hass, entry, other) is True
