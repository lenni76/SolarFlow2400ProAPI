"""Sensor platform for SolarFlow2400-API (read-only properties).

Units, scaling and battery-pack fields follow Zendure zenSDK OpenAPI 1.0.2 and
the manufacturer's Zendure-HA integration (totalVol scaling). Any property reported
that is *not* explicitly listed here is still exposed as a raw diagnostic
sensor (disabled by default) so no data is lost - matching the reference
Symcon script's "create a variable for every property" behaviour.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ZendureConfigEntry, ZendureCoordinator
from .entity import ZendureDeviceEntity, ZendurePackEntity

PARALLEL_UPDATES = 0

# Keys handled by other platforms (writable controls / binary flags) so we do
# not also expose them as raw fallback sensors.
_WRITABLE_KEYS = {
    "acMode",
    "inputLimit",
    "outputLimit",
    "socSet",
    "minSoc",
    "gridReverse",
    "inverseMaxPower",
    "gridStandard",
    "smartMode",
    "batCalTime",
    "Fanmode",
    "Fanspeed",
    "gridOffMode",
    "writeRsp",
}
_BINARY_KEYS = {
    "pass",
    "reverseState",
    "socStatus",
    "dataReady",
    "gridState",
    "is_error",
    "heatState",
    "pvStatus",
    "lampSwitch",
    "fanSwitch",
    "dryNodeState",
}


@dataclass(frozen=True, kw_only=True)
class ZendureSensorEntityDescription(SensorEntityDescription):
    """Sensor description with an optional linear scale factor."""

    scale: float = 1.0
    # Convert raw value to native value; overrides scale when provided.
    value_fn: Callable[[Any], Any] | None = None


def _kelvin_tenths_to_c(raw: Any) -> float | None:
    """maxTemp is stored in 0.1 Kelvin: C = (raw - 2731) / 10 (zenSDK doc)."""
    try:
        return round((float(raw) - 2731) / 10.0, 1)
    except (TypeError, ValueError):
        return None


def _battery_current_to_a(raw: Any) -> float | None:
    """Decode the documented signed int16 in tenths of an ampere.

    Accept unsigned two's-complement values and already signed JSON integers.
    The wire schema specifies an integer, not a byte array or fractional value.
    """
    try:
        if isinstance(raw, bool):
            return None
        value = int(raw)
        if float(raw) != value or not -32768 <= value <= 65535:
            return None
    except (TypeError, ValueError, OverflowError):
        return None
    if value >= 32768:
        value -= 65536
    return value / 10.0


# --- Device-level sensors (Device Data Properties, RO) ----------------------
_POWER_KEYS = (
    "packInputPower",
    "outputPackPower",
    "outputHomePower",
    "gridInputPower",
    "solarInputPower",
    "gridOffPower",
)

DEVICE_SENSORS: tuple[ZendureSensorEntityDescription, ...] = (
    *(
        ZendureSensorEntityDescription(
            key=key,
            name=key,
            native_unit_of_measurement=UnitOfPower.WATT,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
        )
        for key in _POWER_KEYS
    ),
    *(
        ZendureSensorEntityDescription(
            key=f"solarPower{n}",
            name=f"solarPower{n}",
            native_unit_of_measurement=UnitOfPower.WATT,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
        )
        for n in range(1, 7)
    ),
    ZendureSensorEntityDescription(
        key="electricLevel",
        name="electricLevel",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ZendureSensorEntityDescription(
        # OpenAPI 1.0.2 specifies the same 0.1 K conversion as maxTemp.
        key="hyperTmp",
        name="hyperTmp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_kelvin_tenths_to_c,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZendureSensorEntityDescription(
        key="remainOutTime",
        name="remainOutTime",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
    ),
    ZendureSensorEntityDescription(
        # BatVolt is reported in 0.01 V (zenSDK doc) -> scale to volts.
        key="BatVolt",
        name="BatVolt",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        scale=0.01,
        suggested_display_precision=2,
    ),
    ZendureSensorEntityDescription(
        key="FMVolt",
        name="FMVolt",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ZendureSensorEntityDescription(
        key="chargeMaxLimit",
        name="chargeMaxLimit",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ZendureSensorEntityDescription(
        key="rssi",
        name="rssi",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZendureSensorEntityDescription(
        key="packNum", name="packNum", entity_category=EntityCategory.DIAGNOSTIC
    ),
    # Multi-state fields (0-2 etc.) are exposed as raw integers; see README for
    # the meaning of each value (from the zenSDK property table).
    *(
        ZendureSensorEntityDescription(
            key=key, name=key, entity_category=EntityCategory.DIAGNOSTIC
        )
        for key in (
            "packState",
            "dcStatus",
            "acStatus",
            "socLimit",
            "faultLevel",
            "fanSpeed",
        )
    ),
)

# --- Battery-pack sensors (Battery Pack Data Properties, RO) -----------------
PACK_SENSORS: tuple[ZendureSensorEntityDescription, ...] = (
    ZendureSensorEntityDescription(
        key="socLevel",
        name="socLevel",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ZendureSensorEntityDescription(
        key="power",
        name="power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ZendureSensorEntityDescription(
        key="totalVol",
        name="totalVol",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        # Zendure-HA's EntityDevice.createEntity uses factor 100 for totalVol;
        # the OpenAPI unit label alone omits this wire scaling.
        scale=0.01,
        suggested_display_precision=2,
    ),
    ZendureSensorEntityDescription(
        key="maxVol",  # 0.01 V per doc
        name="maxVol",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        scale=0.01,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ZendureSensorEntityDescription(
        key="minVol",  # 0.01 V per doc
        name="minVol",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        scale=0.01,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ZendureSensorEntityDescription(
        key="maxTemp",  # 0.1 K per doc -> C
        name="maxTemp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_kelvin_tenths_to_c,
    ),
    ZendureSensorEntityDescription(
        # Decode uint16 two's-complement before scaling, while also accepting
        # already signed JSON values. Keep this diagnostic disabled by default.
        key="batcur",
        name="batcur",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        value_fn=_battery_current_to_a,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZendureSensorEntityDescription(
        key="state", name="state", entity_category=EntityCategory.DIAGNOSTIC
    ),
    ZendureSensorEntityDescription(
        key="softVersion",
        name="softVersion",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ZendureSensorEntityDescription(
        key="packType",
        name="packType",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    ZendureSensorEntityDescription(
        # Documented 0/1 heating flag, preserved as a numeric diagnostic value.
        key="heatState",
        name="heatState",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)

_KNOWN_DEVICE_KEYS = {d.key for d in DEVICE_SENSORS}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZendureConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Zendure sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        ZendureStatusSensor(coordinator),
        ZendureHealthSensor(coordinator),
        ZendureCommandSensor(coordinator),
        *(
            ZendureCounterSensor(coordinator, key, attribute)
            for key, attribute in (
                ("api_write_count", "write_count"),
                ("skipped_write_count", "skipped_write_count"),
                ("retry_write_count", "total_retry_count"),
                ("recovery_write_count", "recovery_write_count"),
            )
        ),
    ]

    # Known device sensors.
    for description in DEVICE_SENSORS:
        if description.key in coordinator.data.device:
            entities.append(ZendureDeviceSensor(coordinator, description))

    # Fallback: any other reported scalar becomes a raw diagnostic sensor.
    handled = _KNOWN_DEVICE_KEYS | _WRITABLE_KEYS | _BINARY_KEYS | {"sn"}
    for key in coordinator.data.device:
        if key in handled:
            continue
        entities.append(
            ZendureDeviceSensor(
                coordinator,
                ZendureSensorEntityDescription(
                    key=key,
                    name=key,
                    entity_category=EntityCategory.DIAGNOSTIC,
                    entity_registry_enabled_default=False,
                ),
            )
        )

    async_add_entities(entities)

    known_pack_entities: set[tuple[str, str]] = set()

    @callback
    def _async_add_pack_entities() -> None:
        new_entities: list[ZendurePackSensor] = []
        for pack_sn, pack in coordinator.data.packs.items():
            for description in PACK_SENSORS:
                entity_key = (pack_sn, description.key)
                if description.key not in pack or entity_key in known_pack_entities:
                    continue
                known_pack_entities.add(entity_key)
                new_entities.append(
                    ZendurePackSensor(coordinator, pack_sn, description)
                )
        if new_entities:
            async_add_entities(new_entities)

    _async_add_pack_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_pack_entities))


class ZendureDeviceSensor(ZendureDeviceEntity, SensorEntity):
    """A device-level sensor."""

    entity_description: ZendureSensorEntityDescription

    def __init__(
        self,
        coordinator: ZendureCoordinator,
        description: ZendureSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key

    @property
    def native_value(self) -> Any:
        """Return the scaled value for this property."""
        return _apply(self.entity_description, self.native_property_value)


class ZendurePackSensor(ZendurePackEntity, SensorEntity):
    """A battery-pack sensor."""

    entity_description: ZendureSensorEntityDescription

    def __init__(
        self,
        coordinator: ZendureCoordinator,
        pack_sn: str,
        description: ZendureSensorEntityDescription,
    ) -> None:
        """Initialize the pack sensor."""
        super().__init__(coordinator, pack_sn, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key

    @property
    def native_value(self) -> Any:
        """Return the scaled value for this pack property."""
        return _apply(self.entity_description, self.native_property_value)


def _apply(description: ZendureSensorEntityDescription, raw: Any) -> Any:
    """Apply value_fn / scale to a raw property value."""
    if raw is None:
        return None
    if description.value_fn is not None:
        return description.value_fn(raw)
    if description.scale != 1.0:
        try:
            return round(float(raw) * description.scale, 2)
        except (TypeError, ValueError):
            return None
    return raw


class ZendureStatusSensor(ZendureDeviceEntity, SensorEntity):
    """Human-readable derived integration status; no raw enum interpretation."""

    _attr_name = "Zendure Status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:information-outline"

    def __init__(self, coordinator: ZendureCoordinator) -> None:
        super().__init__(coordinator, "zendure_status")

    @property
    def native_value(self) -> str:
        return self.coordinator.current_status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.diagnostics
        return {
            "letzter_befehl": d.last_command,
            "befehl_status": d.status,
            "letzter_fehler": d.last_error,
            "ac_modus_unbestaetigt": d.recovery_restore_failed,
            "angeforderter_wert": d.last_requested_value,
            "gesendeter_wert": d.last_sent_value,
            "gemeldeter_wert": d.last_reported_value,
            "befehl_erfolgreich": d.command_success,
            "wiederholungen": d.retry_count,
            "verwendetes_geraetelimit": d.limit_used,
            "recovery_aktiv": d.recovery_active,
            "letzte_ereignisse": list(d.events),
        }

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success


class ZendureHealthSensor(ZendureDeviceEntity, SensorEntity):
    """Condensed health assessment based on integration-observed outcomes."""

    _attr_name = "Zendure Zustand"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:heart-pulse"

    def __init__(self, coordinator: ZendureCoordinator) -> None:
        super().__init__(coordinator, "zendure_health")

    @property
    def native_value(self) -> str:
        status = self.coordinator.current_status
        if status == "Gerätefehler":
            return "Fehler"
        if status == "Hoher Ladestand, geringe Ausgabe":
            return "Eingeschränkter Betrieb"
        return "OK" if status == "Normal" else status

    @property
    def available(self) -> bool:
        return True


class ZendureCommandSensor(ZendureDeviceEntity, SensorEntity):
    """Last command result with timestamps and unmodified values."""

    _attr_name = "Letzter Steuerbefehl"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:code-json"

    def __init__(self, coordinator: ZendureCoordinator) -> None:
        super().__init__(coordinator, "last_command")

    @property
    def native_value(self) -> str:
        d = self.coordinator.diagnostics
        return d.last_command or "Noch kein Befehl"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.diagnostics
        return {
            "angeforderter_wert": d.last_requested_value,
            "status": d.status,
            "letzter_fehler": d.last_error,
            "ac_modus_unbestaetigt": d.recovery_restore_failed,
            "wiederherzustellender_ac_modus": d.restore_mode,
            "api_schreibversuche_seit_start": d.write_count,
            "vermiedene_schreibversuche_seit_start": d.skipped_write_count,
            "wiederholungen_seit_start": d.total_retry_count,
            "recovery_schreibversuche_seit_start": d.recovery_write_count,
            "gesendeter_wert": d.last_sent_value,
            "gemeldeter_wert": d.last_reported_value,
            "erfolgreich": d.command_success,
            "zeitpunkt": d.last_write_at.isoformat() if d.last_write_at else None,
            "letzter_erfolg": d.last_success_at.isoformat()
            if d.last_success_at
            else None,
            "letzte_recovery": d.last_recovery_at.isoformat()
            if d.last_recovery_at
            else None,
        }

    @property
    def available(self) -> bool:
        return True


class ZendureCounterSensor(ZendureDeviceEntity, SensorEntity):
    """Observed API attempts since integration setup, never physical flash counts."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:counter"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self, coordinator: ZendureCoordinator, key: str, attribute: str
    ) -> None:
        super().__init__(coordinator, key)
        self._attribute = attribute
        self._attr_translation_key = key

    @property
    def native_value(self) -> int:
        return getattr(self.coordinator.diagnostics, self._attribute)

    @property
    def available(self) -> bool:
        return True
