"""Number platform for SolarFlow2400-API (writable numeric properties).

Ranges marked "verified" are taken directly from the zenSDK property table.
Ranges marked "UI bound" are NOT specified by Zendure; they are only slider
limits in the UI - the device enforces its own real limits. Adjust them here
if your model differs (e.g. SolarFlow800 vs 2400 Pro).
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, PERCENTAGE, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ZendureConfigEntry, ZendureCoordinator
from .entity import ZendureDeviceEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class ZendureNumberEntityDescription(NumberEntityDescription):
    """Description for a writable numeric property."""

    read_scale: float = 1.0
    write_scale: float = 1.0


NUMBERS: tuple[ZendureNumberEntityDescription, ...] = (
    ZendureNumberEntityDescription(
        key="outputLimit",  # RW, W. Upper bound is a UI bound (not in doc).
        name="outputLimit",
        native_unit_of_measurement=UnitOfPower.WATT,
        native_min_value=0,
        native_max_value=2400,
        native_step=100,
        mode=NumberMode.BOX,
    ),
    ZendureNumberEntityDescription(
        key="inputLimit",  # RW, W (AC charge limit). UI bound.
        name="inputLimit",
        native_unit_of_measurement=UnitOfPower.WATT,
        native_min_value=0,
        native_max_value=2400,
        native_step=100,
        mode=NumberMode.BOX,
    ),
    ZendureNumberEntityDescription(
        key="inverseMaxPower",  # RW, W (max inverter output). UI bound.
        name="inverseMaxPower",
        native_unit_of_measurement=UnitOfPower.WATT,
        native_min_value=0,
        native_max_value=2400,
        native_step=100,
        mode=NumberMode.BOX,
        entity_registry_enabled_default=False,
    ),
    ZendureNumberEntityDescription(
        key="socSet",  # RW, % 70-100 (verified).
        name="socSet",
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=70,
        native_max_value=100,
        native_step=1,
        mode=NumberMode.SLIDER,
        read_scale=0.1,
        write_scale=10.0,
    ),
    ZendureNumberEntityDescription(
        key="minSoc",  # RW, % 0-50 (verified).
        name="minSoc",
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=0,
        native_max_value=50,
        native_step=1,
        mode=NumberMode.SLIDER,
        read_scale=0.1,
        write_scale=10.0,
    ),
    ZendureNumberEntityDescription(
        key="batCalTime",  # RW, minutes. "Unauthorized modifications not recommended."
        name="batCalTime",
        native_min_value=0,
        native_max_value=1440,
        native_step=1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZendureConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Zendure number entities for writable properties present on the device."""
    coordinator = entry.runtime_data
    async_add_entities(
        ZendureNumber(coordinator, description)
        for description in NUMBERS
        if description.key in coordinator.data.device
    )


class ZendureNumber(ZendureDeviceEntity, NumberEntity):
    """A writable numeric property."""

    entity_description: ZendureNumberEntityDescription

    def __init__(
        self,
        coordinator: ZendureCoordinator,
        description: ZendureNumberEntityDescription,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        """Return the current value reported by the device."""
        raw = self.native_property_value
        try:
            return (
                float(raw) * self.entity_description.read_scale
                if raw is not None
                else None
            )
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Write the new value to the device (integer, per zenSDK)."""
        raw_value = round(value * self.entity_description.write_scale)
        await self.coordinator.async_write_property(self._key, raw_value)
