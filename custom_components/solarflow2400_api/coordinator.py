"""DataUpdateCoordinator for the SolarFlow2400-API local integration."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from math import isfinite
from time import monotonic
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
    CONF_SKIP_UNCHANGED,
    CONF_VALIDATION_DELAY,
    DEFAULT_AUTO_RECOVERY,
    DEFAULT_COMMAND_VALIDATION,
    DEFAULT_RECOVERY_COOLDOWN,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SKIP_UNCHANGED,
    DEFAULT_VALIDATION_DELAY,
    DOMAIN,
    DUPLICATE_MAX_AGE,
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
    last_requested_at: datetime | None = None
    last_error: str | None = None
    write_count: int = 0
    skipped_write_count: int = 0
    total_retry_count: int = 0
    recovery_write_count: int = 0
    recovery_restore_failed: bool = False
    restore_mode: int | None = None
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
        left, right = float(expected), float(actual)
        return isfinite(left) and isfinite(right) and left == right
    except (TypeError, ValueError):
        return expected == actual


type ZendureConfigEntry = ConfigEntry[ZendureCoordinator]


class ZendureCoordinator(DataUpdateCoordinator[ZendureData]):
    """Poll the device and provide verified command diagnostics."""

    config_entry: ZendureConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ZendureConfigEntry) -> None:
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.serial = entry.data[CONF_SERIAL]
        self.model = entry.data.get(CONF_MODEL) or "SolarFlow"
        self.api = ZendureLocalApi(entry.data[CONF_HOST], async_get_clientsession(hass))
        self.command_validation = entry.options.get(
            CONF_COMMAND_VALIDATION, DEFAULT_COMMAND_VALIDATION
        )
        self.auto_recovery = entry.options.get(
            CONF_AUTO_RECOVERY, DEFAULT_AUTO_RECOVERY
        )
        self.validation_delay = entry.options.get(
            CONF_VALIDATION_DELAY, DEFAULT_VALIDATION_DELAY
        )
        self.recovery_cooldown = entry.options.get(
            CONF_RECOVERY_COOLDOWN, DEFAULT_RECOVERY_COOLDOWN
        )
        self.diagnostics = CommandDiagnostics()
        self._write_lock = asyncio.Lock()
        self.skip_unchanged = entry.options.get(
            CONF_SKIP_UNCHANGED, DEFAULT_SKIP_UNCHANGED
        )
        self._last_report_monotonic: float | None = None
        self._write_generation = 0
        self._report_max_age = max(10, scan_interval * 2)
        self._operating_status = "Normal"

    async def _async_update_data(self) -> ZendureData:
        try:
            return await self._read_report()
        except ZendureApiError as err:
            raise UpdateFailed(str(err)) from err

    async def _read_report(self) -> ZendureData:
        """Only use a report from the configured device as confirmation."""
        self._last_report_monotonic = None
        generation = self._write_generation
        report = await self.api.async_get_report()
        props = report.get("properties")
        serial = report.get("sn") or (
            props.get("sn") if isinstance(props, dict) else None
        )
        if serial != self.serial or not isinstance(props, dict) or not props:
            raise ZendureApiError(
                "Gerätebericht ohne passende Seriennummer oder Eigenschaften"
            )
        data = _normalize(report, self.serial)
        if generation == self._write_generation:
            self._last_report_monotonic = monotonic()
        else:
            # Do not publish a pre-write snapshot or clear a pending mode alarm.
            self._last_report_monotonic = None
            raise ZendureApiError(
                "Geräteabfrage durch zwischenzeitlichen Schreibversuch überholt"
            )
        self._update_derived_status(data)
        return data

    @property
    def report_age(self) -> float | None:
        """Age of the last successful report; failed reads invalidate the cache."""
        if self._last_report_monotonic is None:
            return None
        return max(0, monotonic() - self._last_report_monotonic)

    @property
    def current_status(self) -> str:
        """Current device observation, separate from the last command outcome."""
        if not self.last_update_success:
            return "Gerät nicht erreichbar"
        if self.diagnostics.recovery_restore_failed:
            return "AC-Modus unbestätigt"
        age = self.report_age
        if age is None or age > self._report_max_age:
            return "Gerätedaten veraltet"
        if self.data and _numbers_equal(1, self.data.device.get("is_error")):
            return "Gerätefehler"
        if self.diagnostics.recovery_active:
            return "Recovery aktiv"
        return self._operating_status

    def _event(self, message: str) -> None:
        stamp = datetime.now().astimezone().strftime("%H:%M:%S")
        self.diagnostics.events.appendleft(f"{stamp} – {message}")
        _LOGGER.info(message)

    def _dynamic_limit(self, key: str, requested: Any) -> tuple[Any, float | None]:
        """Clamp only against limits that the device itself currently reports."""
        limit_key = {
            "outputLimit": "inverseMaxPower",
            "inputLimit": "chargeMaxLimit",
        }.get(key)
        if not limit_key or not self.data:
            return requested, None
        raw_limit = self.data.device.get(limit_key)
        try:
            limit = float(raw_limit)
            value = float(requested)
        except (TypeError, ValueError):
            return requested, None
        if not isfinite(limit) or limit <= 0 or value <= limit:
            return requested, limit if limit > 0 else None
        limited = int(limit) if float(limit).is_integer() else limit
        return limited, limit

    async def async_write_property(self, key: str, value: Any) -> None:
        """Write without rate limiting; confirm or return a meaningful HA error."""
        async with self._write_lock:
            sent_value, limit = self._dynamic_limit(key, value)
            d = self.diagnostics
            previous_failed = d.command_success is False
            d.last_command = key
            d.last_requested_value = value
            d.last_sent_value = sent_value
            d.last_reported_value = None
            d.last_requested_at = datetime.now(UTC)
            d.retry_count = 0
            d.command_success = None
            d.last_error = None
            d.output_limited = sent_value != value
            d.limit_used = limit
            try:
                if self._can_skip(key, sent_value, previous_failed):
                    d.skipped_write_count += 1
                    d.last_reported_value = self.data.device[key]
                    self._complete_success("Sollwert bereits bestätigt")
                    return
                d.status = "Befehl gesendet"
                if d.output_limited:
                    self._event(
                        f"{key}: Sollwert {value} auf Gerätelimit {sent_value} begrenzt"
                    )
                await self._post(key, sent_value)
                if not self.command_validation:
                    # A successful POST alone does not confirm the device setting.
                    d.status = "Gesendet, nicht geprüft"
                    await self.async_request_refresh()
                    return
                if await self._validate_property(key, sent_value):
                    return
                d.retry_count = 1
                d.total_retry_count += 1
                d.status = "Befehl wird wiederholt"
                self._event(f"{key}: Rückmeldung wich ab, einmalige Wiederholung")
                await self._post(key, sent_value)
                if await self._validate_property(key, sent_value):
                    return
                d.status = "Befehl ignoriert"
                if self.auto_recovery and key in {"outputLimit", "inputLimit"}:
                    if await self._attempt_recovery(key, sent_value):
                        return
                raise HomeAssistantError(
                    f"{key}={sent_value} wurde nicht bestätigt. "
                    f"Letzte Rückmeldung: {d.last_reported_value!r}. "
                    f"{d.last_error or d.status}"
                )
            except asyncio.CancelledError:
                d.command_success = False
                d.last_error = "Befehl abgebrochen; Gerätewirkung nicht bestätigt"
                d.status = (
                    "AC-Modus unbestätigt"
                    if d.recovery_restore_failed
                    else "Abgebrochen"
                )
                raise
            except ZendureApiError as err:
                d.command_success = False
                d.status = (
                    "AC-Modus unbestätigt"
                    if d.recovery_restore_failed
                    else "Schreibfehler"
                )
                d.last_error = str(err)
                raise HomeAssistantError(
                    f"SolarFlow: {key}={sent_value} fehlgeschlagen: {err}"
                ) from err
            except HomeAssistantError as err:
                d.command_success = False
                d.last_error = str(err)
                raise
            finally:
                self.async_update_listeners()

    def _can_skip(self, key: str, value: Any, previous_failed: bool) -> bool:
        """Skip exact fresh readbacks only; always transmit zero-power commands."""
        if key in {"outputLimit", "inputLimit"} and _numbers_equal(value, 0):
            return False
        age = self.report_age
        return (
            self.skip_unchanged
            and not previous_failed
            and not self.diagnostics.recovery_restore_failed
            and self.last_update_success
            and age is not None
            and age <= DUPLICATE_MAX_AGE
            and self.data is not None
            and key in self.data.device
            and _numbers_equal(value, self.data.device[key])
        )

    async def _post(self, key: str, value: Any, *, recovery: bool = False) -> None:
        """Count actual HTTP attempts, not assumed physical flash operations."""
        d = self.diagnostics
        d.write_count += 1
        if recovery:
            d.recovery_write_count += 1
        d.last_write_at = datetime.now(UTC)
        self._write_generation += 1
        self._last_report_monotonic = None
        await self.api.async_write_property(self.serial, key, value)

    def _complete_success(self, status: str = "Normal") -> None:
        d = self.diagnostics
        d.status = "Leistung begrenzt" if d.output_limited else status
        d.command_success = True
        d.last_success_at = datetime.now(UTC)
        d.last_error = None

    async def _validate_property(self, key: str, expected: Any) -> bool:
        await asyncio.sleep(self.validation_delay)
        try:
            data = await self._read_report()
        except ZendureApiError as err:
            self.diagnostics.last_error = f"Prüfung fehlgeschlagen: {err}"
            _LOGGER.warning("Validation report failed: %s", err)
            return False
        actual = data.device.get(key)
        self.diagnostics.last_reported_value = actual
        confirmed = key in data.device and _numbers_equal(expected, actual)
        if confirmed:
            # Publish the outcome together with its report, not one poll later.
            self._complete_success()
        self.async_set_updated_data(data)
        return confirmed

    async def _attempt_recovery(self, key: str, value: Any) -> bool:
        """Optional mode toggle, with verified restoration even on cancellation."""
        d = self.diagnostics
        now = datetime.now(UTC)
        if _numbers_equal(value, 0):
            d.status = "Recovery für Nullleistung ausgelassen"
            return False
        if (
            d.last_recovery_at
            and (now - d.last_recovery_at).total_seconds() < self.recovery_cooldown
        ):
            d.status = "Recovery gesperrt"
            return False
        current_mode = self.data.device.get("acMode") if self.data else None
        age = self.report_age
        if (
            current_mode not in (1, 2)
            or age is None
            or age > DUPLICATE_MAX_AGE
            or d.recovery_restore_failed
        ):
            d.status = "Recovery nicht möglich"
            return False
        # Do not briefly enable discharge to recover a charging command. Require
        # the device's reverse-flow prohibition without silently changing it.
        if key != "outputLimit" or current_mode != 2:
            d.status = "Recovery für Ladesteuerung ausgelassen"
            return False
        if not _numbers_equal(self.data.device.get("gridReverse"), 2):
            d.status = "Recovery ohne Rückspeisesperre ausgelassen"
            return False
        alternate = 1
        d.recovery_active = True
        d.last_recovery_at = now
        d.status = "Recovery aktiv"
        d.restore_mode = current_mode
        d.recovery_restore_failed = True
        self._event(f"Einmalige Recovery für {key} gestartet")
        try:
            cancelled = False
            try:
                await self._post("acMode", alternate, recovery=True)
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                cancelled = True
                raise
            finally:
                # Also restore after an ambiguous timeout of the first POST.
                restored = await self._restore_shielded(current_mode)
                if not restored and not cancelled:
                    raise ZendureApiError(
                        f"Ursprünglicher AC-Modus {current_mode} nicht bestätigt"
                    )
            await self._post(key, value, recovery=True)
            if await self._validate_property(key, value):
                self._event("Recovery erfolgreich")
                return True
            d.status = "Recovery fehlgeschlagen"
            return False
        finally:
            d.recovery_active = False

    async def _restore_shielded(self, mode: int) -> bool:
        """Retain the command lock until bounded cleanup finishes; do not orphan it."""
        task = asyncio.create_task(self._restore_mode(mode))
        cancelled = False
        while True:
            try:
                restored = await asyncio.shield(task)
                break
            except asyncio.CancelledError:
                if task.cancelled():
                    # HA shutdown may cancel the cleanup task independently.
                    # Never spin on an already cancelled task.
                    raise
                cancelled = True
        if cancelled:
            raise asyncio.CancelledError
        return restored

    async def _restore_mode(self, mode: int) -> bool:
        """Try restoration at most twice, confirming readback even after a timeout."""
        d = self.diagnostics
        for _ in range(2):
            try:
                await self._post("acMode", mode, recovery=True)
            except ZendureApiError as err:
                d.last_error = f"AC-Modus-Wiederherstellung: {err}"
            await asyncio.sleep(1)
            try:
                data = await self._read_report()
            except ZendureApiError as err:
                d.last_error = f"AC-Modus nicht prüfbar: {err}"
                continue
            restored = _numbers_equal(data.device.get("acMode"), mode)
            if restored:
                d.recovery_restore_failed = False
                d.restore_mode = None
            self.async_set_updated_data(data)
            if restored:
                return True
        d.recovery_restore_failed = True
        d.status = "AC-Modus unbestätigt"
        self._event(f"AC-Modus {mode} konnte nicht bestätigt werden")
        return False

    def _update_derived_status(self, data: ZendureData) -> None:
        """Detect only observable conditions; raw enums remain untranslated."""
        d = self.diagnostics
        if d.recovery_restore_failed and _numbers_equal(
            data.device.get("acMode"), d.restore_mode
        ):
            d.recovery_restore_failed = False
            d.restore_mode = None
        self._operating_status = "Normal"
        try:
            soc = float(data.device.get("electricLevel"))
            requested = (
                float(d.last_sent_value) if d.last_command == "outputLimit" else 0
            )
            output = float(data.device.get("outputHomePower", 0))
        except (TypeError, ValueError):
            return
        if soc >= 99 and requested > 0 and output < min(50, requested * 0.1):
            self._operating_status = "Hoher Ladestand, geringe Ausgabe"
