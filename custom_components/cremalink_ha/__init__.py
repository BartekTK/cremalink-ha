"""The Cremalink Home Assistant integration."""
import logging
import voluptuous as vol
from urllib.parse import urlparse
from functools import partial

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

from cremalink import create_local_device, device_map, Client

from .const import *
from .coordinator import CremalinkCoordinator, CremalinkPropertiesCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SWITCH, Platform.BUTTON, Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SELECT]

BREW_SCHEMA = vol.Schema({
    vol.Required("beverage"): cv.string,
    vol.Optional("coffee_ml"): vol.Coerce(int),
    vol.Optional("milk_ml"): vol.Coerce(int),
    vol.Optional("water_ml"): vol.Coerce(int),
    vol.Optional("temperature"): vol.Coerce(int),
    vol.Optional("taste"): vol.Coerce(int),
    vol.Optional("aroma"): vol.Coerce(int),
    vol.Optional("foam_level"): vol.Coerce(int),
    vol.Optional("milk_temp"): vol.Coerce(int),
})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Cremalink from a config entry.

        Args:
            hass: The Home Assistant instance.
            entry: The config entry.

        Returns:
            True if the setup was successful, False otherwise.
    """
    connection_type = entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_LOCAL)

    dsn = entry.data[CONF_DSN]

    map_selection = entry.data[CONF_DEVICE_MAP]

    try:
        # Resolve the device map path
        if map_selection.startswith("custom:"):
            filename = map_selection.split(":", 1)[1]
            map_path = hass.config.path(CUSTOM_MAP_DIR, filename)
        else:
            map_path = await hass.async_add_executor_job(device_map, map_selection)

    except Exception as e:
        _LOGGER.error("Could not resolve device map '%s': %s", map_selection, e)
        return False

    try:
        if connection_type == CONNECTION_LOCAL:
            addon_url = entry.data[CONF_ADDON_URL]
            lan_key = entry.data[CONF_LAN_KEY]
            device_ip = entry.data[CONF_DEVICE_IP]

            # Parse the addon URL to get host and port
            parsed_url = urlparse(addon_url)
            server_host = parsed_url.hostname
            server_port = parsed_url.port or 80

            # Create the local device instance
            device = await hass.async_add_executor_job(
                partial(
                    create_local_device,
                    dsn=dsn,
                    server_host=server_host,
                    server_port=server_port,
                    device_ip=device_ip,
                    lan_key=lan_key,
                    device_map_path=str(map_path)
                )
            )
        elif connection_type == CONNECTION_CLOUD:
            token_file = entry.data[CONF_TOKEN_FILE]

            def _create_cloud_device():
                client = Client(token_file)
                return client.get_device(dsn, device_map_path=str(map_path))

            device = await hass.async_add_executor_job(_create_cloud_device)

            if device is None:
                raise ConfigEntryNotReady(f"Could not find cloud device with DSN {dsn}")

        else:
            _LOGGER.error("Unknown connection type: %s", connection_type)
            return False
        # Configure the device
        await hass.async_add_executor_job(device.configure)

    except Exception as e:
        raise ConfigEntryNotReady(f"Could not connect to Cremalink device: {e}") from e

    coordinator = CremalinkCoordinator(hass, device, connection_type)
    await coordinator.async_config_entry_first_refresh()

    entry_data: dict = {
        "coordinator": coordinator,
        "device": device,
        "selected_profile": 1,
    }

    if connection_type == CONNECTION_CLOUD:
        properties_coordinator = CremalinkPropertiesCoordinator(hass, device)
        await properties_coordinator.async_config_entry_first_refresh()
        entry_data["properties_coordinator"] = properties_coordinator

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry_data

    # Register the brew service (once, on first entry).
    if not hass.services.has_service(DOMAIN, SERVICE_BREW):
        async def handle_brew(call: ServiceCall) -> None:
            """Handle the brew service call."""
            beverage = call.data["beverage"]
            params = {}
            for param_name in BREW_PARAMS:
                if param_name in call.data:
                    params[param_name] = call.data[param_name]

            for eid, edata in hass.data.get(DOMAIN, {}).items():
                dev = edata.get("device")
                if dev:
                    await hass.async_add_executor_job(
                        dev.brew_custom, beverage, params or None
                    )
                    coord = edata.get("coordinator")
                    if coord:
                        await coord.async_request_refresh()
                    break

        hass.services.async_register(DOMAIN, SERVICE_BREW, handle_brew, schema=BREW_SCHEMA)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry.

    Returns:
        True if unload was successful.
    """
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
