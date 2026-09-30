"""Constants for EnBW Charging Stations integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "enbw"

# EnBW moved the API from enbw-emp.azure-api.net to this host in 2026. The
# public map page embeds the current service URL and subscription key, so both
# are rediscovered from there when the defaults stop working.
DEFAULT_SERVICE_URL: Final = (
    "https://api.emp.emob-enbw.com/emobility-public-api/api/v1/chargestations"
)
DEFAULT_PUBLIC_API_KEY: Final = "90a67b9900364009b588e100e4b1cc64"
MAP_PAGE_URL: Final = (
    "https://www.enbw.com/elektromobilitaet/produkte/mobilityplus-app/ladestation-finden/map"
)

API_HEADERS_BASE: Final = {
    "User-Agent": "HomeAssistant/EnBW-Integration",
    "Accept": "application/json",
    "Origin": "https://www.enbw.com",
    "Referer": "https://www.enbw.com/",
}
API_HEADER_KEY: Final = "Ocp-Apim-Subscription-Key"
API_TIMEOUT: Final = 10

DEFAULT_SCAN_INTERVAL: Final = timedelta(seconds=60)
MIN_SCAN_INTERVAL: Final = 30
MAX_SCAN_INTERVAL: Final = 300

CONF_STATION_ID: Final = "station_id"
CONF_STATION_NAME: Final = "station_name"
CONF_API_KEY: Final = "api_key"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_LATITUDE: Final = "latitude"
CONF_LONGITUDE: Final = "longitude"
CONF_SEARCH_RADIUS: Final = "search_radius"
CONF_ADDRESS: Final = "address"
CONF_OPERATOR: Final = "operator"

DEFAULT_SEARCH_RADIUS: Final = 2.0
DEG_PER_KM: Final = 1 / 111
# The search endpoint clusters stations in large boxes; clustered boxes are
# split into quadrants until single stations come back.
MAX_SEARCH_DEPTH: Final = 6
MAX_SEARCH_REQUESTS: Final = 150
SEARCH_CONCURRENCY: Final = 4
# Minimum time between two rediscoveries of service URL and key.
DISCOVERY_COOLDOWN: Final = timedelta(minutes=30)
# Radius used to find a station again after its ID changed.
RELOCATE_RADIUS_KM: Final = 0.3

STATUS_AVAILABLE: Final = "AVAILABLE"
STATUS_OCCUPIED: Final = "OCCUPIED"
STATUS_BLOCKED: Final = "BLOCKED"
STATUS_OUT_OF_SERVICE: Final = "OUT_OF_SERVICE"
STATUS_UNKNOWN: Final = "UNKNOWN"


def entry_base_id(entry) -> str:
    """Return the stable ID prefix for an entry's device and entities.

    Equal to ``enbw_<original station id>``. It is kept when the station is
    re-registered under a new ID, so entity IDs survive that change.
    """
    return entry.unique_id or f"enbw_{entry.data[CONF_STATION_ID]}"
