"""Tests for the EnBW config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.enbw.api import (
    EnbwAuthError,
    EnbwConnectionError,
    EnbwNotFoundError,
)
from custom_components.enbw.config_flow import EnbwConfigFlow, EnbwOptionsFlow
from custom_components.enbw.const import (
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    DOMAIN,
)

from .conftest import MOCK_API_KEY, MOCK_STATION_DATA, MOCK_STATION_ID, make_station_data


# --- Config Flow tests (unit-style, no full HA integration loading) ---


class TestConfigFlowManualStep:
    """Tests for the manual step of the config flow."""

    @pytest.mark.asyncio
    async def test_shows_form_when_no_input(self):
        flow = EnbwConfigFlow()
        flow.hass = MagicMock()

        result = await flow.async_step_manual(user_input=None)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "manual"
        assert result["errors"] == {}

    @pytest.mark.asyncio
    async def test_invalid_auth_error(self):
        flow = EnbwConfigFlow()
        flow.hass = MagicMock()

        with patch.object(
            flow,
            "_get_client",
            return_value=MagicMock(
                get_station=AsyncMock(side_effect=EnbwAuthError("Invalid"))
            ),
        ):
            result = await flow.async_step_manual(
                user_input={
                    CONF_STATION_ID: MOCK_STATION_ID,
                    CONF_API_KEY: "bad-key",
                }
            )

        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}

    @pytest.mark.asyncio
    async def test_station_not_found_error(self):
        flow = EnbwConfigFlow()
        flow.hass = MagicMock()

        with patch.object(
            flow,
            "_get_client",
            return_value=MagicMock(
                get_station=AsyncMock(side_effect=EnbwNotFoundError("Not found"))
            ),
        ):
            result = await flow.async_step_manual(
                user_input={
                    CONF_STATION_ID: "nonexistent",
                    CONF_API_KEY: MOCK_API_KEY,
                }
            )

        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {CONF_STATION_ID: "station_not_found"}

    @pytest.mark.asyncio
    async def test_connection_error(self):
        flow = EnbwConfigFlow()
        flow.hass = MagicMock()

        with patch.object(
            flow,
            "_get_client",
            return_value=MagicMock(
                get_station=AsyncMock(side_effect=EnbwConnectionError("Timeout"))
            ),
        ):
            result = await flow.async_step_manual(
                user_input={
                    CONF_STATION_ID: MOCK_STATION_ID,
                    CONF_API_KEY: MOCK_API_KEY,
                }
            )

        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}

    @pytest.mark.asyncio
    async def test_success_creates_entry(self):
        flow = EnbwConfigFlow()
        flow.hass = MagicMock()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        flow.async_create_entry = MagicMock(return_value={"type": FlowResultType.CREATE_ENTRY})

        with patch.object(
            flow,
            "_get_client",
            return_value=MagicMock(
                get_station=AsyncMock(return_value=MOCK_STATION_DATA)
            ),
        ):
            result = await flow.async_step_manual(
                user_input={
                    CONF_STATION_ID: MOCK_STATION_ID,
                    CONF_API_KEY: MOCK_API_KEY,
                }
            )

        flow.async_set_unique_id.assert_called_once_with(f"enbw_{MOCK_STATION_ID}")
        flow._abort_if_unique_id_configured.assert_called_once()
        flow.async_create_entry.assert_called_once()
        call_kwargs = flow.async_create_entry.call_args
        assert call_kwargs.kwargs["data"][CONF_STATION_ID] == MOCK_STATION_ID
        assert call_kwargs.kwargs["data"][CONF_API_KEY] == MOCK_API_KEY

    @pytest.mark.asyncio
    async def test_strips_station_id_whitespace(self):
        flow = EnbwConfigFlow()
        flow.hass = MagicMock()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        flow.async_create_entry = MagicMock(return_value={"type": FlowResultType.CREATE_ENTRY})

        with patch.object(
            flow,
            "_get_client",
            return_value=MagicMock(
                get_station=AsyncMock(return_value=MOCK_STATION_DATA)
            ),
        ) as mock_client:
            await flow.async_step_manual(
                user_input={
                    CONF_STATION_ID: f"  {MOCK_STATION_ID}  ",
                    CONF_API_KEY: MOCK_API_KEY,
                }
            )

        # Should strip whitespace before calling API
        mock_client.return_value.get_station.assert_called_once_with(MOCK_STATION_ID)


class TestConfigFlowUserStep:
    """Tests for the user (menu) step."""

    @pytest.mark.asyncio
    async def test_shows_menu(self):
        flow = EnbwConfigFlow()
        flow.hass = MagicMock()
        flow.async_show_menu = MagicMock(return_value={"type": FlowResultType.MENU})

        result = await flow.async_step_user()

        flow.async_show_menu.assert_called_once()
        call_kwargs = flow.async_show_menu.call_args
        assert "manual" in call_kwargs.kwargs["menu_options"]
        assert "search" in call_kwargs.kwargs["menu_options"]


class TestConfigFlowSearchStep:
    """Tests for the search step."""

    @pytest.mark.asyncio
    async def test_shows_form_when_no_input(self):
        flow = EnbwConfigFlow()
        flow.hass = MagicMock()
        flow.hass.config.latitude = 52.52
        flow.hass.config.longitude = 13.405

        result = await flow.async_step_search(user_input=None)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "search"

    @pytest.mark.asyncio
    async def test_invalid_auth(self):
        flow = EnbwConfigFlow()
        flow.hass = MagicMock()
        flow.hass.config.latitude = 52.52
        flow.hass.config.longitude = 13.405

        with patch.object(
            flow,
            "_get_client",
            return_value=MagicMock(
                validate_api_key=AsyncMock(return_value=False),
            ),
        ):
            result = await flow.async_step_search(
                user_input={
                    CONF_API_KEY: "bad-key",
                    "latitude": 52.52,
                    "longitude": 13.405,
                }
            )

        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}

    @pytest.mark.asyncio
    async def test_no_stations_found(self):
        flow = EnbwConfigFlow()
        flow.hass = MagicMock()
        flow.hass.config.latitude = 52.52
        flow.hass.config.longitude = 13.405

        with patch.object(
            flow,
            "_get_client",
            return_value=MagicMock(
                validate_api_key=AsyncMock(return_value=True),
                search_stations=AsyncMock(return_value=[]),
            ),
        ):
            result = await flow.async_step_search(
                user_input={
                    CONF_API_KEY: MOCK_API_KEY,
                    "latitude": 52.52,
                    "longitude": 13.405,
                }
            )

        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "no_stations_found"}

    @pytest.mark.asyncio
    async def test_connection_error(self):
        flow = EnbwConfigFlow()
        flow.hass = MagicMock()
        flow.hass.config.latitude = 52.52
        flow.hass.config.longitude = 13.405

        with patch.object(
            flow,
            "_get_client",
            return_value=MagicMock(
                validate_api_key=AsyncMock(side_effect=EnbwConnectionError("Timeout")),
            ),
        ):
            result = await flow.async_step_search(
                user_input={
                    CONF_API_KEY: MOCK_API_KEY,
                    "latitude": 52.52,
                    "longitude": 13.405,
                }
            )

        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}


class TestConfigFlowSelectStation:
    """Tests for the select station step."""

    @pytest.mark.asyncio
    async def test_shows_station_list(self):
        flow = EnbwConfigFlow()
        flow.hass = MagicMock()
        flow._stations = [make_station_data("111"), make_station_data("222")]

        result = await flow.async_step_select_station(user_input=None)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "select_station"

    @pytest.mark.asyncio
    async def test_select_creates_entry(self):
        flow = EnbwConfigFlow()
        flow.hass = MagicMock()
        flow._api_key = MOCK_API_KEY
        flow._stations = [make_station_data("111")]
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        flow.async_create_entry = MagicMock(return_value={"type": FlowResultType.CREATE_ENTRY})

        result = await flow.async_step_select_station(
            user_input={CONF_STATION_ID: "111"}
        )

        flow.async_set_unique_id.assert_called_once_with("enbw_111")
        flow.async_create_entry.assert_called_once()
        call_kwargs = flow.async_create_entry.call_args
        assert call_kwargs.kwargs["data"][CONF_STATION_ID] == "111"
        assert call_kwargs.kwargs["data"][CONF_API_KEY] == MOCK_API_KEY


class TestOptionsFlow:
    """Tests for the options flow."""

    @pytest.mark.asyncio
    async def test_shows_form(self):
        entry = MagicMock()
        entry.options = {CONF_SCAN_INTERVAL: 60}

        flow = EnbwOptionsFlow(entry)
        flow.hass = MagicMock()

        result = await flow.async_step_init()
        assert result["type"] == FlowResultType.FORM

    @pytest.mark.asyncio
    async def test_creates_entry_with_new_interval(self):
        entry = MagicMock()
        entry.options = {}

        flow = EnbwOptionsFlow(entry)
        flow.hass = MagicMock()
        flow.async_create_entry = MagicMock(return_value={"type": FlowResultType.CREATE_ENTRY})

        result = await flow.async_step_init(user_input={CONF_SCAN_INTERVAL: 120})

        flow.async_create_entry.assert_called_once_with(
            title="", data={CONF_SCAN_INTERVAL: 120}
        )

    @pytest.mark.asyncio
    async def test_default_interval_from_options(self):
        entry = MagicMock()
        entry.options = {CONF_SCAN_INTERVAL: 90}

        flow = EnbwOptionsFlow(entry)
        flow.hass = MagicMock()

        result = await flow.async_step_init()
        assert result["type"] == FlowResultType.FORM
        # The form should be rendered with the current interval
