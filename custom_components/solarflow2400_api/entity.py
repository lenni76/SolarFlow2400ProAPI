"""Base entities for the SolarFlow2400-API integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_info import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import ZendureCoordinator


class ZendureDeviceEntity(CoordinatorEntity[ZendureCoordinator]):
    """Base for entities that read/write a device-level property."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ZendureCoordinator, key: str) -> None:
        """Initialize with the property key this entity represents."""
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.serial}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return the main SolarFlow device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.serial)},
            manufacturer=MANUFACTURER,
            model=self.coordinator.model,
            name=f"Zendure {self.coordinator.model}",
            serial_number=self.coordinator.serial,
            configuration_url=f"http://{self.coordinator.api.host}",
        )

    @property
    def native_property_value(self) -> Any:
        """Return the raw value of this property from the last report."""
        return self.coordinator.data.device.get(self._key)

    @property
    def available(self) -> bool:
        """Available only when the last poll succeeded and the key is present."""
        return super().available and self._key in self.coordinator.data.device


class ZendurePackEntity(CoordinatorEntity[ZendureCoordinator]):
    """Base for entities that read a battery-pack property."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: ZendureCoordinator, pack_sn: str, key: str
    ) -> None:
        """Initialize with the pack serial and property key."""
        super().__init__(coordinator)
        self._pack_sn = pack_sn
        self._key = key
        self._attr_unique_id = f"{pack_sn}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return the battery pack as a sub-device of the main SolarFlow."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._pack_sn)},
            manufacturer=MANUFACTURER,
            model="SolarFlow Battery Pack",
            name=f"Zendure Battery {self._pack_sn}",
            serial_number=self._pack_sn,
            via_device=(DOMAIN, self.coordinator.serial),
        )

    @property
    def native_property_value(self) -> Any:
        """Return the raw value of this property for this pack."""
        return self.coordinator.data.packs.get(self._pack_sn, {}).get(self._key)

    @property
    def available(self) -> bool:
        """Available only when the pack reported this key on the last poll."""
        return (
            super().available
            and self._key in self.coordinator.data.packs.get(self._pack_sn, {})
        )
