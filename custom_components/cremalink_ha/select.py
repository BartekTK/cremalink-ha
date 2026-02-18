"""Select platform for the Cremalink integration."""
import logging

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the select platform.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry.
        async_add_entities: Function to add entities.
    """
    data = hass.data[DOMAIN][entry.entry_id]
    properties_coordinator = data.get("properties_coordinator")

    if not properties_coordinator:
        _LOGGER.debug("No properties coordinator, skipping select platform")
        return

    if not properties_coordinator.data:
        _LOGGER.debug("Properties coordinator has no data, skipping select platform")
        return

    profile_names = properties_coordinator.data.profile_names
    if not profile_names:
        _LOGGER.debug("No profile names found, skipping select platform")
        return

    _LOGGER.info("Creating brew profile select with profiles: %s", profile_names)
    async_add_entities([
        CremalinkProfileSelect(properties_coordinator, entry, profile_names)
    ])


class CremalinkProfileSelect(CoordinatorEntity, SelectEntity, RestoreEntity):
    """Select entity for choosing which profile's recipes to use when brewing."""

    def __init__(self, coordinator, entry, profile_names):
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._profile_names = profile_names
        self._selected_profile = 1
        self._attr_name = f"{entry.title} Brew Profile"
        self._attr_unique_id = f"{entry.entry_id}_brew_profile"
        self._attr_icon = "mdi:account-switch"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="cremalink",
        )

    async def async_added_to_hass(self) -> None:
        """Restore previous selection on startup."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state:
            # Find which profile number matches the saved state
            for num, name in self._profile_names.items():
                if name == last_state.state:
                    self._selected_profile = num
                    break
        # Store in hass.data so buttons can access it
        self.hass.data[DOMAIN][self._entry_id]["selected_profile"] = self._selected_profile

    @property
    def options(self) -> list[str]:
        """Return list of profile names as options."""
        if self.coordinator.data and self.coordinator.data.profile_names:
            names = self.coordinator.data.profile_names
        else:
            names = self._profile_names
        return [names.get(i, f"Profile {i}") for i in range(1, 5) if i in names]

    @property
    def current_option(self) -> str | None:
        """Return the currently selected profile name."""
        if self.coordinator.data and self.coordinator.data.profile_names:
            names = self.coordinator.data.profile_names
        else:
            names = self._profile_names
        return names.get(self._selected_profile, f"Profile {self._selected_profile}")

    async def async_select_option(self, option: str) -> None:
        """Handle profile selection."""
        if self.coordinator.data and self.coordinator.data.profile_names:
            names = self.coordinator.data.profile_names
        else:
            names = self._profile_names

        for num, name in names.items():
            if name == option:
                self._selected_profile = num
                break

        self.hass.data[DOMAIN][self._entry_id]["selected_profile"] = self._selected_profile
        self.async_write_ha_state()
