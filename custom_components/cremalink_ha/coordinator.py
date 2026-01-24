"""Data update coordinator for the Cremalink integration."""
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from cremalink.domain.device import Device

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class CremalinkCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Cremalink device."""

    def __init__(self, hass: HomeAssistant, device: Device):
        """Initialize the coordinator.

        Args:
            hass: The Home Assistant instance.
            device: The Cremalink device instance.
        """
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            # Poll the device every second for updates
            update_interval=timedelta(seconds=1),
        )
        self.device = device

    async def _async_update_data(self):
        """Fetch data from the device.

        Returns:
            The monitoring data from the device.

        Raises:
            UpdateFailed: If there is an error communicating with the device.
        """
        try:
            return await self.hass.async_add_executor_job(self.device.get_monitor)
        except Exception as err:
            raise UpdateFailed(f"Error communicating with device: {err}") from err
