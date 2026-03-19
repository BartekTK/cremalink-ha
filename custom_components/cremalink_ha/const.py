"""Constants for the Cremalink Home Assistant integration."""

DEVICE_NAME = "device_name"

DOMAIN = "cremalink_ha"
CONF_ADDON_URL = "addon_url"
CONF_DSN = "dsn"
CONF_LAN_KEY = "lan_key"
CONF_DEVICE_IP = "device_ip"
CONF_DEVICE_MAP = "device_map"
CONF_PROFILE = "profile"

CONF_CONNECTION_TYPE = "connection_type"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_TOKEN_FILE = "token_file"
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_FAST_SCAN_INTERVAL = "fast_scan_interval"
CONF_SLOW_SCAN_INTERVAL = "slow_scan_interval"
CONF_PROPERTIES_SCAN_INTERVAL = "properties_scan_interval"
CONF_APP_ID_REFRESH_INTERVAL = "app_id_refresh_interval"
CONF_FILTER_ALERT_THRESHOLD = "filter_alert_threshold"
CONF_GROUNDS_ALERT_THRESHOLD = "grounds_alert_threshold"

CONNECTION_LOCAL = "local"
CONNECTION_CLOUD = "cloud"

DEFAULT_ADDON_URL = "http://localhost:10280"
CUSTOM_MAP_DIR = "cremalink_custom_maps"
TOKEN_DIR = "cremalink_tokens"

# App connection refresh interval in seconds.
APP_ID_REFRESH_INTERVAL = 60

# Properties (counters, recipes, profiles) polling interval in seconds.
PROPERTIES_SCAN_INTERVAL = 300
FAST_SCAN_INTERVAL = 1
SLOW_SCAN_INTERVAL = 30
FILTER_ALERT_THRESHOLD = 10
GROUNDS_ALERT_THRESHOLD = 90

# Service name for custom brewing.
SERVICE_BREW = "brew"
SERVICE_RUN_COMMAND = "run_command"

# Brew service parameter names (matching TLV param names).
BREW_PARAMS = [
    "coffee_ml", "milk_ml", "water_ml", "temperature",
    "taste", "aroma", "foam_level", "milk_temp",
    "double_shot", "milk_first", "pre_brew", "ice_amount",
    "cups_count", "grinder",
]
