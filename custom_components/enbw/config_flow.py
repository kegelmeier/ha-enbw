"""Config flow for EnBW Charging Stations."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    EnbwApiClient,
    EnbwAuthError,
    EnbwConnectionError,
    EnbwNotFoundError,
    StationData,
)
from .const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_SCAN_INTERVAL,
    CONF_SEARCH_RADIUS,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SEARCH_RADIUS,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class EnbwConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EnBW Charging Stations."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._api_key: str = ""
        self._stations: list[StationData] = []
        self._station_name: str = ""

    def _get_client(self, api_key: str) -> EnbwApiClient:
        """Create an API client."""
        session = async_get_clientsession(self.hass)
        return EnbwApiClient(session, api_key)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - choose setup method."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["manual", "search"],
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual station ID entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            station_id = user_input[CONF_STATION_ID].strip()

            client = self._get_client(api_key)

            try:
                station = await client.get_station(station_id)
            except EnbwAuthError:
                errors["base"] = "invalid_auth"
            except EnbwNotFoundError:
                errors[CONF_STATION_ID] = "station_not_found"
            except EnbwConnectionError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(f"enbw_{station_id}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=station.short_address or station.name,
                    data={
                        CONF_STATION_ID: station_id,
                        CONF_API_KEY: api_key,
                        CONF_STATION_NAME: station.name,
                    },
                )

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STATION_ID): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Required(CONF_API_KEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_search(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle location-based search."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            latitude = user_input[CONF_LATITUDE]
            longitude = user_input[CONF_LONGITUDE]
            radius = user_input.get(CONF_SEARCH_RADIUS, DEFAULT_SEARCH_RADIUS)

            self._api_key = api_key
            client = self._get_client(api_key)

            try:
                if not await client.validate_api_key():
                    errors["base"] = "invalid_auth"
                else:
                    self._stations = await client.search_stations(
                        latitude, longitude, radius
                    )
                    if not self._stations:
                        errors["base"] = "no_stations_found"
                    else:
                        # Sort by distance from search point
                        from homeassistant.util.location import distance as calc_distance

                        for s in self._stations:
                            s._search_distance = calc_distance(
                                latitude, longitude, s.latitude, s.longitude
                            )
                        self._stations.sort(key=lambda s: s._search_distance)
                        self._stations = self._stations[:15]

                        return await self.async_step_select_station()
            except EnbwConnectionError:
                errors["base"] = "cannot_connect"

        ha_lat = self.hass.config.latitude
        ha_lon = self.hass.config.longitude

        return self.async_show_form(
            step_id="search",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Required(CONF_LATITUDE, default=ha_lat): vol.Coerce(float),
                    vol.Required(CONF_LONGITUDE, default=ha_lon): vol.Coerce(float),
                    vol.Optional(
                        CONF_SEARCH_RADIUS, default=DEFAULT_SEARCH_RADIUS
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1, max=50, step=1, mode=NumberSelectorMode.SLIDER, unit_of_measurement="km",
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_select_station(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle station selection from search results."""
        if user_input is not None:
            station_id = user_input[CONF_STATION_ID]

            await self.async_set_unique_id(f"enbw_{station_id}")
            self._abort_if_unique_id_configured()

            station = next(
                (s for s in self._stations if s.station_id == station_id), None
            )
            title = station.short_address if station else station_id

            return self.async_create_entry(
                title=title,
                data={
                    CONF_STATION_ID: station_id,
                    CONF_API_KEY: self._api_key,
                    CONF_STATION_NAME: station.name if station else "",
                },
            )

        options = []
        for s in self._stations:
            dist_km = getattr(s, "_search_distance", 0) / 1000
            label = f"{s.short_address} ({dist_km:.1f} km, {s.max_power_kw} kW, {s.number_of_charge_points} CP)"
            options.append(SelectOptionDict(value=s.station_id, label=label))

        return self.async_show_form(
            step_id="select_station",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STATION_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            multiple=False,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reconfiguration."""
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])

        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            station_id = user_input[CONF_STATION_ID].strip()

            client = self._get_client(api_key)
            try:
                station = await client.get_station(station_id)
            except EnbwAuthError:
                errors["base"] = "invalid_auth"
            except EnbwNotFoundError:
                errors[CONF_STATION_ID] = "station_not_found"
            except EnbwConnectionError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data={
                        CONF_STATION_ID: station_id,
                        CONF_API_KEY: api_key,
                        CONF_STATION_NAME: station.name,
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_STATION_ID, default=entry.data.get(CONF_STATION_ID, "")
                    ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
                    vol.Required(
                        CONF_API_KEY, default=entry.data.get(CONF_API_KEY, "")
                    ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> EnbwOptionsFlow:
        """Get the options flow."""
        return EnbwOptionsFlow(config_entry)


class EnbwOptionsFlow(OptionsFlow):
    """Handle options for EnBW Charging Stations."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self._config_entry.options.get(
            CONF_SCAN_INTERVAL, int(DEFAULT_SCAN_INTERVAL.total_seconds())
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL, default=current_interval
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            max=MAX_SCAN_INTERVAL,
                            step=10,
                            mode=NumberSelectorMode.SLIDER,
                            unit_of_measurement="s",
                        )
                    ),
                }
            ),
        )
