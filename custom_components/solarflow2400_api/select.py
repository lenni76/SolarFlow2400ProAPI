"""Select platform for SolarFlow2400-API (writable enumerated properties).

All value<->label mappings below are taken from the zenSDK property table.
Where Zendure documents the exact meaning of each integer (gridStandard,
gridOffMode) those labels are used verbatim. Where only a range is given
(gridReverse) the raw integers are shown as options.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ZendureConfigEntry, ZendureCoordinator
from .entity import ZendureDeviceEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class ZendureSelectEntityDescription(SelectEntityDescription):
    """A writable enumerated property with a label<->int mapping."""

    # Ordered mapping of display label -> integer value written to the device.
    value_map: dict[str, int] = field(default_factory=dict)


SELECTS: tuple[ZendureSelectEntityDescription, ...] = (
    ZendureSelectEntityDescription(
        # acMode RW, range 1-2, "Charge or discharge mode" (zenSDK).
        # Zendure documents the range and direction but not per-value labels
        # beyond "charge or discharge"; the raw value stays visible in each label.
        key="acMode",
        name="acMode",
        value_map={"1 (charge)": 1, "2 (discharge)": 2},
    ),
    ZendureSelectEntityDescription(
        # gridReverse RW, range 0-2, no per-value labels documented.
        key="gridReverse",
        name="gridReverse",
        value_map={"0": 0, "1": 1, "2": 2},
    ),
    ZendureSelectEntityDescription(
        # gridOffMode RW 0-2 (verified labels).
        key="gridOffMode",
        name="gridOffMode",
        value_map={"Standard": 0, "Economic": 1, "Closure": 2},
    ),
    ZendureSelectEntityDescription(
        # gridStandard RW 0-9 (verified country labels).
        key="gridStandard",
        name="gridStandard",
        value_map={
            "Germany": 0,
            "France": 1,
            "Austria": 2,
            "Switzerland": 3,
            "Netherlands": 4,
            "Spain": 5,
            "Belgium": 6,
            "Greece": 7,
            "Denmark": 8,
            "Italy": 9,
        },
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    ZendureSelectEntityDescription(
        # Fanspeed RW. Description says 0 Auto / 1 Gear1 / 2 Gear2 (note: the
        # table's Range column says 0-1, the Description says 0-2 - documented
        # discrepancy). "Unauthorized modification is not recommended."
        key="Fanspeed",
        name="Fanspeed",
        value_map={"Auto": 0, "Gear 1": 1, "Gear 2": 2},
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZendureConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Zendure select entities for writable enum properties on the device."""
    coordinator = entry.runtime_data
    async_add_entities(
        ZendureSelect(coordinator, description)
        for description in SELECTS
        if description.key in coordinator.data.device
    )


class ZendureSelect(ZendureDeviceEntity, SelectEntity):
    """A writable enumerated property."""

    entity_description: ZendureSelectEntityDescription

    def __init__(
        self,
        coordinator: ZendureCoordinator,
        description: ZendureSelectEntityDescription,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_options = list(description.value_map)
        self._label_by_value = {v: k for k, v in description.value_map.items()}

    @property
    def current_option(self) -> str | None:
        """Return the label matching the current integer value."""
        raw = self.native_property_value
        try:
            return self._label_by_value.get(int(raw)) if raw is not None else None
        except (TypeError, ValueError):
            return None

    async def async_select_option(self, option: str) -> None:
        """Write the integer value for the chosen label."""
        value = self.entity_description.value_map[option]
        await self.coordinator.async_write_property(self._key, value)
