"""Button platform for the Cremalink integration."""
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from cremalink.domain.beverages import BeverageCatalog, BeverageCategory

from .const import DOMAIN, CONF_CONNECTION_TYPE, CONNECTION_CLOUD

_CATALOG = BeverageCatalog()

# Icons by beverage category.
_CATEGORY_ICONS = {
    BeverageCategory.BLACK_COFFEE: "mdi:coffee",
    BeverageCategory.MILK_COFFEE: "mdi:glass-mug-variant",
    BeverageCategory.HOT_OTHER: "mdi:cup-water",
    BeverageCategory.ICED: "mdi:snowflake",
    BeverageCategory.MY: "mdi:star",
    BeverageCategory.MY_ICED: "mdi:star-outline",
    BeverageCategory.CARAFE: "mdi:coffee-maker-outline",
    BeverageCategory.SPECIAL: "mdi:creation",
}


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the button platform.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry.
        async_add_entities: Function to add entities.
    """
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    device = data["device"]
    properties_coordinator = data.get("properties_coordinator")

    # Get available commands from the device
    cmds = await hass.async_add_executor_job(device.get_commands)

    entities = []
    for cmd in cmds:
        # Filter out power commands as they are handled by the switch platform
        if cmd.lower() not in ["wakeup", "standby", "refresh"]:
            entities.append(
                CremalinkButton(coordinator, device, cmd, entry, properties_coordinator)
            )
    async_add_entities(entities)


class CremalinkButton(CoordinatorEntity, ButtonEntity):
    """Representation of a Cremalink button."""

    def __init__(self, coordinator, device, cmd, entry, properties_coordinator=None):
        """Initialize the button.

        Args:
            coordinator: The data update coordinator.
            device: The Cremalink device instance.
            cmd: The command associated with this button.
            entry: The config entry.
            properties_coordinator: Optional properties coordinator for recipe data.
        """
        super().__init__(coordinator)
        self.device = device
        self._cmd = cmd
        self._properties_coordinator = properties_coordinator

        # Use BeverageCatalog for proper display names and icons.
        bev_info = _CATALOG.get_by_name(cmd)
        if bev_info:
            self._title = bev_info.display_name
            self._attr_icon = _CATEGORY_ICONS.get(bev_info.category, "mdi:coffee")
        else:
            self._title = cmd.replace('_', ' ').title()
            self._attr_icon = "mdi:coffee"

        if cmd.lower() == "stop":
            self._attr_name = f"Stop"
            self._attr_icon = "mdi:stop"
        else:
            self._attr_name = f"Brew {self._title}"

        self._attr_unique_id = f"{entry.entry_id}_cmd_{cmd}"
        self._connection_type = entry.data.get(CONF_CONNECTION_TYPE)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="cremalink",
        )

    async def async_added_to_hass(self) -> None:
        """Register listener on the properties coordinator for attribute updates."""
        await super().async_added_to_hass()
        if self._properties_coordinator:
            self.async_on_remove(
                self._properties_coordinator.async_add_listener(
                    self._handle_properties_update
                )
            )

    def _handle_properties_update(self) -> None:
        """Write state when the properties coordinator refreshes."""
        self.async_write_ha_state()

    @property
    def available(self):
        """Return True if entity is available."""
        if self._cmd.lower() == "stop":
            return super().available and self.coordinator.data.is_busy
        return super().available and not self.coordinator.data.is_busy

    @property
    def extra_state_attributes(self):
        """Return recipe parameters as extra state attributes."""
        if not self._properties_coordinator or not self._properties_coordinator.data:
            return None

        bev_info = _CATALOG.get_by_name(self._cmd)
        if not bev_info:
            return None

        # Find the first recipe matching this beverage ID (profile 1 preferred).
        recipes = self._properties_coordinator.data.recipes
        match = None
        for recipe in recipes:
            if recipe.bev_id == bev_info.id:
                if recipe.profile == 1:
                    match = recipe
                    break
                if match is None:
                    match = recipe

        if not match or not match.named_params:
            return None

        return {k: v for k, v in match.named_params.items()}

    async def async_press(self):
        """Handle the button press."""
        await self.hass.async_add_executor_job(self.device.do, self._cmd)
        await self.coordinator.async_request_refresh()
