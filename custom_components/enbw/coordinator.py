"""DataUpdateCoordinator for EnBW charging stations."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EnbwApiClient, EnbwApiError, EnbwAuthError, StationData
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class EnbwCoordinator(DataUpdateCoordinator[StationData]):
    """Coordinator to poll EnBW station data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: EnbwApiClient,
        station_id: str,
        update_interval: timedelta,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{station_id}",
            update_interval=update_interval,
            always_update=False,
        )
        self.client = client
        self.station_id = station_id

    async def _async_update_data(self) -> StationData:
        """Fetch station data from the API."""
        try:
            return await self.client.get_station(self.station_id)
        except EnbwAuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except EnbwApiError as err:
            raise UpdateFailed(f"Error fetching station data: {err}") from err
