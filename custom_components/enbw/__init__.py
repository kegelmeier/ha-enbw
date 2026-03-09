"""EnBW Charging Stations integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EnbwApiClient
from .const import CONF_API_KEY, CONF_SCAN_INTERVAL, CONF_STATION_ID, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import EnbwCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EnBW Charging Stations from a config entry."""
    session = async_get_clientsession(hass)
    api_key = entry.data[CONF_API_KEY]
    station_id = entry.data[CONF_STATION_ID]

    scan_interval_seconds = entry.options.get(
        CONF_SCAN_INTERVAL, int(DEFAULT_SCAN_INTERVAL.total_seconds())
    )
    update_interval = timedelta(seconds=scan_interval_seconds)

    client = EnbwApiClient(session, api_key)
    coordinator = EnbwCoordinator(hass, client, station_id, update_interval)

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
