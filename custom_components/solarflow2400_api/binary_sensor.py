"""Binary sensor platform for SolarFlow2400-API (read-only 0/1 flags)."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ZendureConfigEntry, ZendureCoordinator
from .entity import ZendureDeviceEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class ZendureBinarySensorEntityDescription(BinarySensorEntityDescription):
    """A read-only 0/1 flag (on when value == 1)."""


# All keys and their 0-1 semantics come from the zenSDK "Device Data
# Properties - Read Only" table. Only clearly-typed flags get a device_class;
# the rest are conservative diagnostic booleans.
BINARY_SENSORS: tuple[ZendureBinarySensorEntityDescription, ...] = (
    ZendureBinarySensorEntityDescription(
        key="is_error",
        name="is_error",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    ZendureBinarySensorEntityDescription(
        key="gridState",
        name="gridState",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ZendureBinarySensorEntityDescription(
        key="heatState",
        name="heatState",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ZendureBinarySensorEntityDescription(
        key="pvStatus",
        name="pvStatus",
        device_class=BinarySensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    *(
        ZendureBinarySensorEntityDescription(
            key=key, name=key, entity_category=EntityCategory.DIAGNOSTIC
        )
        for key in (
            "pass",
            "reverseState",
            "socStatus",
            "dataReady",
            "lampSwitch",
            "fanSwitch",
            "dryNodeState",
        )
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZendureConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Zendure binary sensors for 0/1 flags present on the device."""
    coordinator = entry.runtime_data
    async_add_entities(
        ZendureBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
        if description.key in coordinator.data.device
    )


class ZendureBinarySensor(ZendureDeviceEntity, BinarySensorEntity):
    """A read-only boolean flag."""

    entity_description: ZendureBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: ZendureCoordinator,
        description: ZendureBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key.lower()

    @property
    def is_on(self) -> bool | None:
        """Return True when the flag equals 1."""
        raw = self.native_property_value
        try:
            return int(raw) == 1 if raw is not None else None
        except (TypeError, ValueError):
            return None
