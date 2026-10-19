"""Switch platform for SolarFlow2400-API (writable 0/1 properties)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ZendureConfigEntry, ZendureCoordinator
from .entity import ZendureDeviceEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class ZendureSwitchEntityDescription(SwitchEntityDescription):
    """A writable boolean (0/1) property."""


SWITCHES: tuple[ZendureSwitchEntityDescription, ...] = (
    ZendureSwitchEntityDescription(
        # smartMode RW 0-1: 1 = do not persist config to flash (zenSDK).
        key="smartMode",
        name="smartMode",
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
    ),
    ZendureSwitchEntityDescription(
        # Fanmode RW 0-1: 0 off / 1 on. "Unauthorized modification not recommended."
        key="Fanmode",
        name="Fanmode",
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZendureConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Zendure switch entities for writable boolean properties on the device."""
    coordinator = entry.runtime_data
    async_add_entities(
        ZendureSwitch(coordinator, description)
        for description in SWITCHES
        if description.key in coordinator.data.device
    )


class ZendureSwitch(ZendureDeviceEntity, SwitchEntity):
    """A writable boolean property."""

    entity_description: ZendureSwitchEntityDescription

    def __init__(
        self,
        coordinator: ZendureCoordinator,
        description: ZendureSwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Explain flash persistence without changing the device's switch value."""
        if self._key != "smartMode":
            return None
        return {
            "flash_speicherung_unterdrueckt": self.is_on,
            "hinweis": (
                "Ein: Änderungen nicht dauerhaft speichern; nach Geräte-Neustart "
                "gelten die zuvor gespeicherten Einstellungen."
            ),
        }

    @property
    def is_on(self) -> bool | None:
        """Return True when the property equals 1."""
        raw = self.native_property_value
        try:
            return int(raw) == 1 if raw is not None else None
        except (TypeError, ValueError):
            return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Set the property to 1."""
        await self.coordinator.async_write_property(self._key, 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Set the property to 0."""
        await self.coordinator.async_write_property(self._key, 0)
