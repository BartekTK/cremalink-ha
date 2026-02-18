"""Data update coordinator for the Cremalink integration."""
import logging
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from cremalink.domain.device import Device
from cremalink.parsing.properties import PropertiesSnapshot
from cremalink.parsing.recipes import RecipeSnapshot

from .const import DOMAIN, CONNECTION_CLOUD, APP_ID_REFRESH_INTERVAL, PROPERTIES_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL_FAST = timedelta(seconds=1)
SCAN_INTERVAL_SLOW = timedelta(seconds=30)

class CremalinkCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Cremalink device."""

    def __init__(self, hass: HomeAssistant, device: Device, connection_type: str = ""):
        """Initialize the coordinator.

        Args:
            hass: The Home Assistant instance.
            device: The Cremalink device instance.
            connection_type: The connection type ("local" or "cloud").
        """
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            # Poll the device every second for updates
            update_interval=SCAN_INTERVAL_FAST,
        )
        self.device = device
        self.connection_type = connection_type
        self._app_id_activated = False
        self._last_app_id_refresh: float = 0

    async def _async_ensure_app_connection(self) -> None:
        """Activate and periodically refresh the app connection for cloud devices.

        The machine only pushes live monitor data when an app has registered
        via the app_id property. This ensures the connection stays active.
        """
        if self.connection_type != CONNECTION_CLOUD:
            return

        now = time.monotonic()

        if not self._app_id_activated:
            _LOGGER.debug("Activating app connection for live monitor data")
            try:
                result = await self.hass.async_add_executor_job(
                    self.device.activate_app_connection
                )
                self._app_id_activated = True
                self._last_app_id_refresh = now
                if result:
                    _LOGGER.info("App connection activated successfully")
                else:
                    _LOGGER.warning("App connection activation returned False; monitor data may be stale")
            except Exception as err:
                _LOGGER.warning("Failed to activate app connection: %s", err)
                return

        elif now - self._last_app_id_refresh > APP_ID_REFRESH_INTERVAL:
            try:
                await self.hass.async_add_executor_job(self.device._refresh_app_id)
                self._last_app_id_refresh = now
            except Exception as err:
                _LOGGER.debug("App ID refresh failed (will retry): %s", err)

    async def _async_update_data(self):
        """Fetch data from the device.

        Returns:
            The monitoring data from the device.

        Raises:
            UpdateFailed: If there is an error communicating with the device.
        """
        try:
            # Ensure app connection is active for cloud devices.
            await self._async_ensure_app_connection()

            data = await self.hass.async_add_executor_job(self.device.get_monitor)

            if data and hasattr(data, 'parsed') and isinstance(data.parsed, dict):
                status = data.parsed.get("status")
                if status == 0:  # if in standby, poll slowly
                    self.update_interval = SCAN_INTERVAL_SLOW
                elif status is not None:
                    self.update_interval = SCAN_INTERVAL_FAST

            return data
        except Exception as err:
            raise UpdateFailed(f"Error communicating with device: {err}") from err


@dataclass
class PropertiesData:
    """Parsed results from a properties fetch."""

    counters: dict[str, int] = field(default_factory=dict)
    profile_names: dict[int, str] = field(default_factory=dict)
    recipes: list[RecipeSnapshot] = field(default_factory=list)


class CremalinkPropertiesCoordinator(DataUpdateCoordinator[PropertiesData]):
    """Slow-polling coordinator for cloud properties (counters, profiles, recipes)."""

    def __init__(self, hass: HomeAssistant, device: Device) -> None:
        """Initialize the properties coordinator.

        Args:
            hass: The Home Assistant instance.
            device: The Cremalink device instance.
        """
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_properties",
            update_interval=timedelta(seconds=PROPERTIES_SCAN_INTERVAL),
        )
        self.device = device

    async def _async_update_data(self) -> PropertiesData:
        """Fetch and parse cloud properties.

        Returns:
            Parsed properties data with counters, profile names, and recipes.

        Raises:
            UpdateFailed: If there is an error communicating with the device.
        """
        try:
            snapshot: PropertiesSnapshot = await self.hass.async_add_executor_job(
                self.device.get_properties
            )
            return PropertiesData(
                counters=snapshot.get_counters(),
                profile_names=snapshot.get_profile_names(),
                recipes=snapshot.get_recipes(),
            )
        except Exception as err:
            raise UpdateFailed(f"Error fetching properties: {err}") from err
