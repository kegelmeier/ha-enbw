"""Constants for EnBW Charging Stations integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "enbw"

API_BASE_URL: Final = "https://enbw-emp.azure-api.net/emobility-public-api/api/v1"
API_STATION_URL: Final = f"{API_BASE_URL}/chargestations/{{station_id}}"
API_SEARCH_URL: Final = f"{API_BASE_URL}/chargestations"

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

DEFAULT_SEARCH_RADIUS: Final = 5.0
DEG_PER_KM: Final = 1 / 111

STATUS_AVAILABLE: Final = "AVAILABLE"
STATUS_OCCUPIED: Final = "OCCUPIED"
STATUS_BLOCKED: Final = "BLOCKED"
STATUS_OUT_OF_SERVICE: Final = "OUT_OF_SERVICE"
STATUS_UNKNOWN: Final = "UNKNOWN"
