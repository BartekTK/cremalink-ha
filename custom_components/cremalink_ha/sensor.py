"""Sensor platform for the Cremalink integration."""
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfVolume
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from cremalink.domain.beverages import BeverageCatalog, BeverageCategory

from .const import DOMAIN, CONF_CONNECTION_TYPE, CONNECTION_CLOUD

SENSORS = [
    ("status_name", "Status", "mdi:coffee-maker", None),
    ("progress_percent", "Progress", "mdi:progress-clock", PERCENTAGE),
    ("accessory_name", "Accessory", "mdi:cup", None),
]

# (key in maintenance dict, display name, icon, unit, entity_category)
MAINTENANCE_SENSORS = [
    ("grounds_container", "Grounds Container", "mdi:delete-variant", PERCENTAGE, None),
    ("water_filter", "Water Filter", "mdi:water-check", PERCENTAGE, None),
    ("water_since_descale", "Water Since Descale", "mdi:water-alert", UnitOfVolume.LITERS, EntityCategory.DIAGNOSTIC),
    ("grounds_count", "Total Grounds Emptied", "mdi:counter", "uses", EntityCategory.DIAGNOSTIC),
    ("total_water_dispensed", "Total Water Dispensed", "mdi:water-pump", UnitOfVolume.LITERS, EntityCategory.DIAGNOSTIC),
    ("water_hardness_setting", "Water Hardness Setting", "mdi:water", None, EntityCategory.DIAGNOSTIC),
]

# Machine settings display config.
SETTINGS_DISPLAY = {
    "temperature": ("Temperature Setting", "mdi:thermometer", None),
    "auto_off": ("Auto-Off Timer", "mdi:timer-off-outline", None),
    "water_hardness": ("Water Hardness Config", "mdi:water-opacity", None),
}


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
        props = properties_coordinator.data

        # Counter sensors for beverages with count > 0
        for bev_name, count in props.counters.items():
            if count > 0:
                entities.append(
                    CremalinkCounterSensor(properties_coordinator, entry, bev_name)
                )

        # Aggregate counter sensors
        for label, count in props.aggregate_counters.items():
            entities.append(
                CremalinkAggregateCounterSensor(properties_coordinator, entry, label)
            )

        # Profile sensors for populated profiles
        for profile_num, profile_name in props.profile_names.items():
            if profile_name:
                entities.append(
                    CremalinkProfileSensor(properties_coordinator, entry, profile_num)
                )

        # Maintenance sensors
        for key, name, icon, unit, cat in MAINTENANCE_SENSORS:
            if key in props.maintenance:
                entities.append(
                    CremalinkMaintenanceSensor(
                        properties_coordinator, entry, key, name, icon, unit, cat
                    )
                )

        # Machine settings sensors
        for setting_key, value in props.machine_settings.items():
            if setting_key in SETTINGS_DISPLAY:
                display_name, icon, unit = SETTINGS_DISPLAY[setting_key]
                entities.append(
                    CremalinkSettingSensor(
                        properties_coordinator, entry, setting_key, display_name, icon
                    )
                )

        # Active profile sensor
        if props.active_profile is not None:
            entities.append(
                CremalinkActiveProfileSensor(properties_coordinator, entry)
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

    @property
    def extra_state_attributes(self):
        """Return favorites for this profile as extra attributes."""
        if not self.coordinator.data:
            return None
        favorites = self.coordinator.data.favorites.get(self._profile_num)
        if favorites:
            return {"favorites": favorites}
        return None


class CremalinkAggregateCounterSensor(CoordinatorEntity, SensorEntity):
    """Aggregate usage counter sensor (e.g. total beverages, total mugs)."""

    def __init__(self, coordinator, entry, label):
        super().__init__(coordinator)
        self._label = label
        display = label.replace("_", " ").title()
        self._attr_name = f"{entry.title} {display}"
        self._attr_unique_id = f"{entry.entry_id}_agg_{label}"
        self._attr_icon = "mdi:counter"
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="cremalink",
        )

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        return self.coordinator.data.aggregate_counters.get(self._label, 0)


class CremalinkMaintenanceSensor(CoordinatorEntity, SensorEntity):
    """Maintenance metric sensor (e.g. grounds container %, water filter %)."""

    def __init__(self, coordinator, entry, key, name, icon, unit, entity_category):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = f"{entry.title} {name}"
        self._attr_unique_id = f"{entry.entry_id}_maint_{key}"
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        if entity_category:
            self._attr_entity_category = entity_category
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="cremalink",
        )

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        return self.coordinator.data.maintenance.get(self._key)


class CremalinkSettingSensor(CoordinatorEntity, SensorEntity):
    """Machine setting sensor (temperature, auto-off, water hardness)."""

    def __init__(self, coordinator, entry, key, name, icon):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = f"{entry.title} {name}"
        self._attr_unique_id = f"{entry.entry_id}_setting_{key}"
        self._attr_icon = icon
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="cremalink",
        )

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        return self.coordinator.data.machine_settings.get(self._key)


class CremalinkActiveProfileSensor(CoordinatorEntity, SensorEntity):
    """Active profile sensor — shows which profile is active on the machine."""

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        self._attr_name = f"{entry.title} Active Profile"
        self._attr_unique_id = f"{entry.entry_id}_active_profile"
        self._attr_icon = "mdi:account-check"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="cremalink",
        )

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        profile_num = self.coordinator.data.active_profile
        if profile_num is None:
            return None
        name = self.coordinator.data.profile_names.get(profile_num)
        return name if name else f"Profile {profile_num}"
