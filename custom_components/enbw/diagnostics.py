"""Diagnostics for EnBW Charging Stations."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY, DOMAIN
from .coordinator import EnbwCoordinator

TO_REDACT = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: EnbwCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    diagnostics: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "unique_id": entry.unique_id,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
    }
    if coordinator is None:
        return diagnostics

    station = coordinator.data
    diagnostics["coordinator"] = {
        "station_id": coordinator.station_id,
        "service_url": coordinator.client.service_url,
        "uses_custom_api_key": bool(entry.data.get(CONF_API_KEY)),
        "last_update_success": coordinator.last_update_success,
        "last_exception": repr(coordinator.last_exception)
        if coordinator.last_exception
        else None,
    }
    if station is not None:
        summary = asdict(station)
        summary.pop("raw", None)
        diagnostics["station"] = summary
        diagnostics["raw"] = station.raw
    return diagnostics
