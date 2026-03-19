"""Sensor platform for the Cremalink integration."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTime, UnitOfVolume
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from cremalink.domain.beverages import BeverageCatalog, BeverageCategory

from .const import CONNECTION_CLOUD, CONF_CONNECTION_TYPE, DOMAIN

SENSORS = [
    ("status_name", "Status", "mdi:coffee-maker", None),
    ("progress_percent", "Progress", "mdi:progress-clock", PERCENTAGE),
    ("accessory_name", "Accessory", "mdi:cup", None),
]

MAINTENANCE_SENSORS = [
    ("grounds_container", "Grounds Container", "mdi:delete-variant", PERCENTAGE, None),
    ("descale_progress", "Descale Progress", "mdi:progress-wrench", PERCENTAGE, None),
    ("water_filter", "Water Filter", "mdi:water-check", PERCENTAGE, None),
    (
        "water_since_descale",
        "Water Since Descale",
        "mdi:water-alert",
        UnitOfVolume.LITERS,
        EntityCategory.DIAGNOSTIC,
    ),
    ("grounds_count", "Total Grounds Emptied", "mdi:counter", "uses", EntityCategory.DIAGNOSTIC),
    ("total_descale_cycles", "Total Descale Cycles", "mdi:wrench-clock", "cycles", EntityCategory.DIAGNOSTIC),
    (
        "total_water_dispensed",
        "Total Water Dispensed",
        "mdi:water-pump",
        UnitOfVolume.LITERS,
        EntityCategory.DIAGNOSTIC,
    ),
    (
        "total_filter_replacements",
        "Total Filter Replacements",
        "mdi:filter-check",
        "times",
        EntityCategory.DIAGNOSTIC,
    ),
    (
        "water_since_filter",
        "Water Since Filter Change",
        "mdi:water-sync",
        UnitOfVolume.LITERS,
        EntityCategory.DIAGNOSTIC,
    ),
    ("water_hardness_setting", "Water Hardness Setting", "mdi:water", None, EntityCategory.DIAGNOSTIC),
]

SERVICE_PARAM_SENSORS = [
    ("descale_status", "Descale Status", "mdi:wrench-cog", None),
    ("last_4_water_calc_qty", "Last 4 Descale Water", "mdi:water-thermometer", UnitOfVolume.LITERS),
    ("last_4_calc_threshold", "Descale Threshold", "mdi:gauge", None),
    ("water_steamer_calc_rel_qty", "Steamer Water (Relative)", "mdi:pipe-valve", UnitOfVolume.LITERS),
    ("water_heater_calc_abs_qty", "Heater Water (Total)", "mdi:water-boiler", UnitOfVolume.LITERS),
    ("water_steamer_calc_abs_qty", "Steamer Water (Total)", "mdi:pipe-valve", UnitOfVolume.LITERS),
    (
        "water_cold_branch_calc_rel_qty",
        "Cold Branch Water (Relative)",
        "mdi:snowflake-thermometer",
        UnitOfVolume.LITERS,
    ),
    (
        "water_cold_branch_calc_abs_qty",
        "Cold Branch Water (Total)",
        "mdi:snowflake-thermometer",
        UnitOfVolume.LITERS,
    ),
]

SETTINGS_DISPLAY = {
    "temperature": ("Temperature Setting", "mdi:thermometer"),
    "auto_off": ("Auto-Off Timer", "mdi:timer-off-outline"),
    "water_hardness": ("Water Hardness Config", "mdi:water-opacity"),
}

PROFILE_SLOTS = range(1, 5)
BEAN_SLOTS = range(0, 7)

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


def _device_info(entry) -> DeviceInfo:
    """Build the device info for a config entry."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="cremalink",
    )


def _normalize_datetime(value: datetime | None) -> datetime | None:
    """Convert naive datetimes from the library into HA-aware UTC values."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE or dt_util.UTC)
    return dt_util.as_utc(value)


def _monitor_received_at(view) -> datetime | None:
    """Return a normalized monitor timestamp."""
    return _normalize_datetime(getattr(view, "received_at", None))


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the sensor platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    properties_coordinator = data.get("properties_coordinator")
    device = data["device"]

    entities: list[SensorEntity] = [
        CremalinkSensor(coordinator, entry, key, name, icon, unit)
        for key, name, icon, unit in SENSORS
    ]

    entities.extend(
        [
            CremalinkComputedSensor(
                coordinator,
                entry,
                "connection_type",
                "Connection Type",
                "mdi:connection",
                lambda: entry.data.get(CONF_CONNECTION_TYPE),
                allow_without_data=True,
            ),
            CremalinkComputedSensor(
                coordinator,
                entry,
                "transport_type",
                "Transport Type",
                "mdi:swap-horizontal",
                lambda: device.transport.__class__.__name__,
                allow_without_data=True,
            ),
            CremalinkComputedSensor(
                coordinator,
                entry,
                "device_ip",
                "Device IP",
                "mdi:ip-network",
                lambda: getattr(device, "ip", None),
                allow_without_data=True,
            ),
            CremalinkComputedSensor(
                coordinator,
                entry,
                "monitor_source",
                "Monitor Source",
                "mdi:database-arrow-right",
                lambda: getattr(getattr(coordinator.data, "snapshot", None), "source", None),
            ),
            CremalinkComputedSensor(
                coordinator,
                entry,
                "monitor_age",
                "Monitor Age",
                "mdi:timer-sand",
                lambda: _monitor_age_seconds(coordinator.data),
                unit=UnitOfTime.SECONDS,
            ),
            CremalinkComputedSensor(
                coordinator,
                entry,
                "last_monitor_update",
                "Last Monitor Update",
                "mdi:clock-outline",
                lambda: _monitor_received_at(coordinator.data),
                device_class=SensorDeviceClass.TIMESTAMP,
            ),
            CremalinkComputedSensor(
                coordinator,
                entry,
                "cloud_session_state",
                "Cloud Session State",
                "mdi:cloud-lock",
                lambda: _cloud_session_state(coordinator),
                allow_without_data=True,
            ),
            CremalinkComputedSensor(
                coordinator,
                entry,
                "last_monitor_error",
                "Last Monitor Error",
                "mdi:alert-circle-outline",
                lambda: coordinator.last_error,
                allow_without_data=True,
            ),
        ]
    )

    dynamic_keys = {
        "counters": set(),
        "aggregate": set(),
        "json": set(),
    }

    if properties_coordinator:
        entities.extend(_build_static_property_entities(properties_coordinator, entry))
        entities.extend(
            [
                CremalinkComputedSensor(
                    properties_coordinator,
                    entry,
                    "last_properties_error",
                    "Last Properties Error",
                    "mdi:alert-circle-outline",
                    lambda: properties_coordinator.last_error,
                    allow_without_data=True,
                ),
                CremalinkComputedSensor(
                    properties_coordinator,
                    entry,
                    "properties_snapshot_age",
                    "Properties Age",
                    "mdi:timer-sand",
                    lambda: _properties_age_seconds(properties_coordinator.data),
                    unit=UnitOfTime.SECONDS,
                ),
                CremalinkComputedSensor(
                    properties_coordinator,
                    entry,
                    "last_properties_update",
                    "Last Properties Update",
                    "mdi:clock-outline",
                    lambda: _normalize_datetime(
                        getattr(properties_coordinator.data, "received_at", None)
                    ),
                    device_class=SensorDeviceClass.TIMESTAMP,
                ),
            ]
        )

        def build_dynamic_property_entities() -> list[SensorEntity]:
            new_entities: list[SensorEntity] = []
            props = properties_coordinator.data
            if not props:
                return new_entities

            for bev_name in props.counters:
                if bev_name in dynamic_keys["counters"]:
                    continue
                dynamic_keys["counters"].add(bev_name)
                new_entities.append(
                    CremalinkCounterSensor(properties_coordinator, entry, bev_name)
                )

            for label in props.aggregate_counters:
                if label in dynamic_keys["aggregate"]:
                    continue
                dynamic_keys["aggregate"].add(label)
                new_entities.append(
                    CremalinkAggregateCounterSensor(properties_coordinator, entry, label)
                )

            for label in props.json_counters:
                if label in dynamic_keys["json"]:
                    continue
                dynamic_keys["json"].add(label)
                new_entities.append(
                    CremalinkJsonCounterSensor(properties_coordinator, entry, label)
                )

            return new_entities

        entities.extend(build_dynamic_property_entities())

        @callback
        def _handle_properties_update() -> None:
            new_entities = build_dynamic_property_entities()
            if new_entities:
                async_add_entities(new_entities)

        entry.async_on_unload(
            properties_coordinator.async_add_listener(_handle_properties_update)
        )

    async_add_entities(entities)


def _build_static_property_entities(properties_coordinator, entry) -> list[SensorEntity]:
    """Build sensors that should always exist when properties are supported."""
    entities: list[SensorEntity] = []

    for profile_num in PROFILE_SLOTS:
        entities.append(
            CremalinkProfileSensor(properties_coordinator, entry, profile_num)
        )

    for key, name, icon, unit, entity_category in MAINTENANCE_SENSORS:
        entities.append(
            CremalinkMaintenanceSensor(
                properties_coordinator,
                entry,
                key,
                name,
                icon,
                unit,
                entity_category,
            )
        )

    for setting_key, (display_name, icon) in SETTINGS_DISPLAY.items():
        entities.append(
            CremalinkSettingSensor(
                properties_coordinator,
                entry,
                setting_key,
                display_name,
                icon,
            )
        )

    entities.append(CremalinkActiveProfileSensor(properties_coordinator, entry))

    for key, display_name, icon, unit in SERVICE_PARAM_SENSORS:
        entities.append(
            CremalinkServiceParamSensor(
                properties_coordinator,
                entry,
                key,
                display_name,
                icon,
                unit,
            )
        )

    for slot in BEAN_SLOTS:
        entities.append(CremalinkBeanSystemSensor(properties_coordinator, entry, slot))

    entities.extend(
        [
            CremalinkDiagnosticSensor(
                properties_coordinator,
                entry,
                "serial_number",
                "Serial Number",
                "mdi:barcode",
                lambda d: d.serial_number,
            ),
            CremalinkDiagnosticSensor(
                properties_coordinator,
                entry,
                "software_version",
                "Firmware Version",
                "mdi:chip",
                lambda d: d.software_version,
            ),
        ]
    )

    return entities


def _monitor_age_seconds(view) -> int | None:
    """Return the age of the current monitor snapshot in seconds."""
    received_at = _monitor_received_at(view)
    if received_at is None:
        return None
    return max(int((dt_util.utcnow() - received_at).total_seconds()), 0)


def _properties_age_seconds(data) -> int | None:
    """Return the age of the current properties snapshot in seconds."""
    if not data:
        return None
    received_at = _normalize_datetime(getattr(data, "received_at", None))
    if received_at is None:
        return None
    return max(int((dt_util.utcnow() - received_at).total_seconds()), 0)


def _cloud_session_state(coordinator) -> str:
    """Expose the live cloud monitor session state."""
    if coordinator.connection_type != CONNECTION_CLOUD:
        return "not_required"
    if not coordinator.device.property_map.get("app_id"):
        return "not_required"
    return "active" if getattr(coordinator, "_app_id_activated", False) else "inactive"


class CremalinkSensor(CoordinatorEntity, SensorEntity):
    """Representation of a basic Cremalink monitor sensor."""

    def __init__(self, coordinator, entry, key, name, icon, unit):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = f"{entry.title} {name}"
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        self._attr_device_info = _device_info(entry)

    @property
    def available(self):
        """Return True if entity is available."""
        if not self.coordinator.data:
            return False
        return super().available

    @property
    def native_value(self):
        """Return the current value."""
        return getattr(self.coordinator.data, self._key, None)


class CremalinkComputedSensor(CoordinatorEntity, SensorEntity):
    """Computed sensor backed by a callback rather than a direct property."""

    def __init__(
        self,
        coordinator,
        entry,
        key: str,
        name: str,
        icon: str,
        value_fn: Callable[[], Any],
        *,
        unit: str | None = None,
        device_class: SensorDeviceClass | None = None,
        allow_without_data: bool = False,
    ) -> None:
        super().__init__(coordinator)
        self._value_fn = value_fn
        self._allow_without_data = allow_without_data
        self._attr_name = f"{entry.title} {name}"
        self._attr_unique_id = f"{entry.entry_id}_computed_{key}"
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = _device_info(entry)

    @property
    def available(self):
        """Return True if entity is available."""
        if self._allow_without_data:
            return True
        if not self.coordinator.data:
            return False
        return super().available

    @property
    def native_value(self):
        """Return the current computed value."""
        return self._value_fn()


class CremalinkCounterSensor(CoordinatorEntity, SensorEntity):
    """Beverage usage counter sensor."""

    def __init__(self, coordinator, entry, bev_name):
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
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self):
        """Return the beverage count."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.counters.get(self._bev_name, 0)


class CremalinkProfileSensor(CoordinatorEntity, SensorEntity):
    """User profile name sensor."""

    def __init__(self, coordinator, entry, profile_num):
        super().__init__(coordinator)
        self._profile_num = profile_num
        self._attr_name = f"{entry.title} Profile {profile_num}"
        self._attr_unique_id = f"{entry.entry_id}_profile_{profile_num}"
        self._attr_icon = "mdi:account"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self):
        """Return the profile name."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.profile_names.get(self._profile_num)

    @property
    def extra_state_attributes(self):
        """Return favorites and recipe priority for this profile."""
        if not self.coordinator.data:
            return None

        attrs = {
            "profile_number": self._profile_num,
        }
        favorites = self.coordinator.data.favorites.get(self._profile_num)
        if favorites:
            attrs["favorites"] = favorites
        priority = self.coordinator.data.recipe_priority.get(self._profile_num)
        if priority:
            attrs["recipe_priority"] = priority
        return attrs


class CremalinkAggregateCounterSensor(CoordinatorEntity, SensorEntity):
    """Aggregate usage counter sensor."""

    def __init__(self, coordinator, entry, label):
        super().__init__(coordinator)
        self._label = label
        display = label.replace("_", " ").title()
        self._attr_name = f"{entry.title} {display}"
        self._attr_unique_id = f"{entry.entry_id}_agg_{label}"
        self._attr_icon = "mdi:counter"
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        return self.coordinator.data.aggregate_counters.get(self._label, 0)


class CremalinkMaintenanceSensor(CoordinatorEntity, SensorEntity):
    """Maintenance metric sensor."""

    def __init__(self, coordinator, entry, key, name, icon, unit, entity_category):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = f"{entry.title} {name}"
        self._attr_unique_id = f"{entry.entry_id}_maint_{key}"
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        if entity_category:
            self._attr_entity_category = entity_category
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        return self.coordinator.data.maintenance.get(self._key)


class CremalinkSettingSensor(CoordinatorEntity, SensorEntity):
    """Machine setting sensor."""

    def __init__(self, coordinator, entry, key, name, icon):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = f"{entry.title} {name}"
        self._attr_unique_id = f"{entry.entry_id}_setting_{key}"
        self._attr_icon = icon
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        return self.coordinator.data.machine_settings.get(self._key)


class CremalinkActiveProfileSensor(CoordinatorEntity, SensorEntity):
    """Active profile sensor."""

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_name = f"{entry.title} Active Profile"
        self._attr_unique_id = f"{entry.entry_id}_active_profile"
        self._attr_icon = "mdi:account-check"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        profile_num = self.coordinator.data.active_profile
        if profile_num is None:
            return None
        name = self.coordinator.data.profile_names.get(profile_num)
        return name if name else f"Profile {profile_num}"


class CremalinkJsonCounterSensor(CoordinatorEntity, SensorEntity):
    """Counter from JSON-valued properties."""

    def __init__(self, coordinator, entry, label):
        super().__init__(coordinator)
        self._label = label
        display = label.replace("_", " ").title()
        self._attr_name = f"{entry.title} {display}"
        self._attr_unique_id = f"{entry.entry_id}_jcnt_{label}"
        self._attr_icon = "mdi:counter"
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        return self.coordinator.data.json_counters.get(self._label, 0)


class CremalinkServiceParamSensor(CoordinatorEntity, SensorEntity):
    """Service parameter sensor."""

    def __init__(self, coordinator, entry, key, name, icon, unit):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = f"{entry.title} {name}"
        self._attr_unique_id = f"{entry.entry_id}_svc_{key}"
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        return self.coordinator.data.service_parameters.get(self._key)


class CremalinkBeanSystemSensor(CoordinatorEntity, SensorEntity):
    """Bean system sensor showing the configured bean name."""

    def __init__(self, coordinator, entry, slot):
        super().__init__(coordinator)
        self._slot = slot
        self._attr_name = f"{entry.title} Bean Slot {slot}"
        self._attr_unique_id = f"{entry.entry_id}_bean_{slot}"
        self._attr_icon = "mdi:seed"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        return self.coordinator.data.bean_system.get(self._slot)


class CremalinkDiagnosticSensor(CoordinatorEntity, SensorEntity):
    """Generic diagnostic sensor driven by a value extractor function."""

    def __init__(self, coordinator, entry, key, name, icon, value_fn):
        super().__init__(coordinator)
        self._value_fn = value_fn
        self._attr_name = f"{entry.title} {name}"
        self._attr_unique_id = f"{entry.entry_id}_diag_{key}"
        self._attr_icon = icon
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        return self._value_fn(self.coordinator.data)
