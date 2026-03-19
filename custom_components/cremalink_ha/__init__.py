"""The Cremalink Home Assistant integration."""
import logging
from functools import partial
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from cremalink import create_local_device, device_map, Client
from cremalink.domain.beverages import BeverageCatalog

from .const import *
from .coordinator import CremalinkCoordinator, CremalinkPropertiesCoordinator

_LOGGER = logging.getLogger(__name__)
_CATALOG = BeverageCatalog()

PLATFORMS = [Platform.SWITCH, Platform.BUTTON, Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SELECT]

BREW_SCHEMA = vol.Schema({
    vol.Required("beverage"): cv.string,
    vol.Optional(CONF_DSN): cv.string,
    vol.Optional(CONF_PROFILE): vol.All(vol.Coerce(int), vol.Range(min=1, max=4)),
    vol.Optional("coffee_ml"): vol.Coerce(int),
    vol.Optional("milk_ml"): vol.Coerce(int),
    vol.Optional("water_ml"): vol.Coerce(int),
    vol.Optional("temperature"): vol.Coerce(int),
    vol.Optional("taste"): vol.Coerce(int),
    vol.Optional("aroma"): vol.Coerce(int),
    vol.Optional("foam_level"): vol.Coerce(int),
    vol.Optional("milk_temp"): vol.Coerce(int),
    vol.Optional("double_shot"): vol.Coerce(int),
    vol.Optional("milk_first"): vol.Coerce(int),
    vol.Optional("pre_brew"): vol.Coerce(int),
    vol.Optional("ice_amount"): vol.Coerce(int),
    vol.Optional("cups_count"): vol.Coerce(int),
    vol.Optional("grinder"): vol.Coerce(int),
})
RUN_COMMAND_SCHEMA = vol.Schema({
    vol.Required("command"): cv.string,
    vol.Optional(CONF_DSN): cv.string,
})


def _get_entry_option(entry: ConfigEntry, key: str, default: int) -> int:
    """Return an integer option from a config entry."""
    return int(entry.options.get(key, default))


def _select_entry_data(
    hass: HomeAssistant,
    requested_dsn: str | None = None,
) -> dict[str, Any]:
    """Resolve a config entry payload for a service call."""
    entry_data_map = hass.data.get(DOMAIN, {})

    if requested_dsn:
        target_entry_data = next(
            (
                edata
                for edata in entry_data_map.values()
                if getattr(edata.get("device"), "dsn", None) == requested_dsn
            ),
            None,
        )
        if target_entry_data is None:
            raise ServiceValidationError(
                f"No Cremalink device configured with dsn '{requested_dsn}'."
            )
        return target_entry_data

    if len(entry_data_map) == 1:
        return next(iter(entry_data_map.values()))

    raise ServiceValidationError(
        "Multiple Cremalink devices are configured. Provide 'dsn' in the service call."
    )


def _find_recipe_params(
    entry_data: dict[str, Any],
    beverage: str,
    profile: int | None,
) -> dict[int, int]:
    """Resolve recipe parameters for a beverage/profile pair from properties."""
    properties_coordinator = entry_data.get("properties_coordinator")
    if not properties_coordinator or not properties_coordinator.data:
        return {}

    beverage_info = _CATALOG.get_by_name(beverage)
    if not beverage_info:
        return {}

    selected_profile = profile or entry_data.get("selected_profile", 1)
    fallback = None
    for recipe in properties_coordinator.data.recipes:
        if recipe.bev_id != beverage_info.id or not recipe.params:
            continue
        if recipe.profile == selected_profile:
            return dict(recipe.params)
        if fallback is None:
            fallback = dict(recipe.params)

    return fallback or {}


async def _async_apply_entry_options(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Apply updated options to existing coordinators and refresh entities."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not entry_data:
        return

    coordinator: CremalinkCoordinator = entry_data["coordinator"]
    coordinator.apply_options(
        fast_scan_interval=_get_entry_option(entry, CONF_FAST_SCAN_INTERVAL, FAST_SCAN_INTERVAL),
        slow_scan_interval=_get_entry_option(entry, CONF_SLOW_SCAN_INTERVAL, SLOW_SCAN_INTERVAL),
        app_refresh_interval=_get_entry_option(entry, CONF_APP_ID_REFRESH_INTERVAL, APP_ID_REFRESH_INTERVAL),
    )
    await coordinator.async_request_refresh()

    properties_coordinator: CremalinkPropertiesCoordinator | None = entry_data.get("properties_coordinator")
    if properties_coordinator:
        properties_coordinator.apply_options(
            properties_scan_interval=_get_entry_option(
                entry,
                CONF_PROPERTIES_SCAN_INTERVAL,
                PROPERTIES_SCAN_INTERVAL,
            ),
        )
        await properties_coordinator.async_request_refresh()


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

    coordinator = CremalinkCoordinator(
        hass,
        device,
        connection_type,
        fast_scan_interval=_get_entry_option(entry, CONF_FAST_SCAN_INTERVAL, FAST_SCAN_INTERVAL),
        slow_scan_interval=_get_entry_option(entry, CONF_SLOW_SCAN_INTERVAL, SLOW_SCAN_INTERVAL),
        app_refresh_interval=_get_entry_option(entry, CONF_APP_ID_REFRESH_INTERVAL, APP_ID_REFRESH_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()

    entry_data: dict = {
        "coordinator": coordinator,
        "device": device,
        "selected_profile": 1,
    }

    if connection_type == CONNECTION_CLOUD:
        properties_coordinator = CremalinkPropertiesCoordinator(
            hass,
            device,
            properties_scan_interval=_get_entry_option(
                entry,
                CONF_PROPERTIES_SCAN_INTERVAL,
                PROPERTIES_SCAN_INTERVAL,
            ),
        )
        await properties_coordinator.async_config_entry_first_refresh()
        entry_data["properties_coordinator"] = properties_coordinator

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry_data
    entry.async_on_unload(entry.add_update_listener(_async_apply_entry_options))

    # Register the brew service (once, on first entry).
    if not hass.services.has_service(DOMAIN, SERVICE_BREW):
        async def handle_brew(call: ServiceCall) -> None:
            """Handle the brew service call."""
            beverage = call.data["beverage"]
            target_entry_data = _select_entry_data(hass, call.data.get(CONF_DSN))
            recipe_profile = call.data.get(CONF_PROFILE)
            params: dict[str, int] = {}
            for param_name in BREW_PARAMS:
                if param_name in call.data:
                    params[param_name] = call.data[param_name]

            dev = target_entry_data.get("device")
            if dev is None:
                raise ServiceValidationError("Cremalink device is not available.")

            merged_params = _find_recipe_params(target_entry_data, beverage, recipe_profile)
            for key, value in params.items():
                merged_params[key] = value

            await hass.async_add_executor_job(
                dev.brew_custom, beverage, merged_params or None
            )

            coord = target_entry_data.get("coordinator")
            if coord:
                await coord.async_request_refresh()

        hass.services.async_register(DOMAIN, SERVICE_BREW, handle_brew, schema=BREW_SCHEMA)

    if not hass.services.has_service(DOMAIN, SERVICE_RUN_COMMAND):
        async def handle_run_command(call: ServiceCall) -> None:
            """Handle a raw command alias service call."""
            target_entry_data = _select_entry_data(hass, call.data.get(CONF_DSN))
            dev = target_entry_data.get("device")
            if dev is None:
                raise ServiceValidationError("Cremalink device is not available.")

            await hass.async_add_executor_job(dev.do, call.data["command"])

            coord = target_entry_data.get("coordinator")
            if coord:
                await coord.async_request_refresh()

        hass.services.async_register(
            DOMAIN,
            SERVICE_RUN_COMMAND,
            handle_run_command,
            schema=RUN_COMMAND_SCHEMA,
        )

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
        if not hass.data[DOMAIN]:
            for service in (SERVICE_BREW, SERVICE_RUN_COMMAND):
                if hass.services.has_service(DOMAIN, service):
                    hass.services.async_remove(DOMAIN, service)
    return unload_ok
