"""Constants for the Cremalink Home Assistant integration."""

DEVICE_NAME = "device_name"

DOMAIN = "cremalink_ha"
CONF_ADDON_URL = "addon_url"
CONF_DSN = "dsn"
CONF_LAN_KEY = "lan_key"
CONF_DEVICE_IP = "device_ip"
CONF_DEVICE_MAP = "device_map"

CONF_CONNECTION_TYPE = "connection_type"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_TOKEN_FILE = "token_file"
CONF_EMAIL = "email"
CONF_PASSWORD = "password"

CONNECTION_LOCAL = "local"
CONNECTION_CLOUD = "cloud"

DEFAULT_ADDON_URL = "http://localhost:10280"
CUSTOM_MAP_DIR = "cremalink_custom_maps"
TOKEN_DIR = "cremalink_tokens"

# App connection refresh interval in seconds.
APP_ID_REFRESH_INTERVAL = 60

# Properties (counters, recipes, profiles) polling interval in seconds.
PROPERTIES_SCAN_INTERVAL = 300
