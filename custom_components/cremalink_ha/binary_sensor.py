"""Binary sensor platform for the Cremalink integration."""
from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_FILTER_ALERT_THRESHOLD,
    CONF_GROUNDS_ALERT_THRESHOLD,
    DOMAIN,
    FILTER_ALERT_THRESHOLD,
    GROUNDS_ALERT_THRESHOLD,
)

MONITOR_BINARY_SENSORS = [
    ("is_busy", "Busy", None, BinarySensorDeviceClass.RUNNING),
    ("is_idle", "Idle", "mdi:sleep", None),
    ("is_watertank_open", "Water Tank Open", "mdi:water-boiler-alert", BinarySensorDeviceClass.DOOR),
    ("is_watertank_empty", "Water Tank Empty", "mdi:water-off", BinarySensorDeviceClass.PROBLEM),
    ("is_waste_container_full", "Waste Container Full", "mdi:delete-alert", BinarySensorDeviceClass.PROBLEM),
    ("is_waste_container_missing", "Waste Container Missing", "mdi:delete-alert", BinarySensorDeviceClass.PROBLEM),
]


def _device_info(entry) -> DeviceInfo:
    """Build the device info for a config entry."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="cremalink",
    )


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the binary sensor platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    properties_coordinator = data.get("properties_coordinator")

    entities: list[BinarySensorEntity] = [
        CremalinkBinarySensor(coordinator, entry, key, name, icon, dev_class)
        for key, name, icon, dev_class in MONITOR_BINARY_SENSORS
    ]

    if properties_coordinator:
        entities.extend(
            [
                CremalinkMaintenanceBinarySensor(
                    properties_coordinator,
                    entry,
                    "grounds_attention",
                    "Grounds Container Attention",
                    "mdi:delete-alert",
                    lambda: _grounds_attention(entry, properties_coordinator.data),
                    lambda: {
                        "grounds_container_percent": _maintenance_value(
                            properties_coordinator.data,
                            "grounds_container",
                        ),
                        "threshold_percent": _grounds_threshold(entry),
                    },
                ),
                CremalinkMaintenanceBinarySensor(
                    properties_coordinator,
                    entry,
                    "filter_attention",
                    "Water Filter Attention",
                    "mdi:filter-alert",
                    lambda: _filter_attention(entry, properties_coordinator.data),
                    lambda: {
                        "water_filter_percent": _maintenance_value(
                            properties_coordinator.data,
                            "water_filter",
                        ),
                        "threshold_percent": _filter_threshold(entry),
                    },
                ),
                CremalinkMaintenanceBinarySensor(
                    properties_coordinator,
                    entry,
                    "descaling_attention",
                    "Descaling Attention",
                    "mdi:wrench",
                    lambda: _descaling_attention(
                        properties_coordinator.data,
                        coordinator.data,
                    ),
                    lambda: {
                        "descale_progress_percent": _maintenance_value(
                            properties_coordinator.data,
                            "descale_progress",
                        ),
                        "descale_status": _service_parameter_value(
                            properties_coordinator.data,
                            "descale_status",
                        ),
                    },
                ),
                CremalinkMaintenanceBinarySensor(
                    properties_coordinator,
                    entry,
                    "maintenance_attention",
                    "Maintenance Attention",
                    "mdi:alert-decagram-outline",
                    lambda: any(
                        (
                            _grounds_attention(entry, properties_coordinator.data),
                            _filter_attention(entry, properties_coordinator.data),
                            _descaling_attention(
                                properties_coordinator.data,
                                coordinator.data,
                            ),
                        )
                    ),
                    lambda: {
                        "grounds_attention": _grounds_attention(
                            entry,
                            properties_coordinator.data,
                        ),
                        "filter_attention": _filter_attention(
                            entry,
                            properties_coordinator.data,
                        ),
                        "descaling_attention": _descaling_attention(
                            properties_coordinator.data,
                            coordinator.data,
                        ),
                    },
                ),
            ]
        )

    async_add_entities(entities)


def _grounds_threshold(entry) -> int:
    """Return the configured grounds threshold percentage."""
    return int(entry.options.get(CONF_GROUNDS_ALERT_THRESHOLD, GROUNDS_ALERT_THRESHOLD))


def _filter_threshold(entry) -> int:
    """Return the configured filter threshold percentage."""
    return int(entry.options.get(CONF_FILTER_ALERT_THRESHOLD, FILTER_ALERT_THRESHOLD))


def _maintenance_value(data, key: str):
    """Return a maintenance metric from properties data."""
    if not data:
        return None
    return data.maintenance.get(key)


def _service_parameter_value(data, key: str):
    """Return a service parameter from properties data."""
    if not data:
        return None
    return data.service_parameters.get(key)


def _grounds_attention(entry, properties_data) -> bool:
    """Return True when the grounds percentage crosses the configured threshold."""
    value = _maintenance_value(properties_data, "grounds_container")
    return value is not None and int(value) >= _grounds_threshold(entry)


def _filter_attention(entry, properties_data) -> bool:
    """Return True when the filter percentage falls below the configured threshold."""
    value = _maintenance_value(properties_data, "water_filter")
    return value is not None and int(value) <= _filter_threshold(entry)


def _descaling_attention(properties_data, monitor_data) -> bool:
    """Return True when the machine reports descale-related activity or status."""
    progress = _maintenance_value(properties_data, "descale_progress")
    if progress is not None and int(progress) > 0:
        return True

    descale_status = _service_parameter_value(properties_data, "descale_status")
    if descale_status is not None:
        normalized = str(descale_status).strip().lower()
        if normalized not in {"", "0", "false", "idle", "none", "off"}:
            return True

    status_name = (getattr(monitor_data, "status_name", None) or "").lower()
    return "descal" in status_name


class CremalinkBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a monitor-backed Cremalink binary sensor."""

    def __init__(self, coordinator, entry, key, name, icon, dev_class):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = f"{entry.title} {name}"
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_icon = icon
        self._attr_device_class = dev_class
        self._attr_device_info = _device_info(entry)

    @property
    def available(self):
        """Return True if the binary sensor is available."""
        if not self.coordinator.data:
            return False
        return super().available

    @property
    def is_on(self):
        """Return True if the binary sensor is on."""
        return getattr(self.coordinator.data, self._key, None)


class CremalinkMaintenanceBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a properties-backed maintenance/problem sensor."""

    def __init__(
        self,
        coordinator,
        entry,
        key: str,
        name: str,
        icon: str,
        value_fn: Callable[[], bool],
        attrs_fn: Callable[[], dict],
    ) -> None:
        super().__init__(coordinator)
        self._value_fn = value_fn
        self._attrs_fn = attrs_fn
        self._attr_name = f"{entry.title} {name}"
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_icon = icon
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM
        self._attr_device_info = _device_info(entry)

    @property
    def available(self):
        """Return True if the binary sensor is available."""
        if not self.coordinator.data:
            return False
        return super().available

    @property
    def is_on(self):
        """Return True if the binary sensor is on."""
        return self._value_fn()

    @property
    def extra_state_attributes(self):
        """Return contextual maintenance attributes."""
        return self._attrs_fn()
