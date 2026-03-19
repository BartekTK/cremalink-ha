"""Select platform for the Cremalink integration."""
from __future__ import annotations

import re

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

PROFILE_RANGE = range(1, 5)


def _device_info(entry) -> DeviceInfo:
    """Build the device info for a config entry."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="cremalink",
    )


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the select platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    properties_coordinator = data.get("properties_coordinator")

    if not properties_coordinator:
        return

    async_add_entities([CremalinkProfileSelect(properties_coordinator, entry)])


class CremalinkProfileSelect(CoordinatorEntity, SelectEntity, RestoreEntity):
    """Select entity for choosing which profile's recipes to use when brewing."""

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._selected_profile = 1
        self._attr_name = f"{entry.title} Brew Profile"
        self._attr_unique_id = f"{entry.entry_id}_brew_profile"
        self._attr_icon = "mdi:account-switch"
        self._attr_device_info = _device_info(entry)

    def _profile_names(self) -> dict[int, str]:
        """Return current profile names with generic fallbacks."""
        names = {
            profile_num: f"Profile {profile_num}"
            for profile_num in PROFILE_RANGE
        }
        if self.coordinator.data:
            for profile_num, name in self.coordinator.data.profile_names.items():
                if name:
                    names[profile_num] = name
        return names

    async def async_added_to_hass(self) -> None:
        """Restore previous selection on startup."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state:
            self._selected_profile = self._restore_profile_number(last_state.state)
        self.hass.data[DOMAIN][self._entry_id]["selected_profile"] = self._selected_profile

    def _restore_profile_number(self, value: str) -> int:
        """Restore a profile number from either a name or generic label."""
        for num, name in self._profile_names().items():
            if name == value:
                return num
        match = re.fullmatch(r"Profile (\d+)", value)
        if match:
            profile_num = int(match.group(1))
            if profile_num in PROFILE_RANGE:
                return profile_num
        return 1

    @property
    def options(self) -> list[str]:
        """Return list of profile names as options."""
        names = self._profile_names()
        return [names[i] for i in PROFILE_RANGE]

    @property
    def current_option(self) -> str | None:
        """Return the currently selected profile name."""
        return self._profile_names().get(
            self._selected_profile,
            f"Profile {self._selected_profile}",
        )

    async def async_select_option(self, option: str) -> None:
        """Handle profile selection."""
        for num, name in self._profile_names().items():
            if name == option:
                self._selected_profile = num
                break

        self.hass.data[DOMAIN][self._entry_id]["selected_profile"] = self._selected_profile
        self.async_write_ha_state()
