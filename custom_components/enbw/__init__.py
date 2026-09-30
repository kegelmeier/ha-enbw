"""EnBW Charging Stations integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EnbwApiClient
from .const import (
    CONF_API_KEY,
    CONF_BASE_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    entry_base_id,
)
from .coordinator import EnbwCoordinator, station_not_found_issue_id

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


def _scan_interval(entry: ConfigEntry) -> int:
    """Return the configured scan interval in seconds."""
    return int(
        entry.options.get(
            CONF_SCAN_INTERVAL, int(DEFAULT_SCAN_INTERVAL.total_seconds())
        )
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EnBW Charging Stations from a config entry."""
    if CONF_BASE_ID not in entry.data:
        # Pin the entity ID prefix before the station ID can change.
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_BASE_ID: entry_base_id(entry)}
        )

    session = async_get_clientsession(hass)
    client = EnbwApiClient(session, entry.data.get(CONF_API_KEY) or None)
    coordinator = EnbwCoordinator(
        hass, entry, client, timedelta(seconds=_scan_interval(entry))
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _async_remove_stale_devices(hass, entry)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


def _async_remove_stale_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove devices left over from station IDs this entry followed before.

    Up to 1.1.0 every station ID change created a new device. Only the device
    carrying the entry's stable base ID is current; removing the others also
    removes their entities.
    """
    current = (DOMAIN, entry_base_id(entry))
    registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        if current not in device.identifiers:
            registry.async_update_device(
                device.id, remove_config_entry_id=entry.entry_id
            )


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow deleting any device except the entry's current station."""
    return (DOMAIN, entry_base_id(entry)) not in device.identifiers


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when the scan interval changed.

    The coordinator also updates the entry data (location, relocated station
    ID); those updates must not trigger a reload of their own.
    """
    coordinator: EnbwCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is None or coordinator.update_interval != timedelta(
        seconds=_scan_interval(entry)
    ):
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean up a repair issue left by a removed entry."""
    ir.async_delete_issue(hass, DOMAIN, station_not_found_issue_id(entry))
