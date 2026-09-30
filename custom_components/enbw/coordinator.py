"""DataUpdateCoordinator for EnBW charging stations."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    EnbwApiClient,
    EnbwApiError,
    EnbwAuthError,
    EnbwNotFoundError,
    StationData,
)
from .const import (
    CONF_ADDRESS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_OPERATOR,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    DOMAIN,
    RELOCATE_RADIUS_KM,
)

_LOGGER = logging.getLogger(__name__)


def station_not_found_issue_id(entry: ConfigEntry) -> str:
    """Return the repair issue ID for a vanished station."""
    return f"station_not_found_{entry.entry_id}"


class EnbwCoordinator(DataUpdateCoordinator[StationData]):
    """Coordinator to poll EnBW station data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: EnbwApiClient,
        update_interval: timedelta,
    ) -> None:
        """Initialize the coordinator."""
        station_id = entry.data[CONF_STATION_ID]
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{station_id}",
            update_interval=update_interval,
            always_update=False,
        )
        self.client = client
        self.station_id = station_id

    async def _async_update_data(self) -> StationData:
        """Fetch station data from the API."""
        try:
            station = await self.client.get_station(self.station_id)
        except EnbwAuthError as err:
            raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
        except EnbwNotFoundError as err:
            station = await self._async_relocate()
            if station is None:
                self._create_not_found_issue()
                raise UpdateFailed(f"Error fetching station data: {err}") from err
        except EnbwApiError as err:
            raise UpdateFailed(f"Error fetching station data: {err}") from err

        ir.async_delete_issue(
            self.hass, DOMAIN, station_not_found_issue_id(self.config_entry)
        )
        self._async_store_station(station)
        return station

    async def _async_relocate(self) -> StationData | None:
        """Look for the station under a new ID at its last known location."""
        data = self.config_entry.data
        latitude = data.get(CONF_LATITUDE)
        longitude = data.get(CONF_LONGITUDE)
        address = data.get(CONF_ADDRESS) or self.config_entry.title
        if latitude is None or longitude is None:
            _LOGGER.debug(
                "Station %s not found and no stored location to search",
                self.station_id,
            )
            return None
        followed_elsewhere = {
            str(entry.data.get(CONF_STATION_ID))
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            if entry.entry_id != self.config_entry.entry_id
        }
        try:
            station = await self.client.find_relocated_station(
                latitude,
                longitude,
                address,
                data.get(CONF_OPERATOR),
                RELOCATE_RADIUS_KM,
                exclude_ids=followed_elsewhere,
            )
        except EnbwApiError as err:
            _LOGGER.debug("Relocation search failed: %s", err)
            return None
        if station is None or station.station_id == self.station_id:
            return None

        _LOGGER.warning(
            "EnBW station %s (%s) was re-registered as %s (%s); following it",
            self.station_id,
            address,
            station.station_id,
            station.short_address,
        )
        self.station_id = station.station_id
        if self.data is not None:
            # Entities were built for the old charge points; rebuild them.
            self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
        return station

    def _async_store_station(self, station: StationData) -> None:
        """Persist station ID and location so a later ID change can be followed."""
        data = self.config_entry.data
        new_data = {
            **data,
            CONF_STATION_ID: station.station_id,
            CONF_STATION_NAME: station.name,
            CONF_ADDRESS: station.short_address,
            CONF_OPERATOR: station.operator,
            CONF_LATITUDE: station.latitude,
            CONF_LONGITUDE: station.longitude,
        }
        if new_data == dict(data):
            return
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data=new_data,
            title=station.short_address or self.config_entry.title,
        )

    def _create_not_found_issue(self) -> None:
        """Tell the user the station is gone and how to fix it."""
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            station_not_found_issue_id(self.config_entry),
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="station_not_found",
            translation_placeholders={
                "station_id": self.station_id,
                "title": self.config_entry.title,
            },
        )
