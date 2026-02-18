"""Sensor platform for the Cremalink integration."""
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from cremalink.domain.beverages import BeverageCatalog, BeverageCategory

from .const import DOMAIN, CONF_CONNECTION_TYPE, CONNECTION_CLOUD

SENSORS = [
    ("status_name", "Status", "mdi:coffee-maker", None),
    ("progress_percent", "Progress", "mdi:progress-clock", PERCENTAGE),
    ("accessory_name", "Accessory", "mdi:cup", None),
]


_CATALOG = BeverageCatalog()

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
    """Set up the sensor platform.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry.
        async_add_entities: Function to add entities.
    """
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    entities = []
    for key, name, icon, unit in SENSORS:
        entities.append(CremalinkSensor(coordinator, entry, key, name, icon, unit))

    properties_coordinator = data.get("properties_coordinator")
    if properties_coordinator and properties_coordinator.data:
        # Counter sensors for beverages with count > 0
        for bev_name, count in properties_coordinator.data.counters.items():
            if count > 0:
                entities.append(
                    CremalinkCounterSensor(properties_coordinator, entry, bev_name)
                )

        # Profile sensors for populated profiles
        for profile_num, profile_name in properties_coordinator.data.profile_names.items():
            if profile_name:
                entities.append(
                    CremalinkProfileSensor(properties_coordinator, entry, profile_num)
                )

    async_add_entities(entities)


class CremalinkSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Cremalink sensor."""

    def __init__(self, coordinator, entry, key, name, icon, unit):
        """Initialize the sensor.

        Args:
            coordinator: The data update coordinator.
            entry: The config entry.
            key: The key to identify the sensor data.
            name: The name of the sensor.
            icon: The icon for the sensor.
            unit: The unit of measurement for the sensor.
        """
        super().__init__(coordinator)
        self._key = key
        self._attr_name = f"{entry.title} {name}"
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        self._connection_type = entry.data.get(CONF_CONNECTION_TYPE)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="cremalink",
        )

    @property
    def available(self):
        """Return True if entity is available."""
        if not self.coordinator.data:
            return False
        return super().available

    @property
    def native_value(self):
        """Return the value of the sensor."""
        return getattr(self.coordinator.data, self._key, None)


class CremalinkCounterSensor(CoordinatorEntity, SensorEntity):
    """Beverage usage counter sensor (e.g. 948 espressos)."""

    def __init__(self, coordinator, entry, bev_name):
        """Initialize the counter sensor.

        Args:
            coordinator: The properties data update coordinator.
            entry: The config entry.
            bev_name: The snake_case beverage name (key in counters dict).
        """
        super().__init__(coordinator)
        self._bev_name = bev_name

        bev_info = _CATALOG.get_by_name(bev_name)
        if bev_info:
            display = bev_info.display_name
            self._attr_icon = _CATEGORY_ICONS.get(bev_info.category, "mdi:coffee")
        else:
            display = bev_name.replace("_", " ").title()
            self._attr_icon = "mdi:coffee"

        self._attr_name = f"{entry.title} {display} Count"
        self._attr_unique_id = f"{entry.entry_id}_counter_{bev_name}"
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_unit_of_measurement = "cups"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="cremalink",
        )

    @property
    def native_value(self):
        """Return the beverage count."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.counters.get(self._bev_name, 0)


class CremalinkProfileSensor(CoordinatorEntity, SensorEntity):
    """User profile name sensor (e.g. Profile 1 = "Bartek")."""

    def __init__(self, coordinator, entry, profile_num):
        """Initialize the profile sensor.

        Args:
            coordinator: The properties data update coordinator.
            entry: The config entry.
            profile_num: The profile slot number (1-4).
        """
        super().__init__(coordinator)
        self._profile_num = profile_num
        self._attr_name = f"{entry.title} Profile {profile_num}"
        self._attr_unique_id = f"{entry.entry_id}_profile_{profile_num}"
        self._attr_icon = "mdi:account"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="cremalink",
        )

    @property
    def native_value(self):
        """Return the profile name."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.profile_names.get(self._profile_num)
