"""DataUpdateCoordinator for the SolarFlow2400-API local integration."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ZendureApiError, ZendureLocalApi
from .const import (
    CONF_AUTO_RECOVERY,
    CONF_COMMAND_VALIDATION,
    CONF_HOST,
    CONF_MODEL,
    CONF_RECOVERY_COOLDOWN,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL,
    CONF_VALIDATION_DELAY,
    DEFAULT_AUTO_RECOVERY,
    DEFAULT_COMMAND_VALIDATION,
    DEFAULT_RECOVERY_COOLDOWN,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VALIDATION_DELAY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ZendureData:
    """Normalized snapshot of one /properties/report response."""

    serial: str
    device: dict[str, Any] = field(default_factory=dict)
    packs: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(slots=True)
class CommandDiagnostics:
    """Runtime diagnostics for write validation and recovery."""

    status: str = "Normal"
    last_command: str | None = None
    last_requested_value: Any = None
    last_sent_value: Any = None
    last_reported_value: Any = None
    last_write_at: datetime | None = None
    last_success_at: datetime | None = None
    retry_count: int = 0
    command_success: bool | None = None
    recovery_active: bool = False
    last_recovery_at: datetime | None = None
    output_limited: bool = False
    limit_used: float | None = None
    events: deque[str] = field(default_factory=lambda: deque(maxlen=10))


def _normalize(report: dict[str, Any], fallback_serial: str) -> ZendureData:
    """Flatten a raw /properties/report response into scalars + packs."""
    props = report.get("properties")
    props = props if isinstance(props, dict) else {}
    device: dict[str, Any] = {}
    packs: dict[str, dict[str, Any]] = {}

    for source in (report, props):
        for key, value in source.items():
            if key == "properties":
                continue
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if not isinstance(sub_value, (dict, list)):
                        device[f"{key}_{sub_key}"] = sub_value
                continue
            if isinstance(value, list):
                for index, item in enumerate(value):
                    if not isinstance(item, dict):
                        continue
                    pack_sn = str(item.get("sn") or f"{key}_{index}")
                    packs[pack_sn] = {
                        k: v for k, v in item.items() if not isinstance(v, (dict, list))
                    }
                continue
            device[key] = value

    serial = str(device.get("sn") or fallback_serial)
    return ZendureData(serial=serial, device=device, packs=packs)


def _numbers_equal(expected: Any, actual: Any) -> bool:
    """Compare API values without guessing enum meanings."""
    try:
        return abs(float(expected) - float(actual)) < 1.0
    except (TypeError, ValueError):
        return expected == actual


type ZendureConfigEntry = ConfigEntry[ZendureCoordinator]


class ZendureCoordinator(DataUpdateCoordinator[ZendureData]):
    """Poll the device and provide verified command diagnostics."""

    config_entry: ZendureConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ZendureConfigEntry) -> None:
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass, logger=_LOGGER, name=DOMAIN, config_entry=entry,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.serial = entry.data[CONF_SERIAL]
        self.model = entry.data.get(CONF_MODEL) or "SolarFlow"
        self.api = ZendureLocalApi(entry.data[CONF_HOST], async_get_clientsession(hass))
        self.command_validation = entry.options.get(
            CONF_COMMAND_VALIDATION, DEFAULT_COMMAND_VALIDATION
        )
        self.auto_recovery = entry.options.get(CONF_AUTO_RECOVERY, DEFAULT_AUTO_RECOVERY)
        self.validation_delay = entry.options.get(
            CONF_VALIDATION_DELAY, DEFAULT_VALIDATION_DELAY
        )
        self.recovery_cooldown = entry.options.get(
            CONF_RECOVERY_COOLDOWN, DEFAULT_RECOVERY_COOLDOWN
        )
        self.diagnostics = CommandDiagnostics()
        self._write_lock = asyncio.Lock()

    async def _async_update_data(self) -> ZendureData:
        try:
            report = await self.api.async_get_report()
        except ZendureApiError as err:
            raise UpdateFailed(str(err)) from err
        data = _normalize(report, self.serial)
        self._update_derived_status(data)
        return data

    def _event(self, message: str) -> None:
        stamp = datetime.now().astimezone().strftime("%H:%M:%S")
        self.diagnostics.events.appendleft(f"{stamp} – {message}")
        _LOGGER.info(message)

    def _dynamic_limit(self, key: str, requested: Any) -> tuple[Any, float | None]:
        """Clamp only against limits that the device itself currently reports."""
        limit_key = {"outputLimit": "inverseMaxPower", "inputLimit": "chargeMaxLimit"}.get(key)
        if not limit_key or not self.data:
            return requested, None
        raw_limit = self.data.device.get(limit_key)
        try:
            limit = float(raw_limit)
            value = float(requested)
        except (TypeError, ValueError):
            return requested, None
        if limit <= 0 or value <= limit:
            return requested, limit if limit > 0 else None
        limited = int(limit) if float(limit).is_integer() else limit
        return limited, limit

    async def async_write_property(self, key: str, value: Any) -> None:
        """Write, validate once, retry once, and optionally run one recovery."""
        async with self._write_lock:
            sent_value, limit = self._dynamic_limit(key, value)
            d = self.diagnostics
            d.last_command = key
            d.last_requested_value = value
            d.last_sent_value = sent_value
            d.last_write_at = datetime.now(timezone.utc)
            d.retry_count = 0
            d.command_success = None
            d.output_limited = sent_value != value
            d.limit_used = limit
            d.status = "Leistung begrenzt" if d.output_limited else "Befehl gesendet"
            if d.output_limited:
                self._event(f"{key}: Sollwert {value} auf gemeldetes Gerätelimit {sent_value} begrenzt")

            try:
                await self.api.async_write_property(self.serial, key, sent_value)
            except ZendureApiError as err:
                d.status = "Schreibfehler"
                d.command_success = False
                self.async_update_listeners()
                raise HomeAssistantError(f"Could not write property {key}: {err}") from err

            if not self.command_validation:
                d.status = "Validierung deaktiviert"
                await self.async_request_refresh()
                return

            if await self._validate_property(key, sent_value):
                return

            d.retry_count = 1
            d.status = "Befehl wird wiederholt"
            self._event(f"{key}: Rückmeldung wich ab, Befehl wird einmal wiederholt")
            await self.api.async_write_property(self.serial, key, sent_value)
            if await self._validate_property(key, sent_value):
                return

            d.status = "Befehl ignoriert"
            d.command_success = False
            self._event(f"{key}: Sollwert nach Wiederholung nicht bestätigt")

            if self.auto_recovery and key in {"outputLimit", "inputLimit"}:
                await self._attempt_recovery(key, sent_value)
            self.async_update_listeners()

    async def _validate_property(self, key: str, expected: Any) -> bool:
        await asyncio.sleep(self.validation_delay)
        try:
            report = await self.api.async_get_report()
        except ZendureApiError as err:
            _LOGGER.warning("Validation report failed: %s", err)
            return False
        data = _normalize(report, self.serial)
        self.async_set_updated_data(data)
        actual = data.device.get(key)
        self.diagnostics.last_reported_value = actual
        if _numbers_equal(expected, actual):
            self.diagnostics.status = "Normal"
            self.diagnostics.command_success = True
            self.diagnostics.last_success_at = datetime.now(timezone.utc)
            self._event(f"{key}: Sollwert {expected} bestätigt")
            return True
        return False

    async def _attempt_recovery(self, key: str, value: Any) -> None:
        """Toggle acMode once only when its current raw value is 1 or 2."""
        d = self.diagnostics
        now = datetime.now(timezone.utc)
        if d.last_recovery_at and (now - d.last_recovery_at).total_seconds() < self.recovery_cooldown:
            d.status = "Recovery gesperrt"
            return
        current_mode = self.data.device.get("acMode") if self.data else None
        if current_mode not in (1, 2):
            d.status = "Recovery nicht möglich"
            self._event(f"Recovery ausgelassen: acMode-Rohwert {current_mode!r} ist nicht eindeutig nutzbar")
            return
        alternate = 2 if current_mode == 1 else 1
        d.recovery_active = True
        d.last_recovery_at = now
        d.status = "Recovery aktiv"
        self._event(f"Einmalige Recovery für {key} gestartet")
        try:
            await self.api.async_write_property(self.serial, "acMode", alternate)
            await asyncio.sleep(1)
            await self.api.async_write_property(self.serial, "acMode", current_mode)
            await asyncio.sleep(1)
            await self.api.async_write_property(self.serial, key, value)
            if await self._validate_property(key, value):
                d.status = "Normal"
                self._event("Recovery erfolgreich")
            else:
                d.status = "Recovery fehlgeschlagen"
                self._event("Recovery ohne bestätigte Wirkung")
        except ZendureApiError as err:
            d.status = "Recovery fehlgeschlagen"
            self._event(f"Recovery-Fehler: {err}")
        finally:
            d.recovery_active = False

    def _update_derived_status(self, data: ZendureData) -> None:
        """Detect only observable conditions; raw enums remain untranslated."""
        d = self.diagnostics
        if d.status in {"Befehl ignoriert", "Recovery aktiv", "Recovery fehlgeschlagen", "Schreibfehler"}:
            return
        try:
            soc = float(data.device.get("electricLevel"))
            requested = float(d.last_sent_value) if d.last_command == "outputLimit" else 0
            output = float(data.device.get("outputHomePower", 0))
            grid = float(data.device.get("gridInputPower", 0))
        except (TypeError, ValueError):
            return
        if soc >= 99 and requested > 0 and output < min(50, requested * 0.1) and grid > 0:
            d.status = "100 % erreicht, keine Entladung"
        elif d.output_limited:
            d.status = "Leistung begrenzt"
        elif d.command_success is True:
            d.status = "Normal"
