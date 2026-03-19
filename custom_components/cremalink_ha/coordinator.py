"""Data update coordinator for the Cremalink integration."""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from cremalink.domain.device import Device
from cremalink.parsing.properties import PropertiesSnapshot
from cremalink.parsing.recipes import RecipeSnapshot

from .const import (
    APP_ID_REFRESH_INTERVAL,
    CONNECTION_CLOUD,
    DOMAIN,
    FAST_SCAN_INTERVAL,
    PROPERTIES_SCAN_INTERVAL,
    SLOW_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

class CremalinkCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Cremalink device."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: Device,
        connection_type: str = "",
        fast_scan_interval: int = FAST_SCAN_INTERVAL,
        slow_scan_interval: int = SLOW_SCAN_INTERVAL,
        app_refresh_interval: int = APP_ID_REFRESH_INTERVAL,
    ):
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
            update_interval=timedelta(seconds=fast_scan_interval),
        )
        self.device = device
        self.connection_type = connection_type
        self._app_id_activated = False
        self._fast_scan_interval = timedelta(seconds=fast_scan_interval)
        self._slow_scan_interval = timedelta(seconds=slow_scan_interval)
        self._app_refresh_interval = app_refresh_interval
        self.last_error: str | None = None

    def apply_options(
        self,
        fast_scan_interval: int,
        slow_scan_interval: int,
        app_refresh_interval: int,
    ) -> None:
        """Update coordinator timing from config entry options."""
        self._fast_scan_interval = timedelta(seconds=fast_scan_interval)
        self._slow_scan_interval = timedelta(seconds=slow_scan_interval)
        self._app_refresh_interval = app_refresh_interval
        self.update_interval = self._fast_scan_interval

    async def _async_ensure_app_connection(self) -> None:
        """Activate and periodically refresh the app connection for cloud devices.

        The machine only pushes live monitor data when an app has registered
        via the app_id property. This ensures the connection stays active.
        """
        if self.connection_type != CONNECTION_CLOUD:
            return

        try:
            result = await self.hass.async_add_executor_job(
                self.device.ensure_app_connection,
                self._app_refresh_interval,
            )
            if result and not self._app_id_activated:
                _LOGGER.info("App connection activated successfully")
            elif not result:
                _LOGGER.warning(
                    "App connection activation returned False; monitor data may be stale"
                )
            self._app_id_activated = result
        except Exception as err:
            self._app_id_activated = False
            _LOGGER.warning("Failed to activate app connection: %s", err)

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
                    self.update_interval = self._slow_scan_interval
                elif status is not None:
                    self.update_interval = self._fast_scan_interval

            self.last_error = None
            return data
        except Exception as err:
            self.last_error = str(err)
            raise UpdateFailed(f"Error communicating with device: {err}") from err


@dataclass
class PropertiesData:
    """Parsed results from a properties fetch."""

    received_at: Optional[datetime] = None
    counters: dict[str, int] = field(default_factory=dict)
    aggregate_counters: dict[str, int] = field(default_factory=dict)
    profile_names: dict[int, str] = field(default_factory=dict)
    recipes: list[RecipeSnapshot] = field(default_factory=list)
    maintenance: dict[str, int] = field(default_factory=dict)
    favorites: dict[int, list[str]] = field(default_factory=dict)
    machine_settings: dict[str, int] = field(default_factory=dict)
    active_profile: Optional[int] = None
    recipe_priority: dict[int, list[str]] = field(default_factory=dict)
    serial_number: Optional[str] = None
    bean_system: dict[int, str] = field(default_factory=dict)
    service_parameters: dict[str, Any] = field(default_factory=dict)
    json_counters: dict[str, int] = field(default_factory=dict)
    software_version: Optional[str] = None


class CremalinkPropertiesCoordinator(DataUpdateCoordinator[PropertiesData]):
    """Slow-polling coordinator for cloud properties (counters, profiles, recipes)."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: Device,
        properties_scan_interval: int = PROPERTIES_SCAN_INTERVAL,
    ) -> None:
        """Initialize the properties coordinator.

        Args:
            hass: The Home Assistant instance.
            device: The Cremalink device instance.
        """
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_properties",
            update_interval=timedelta(seconds=properties_scan_interval),
        )
        self.device = device
        self.last_error: str | None = None

    def apply_options(self, properties_scan_interval: int) -> None:
        """Update the properties polling interval from entry options."""
        self.update_interval = timedelta(seconds=properties_scan_interval)

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
            result = PropertiesData(
                received_at=snapshot.received_at,
                counters=snapshot.get_counters(),
                aggregate_counters=snapshot.get_aggregate_counters(),
                profile_names=snapshot.get_profile_names(),
                recipes=snapshot.get_recipes(),
                maintenance=snapshot.get_maintenance(),
                favorites=snapshot.get_favorites(),
                machine_settings=snapshot.get_machine_settings(),
                active_profile=snapshot.get_active_profile(),
                recipe_priority=snapshot.get_recipe_priority(),
                serial_number=snapshot.get_serial_number(),
                bean_system=snapshot.get_bean_system(),
                service_parameters=snapshot.get_service_parameters(),
                json_counters=snapshot.get_json_counters(),
                software_version=snapshot.get_software_version(),
            )
            self.last_error = None
            return result
        except Exception as err:
            self.last_error = str(err)
            raise UpdateFailed(f"Error fetching properties: {err}") from err
