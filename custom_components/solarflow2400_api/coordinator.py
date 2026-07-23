"""DataUpdateCoordinator for the SolarFlow2400-API local integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ZendureApiError, ZendureLocalApi
from .const import (
    CONF_HOST,
    CONF_MODEL,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True, slots=True)
class ZendureData:
    """Normalized snapshot of one /properties/report response."""

    serial: str
    device: dict[str, Any] = field(default_factory=dict)
    # Per battery pack, keyed by the pack serial number.
    packs: dict[str, dict[str, Any]] = field(default_factory=dict)


def _normalize(report: dict[str, Any], fallback_serial: str) -> ZendureData:
    """Flatten a raw /properties/report response into scalars + packs.

    The exact envelope differs between firmware versions (some devices wrap
    everything in a "properties" object, some report battery packs as a list
    under an unknown key). Instead of hard-coding key names we:

      * treat every top-level / "properties" scalar as a device property, and
      * treat any list-of-objects as a list of battery packs (each identified
        by its own "sn").

    This mirrors the recursive handling of the reference Symcon script without
    assuming a fixed schema.
    """
    props = report.get("properties")
    props = props if isinstance(props, dict) else {}

    device: dict[str, Any] = {}
    packs: dict[str, dict[str, Any]] = {}

    for source in (report, props):
        for key, value in source.items():
            if key == "properties":
                continue
            if isinstance(value, dict):
                # Nested object of scalars -> merge with a prefix so nothing is lost.
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


type ZendureConfigEntry = ConfigEntry[ZendureCoordinator]


class ZendureCoordinator(DataUpdateCoordinator[ZendureData]):
    """Poll GET /properties/report on a fixed interval."""

    config_entry: ZendureConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ZendureConfigEntry) -> None:
        """Initialize the coordinator from a config entry."""
        scan_interval = entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.serial: str = entry.data[CONF_SERIAL]
        self.model: str = entry.data.get(CONF_MODEL) or "SolarFlow"
        self.api = ZendureLocalApi(entry.data[CONF_HOST], async_get_clientsession(hass))

    async def _async_update_data(self) -> ZendureData:
        """Fetch and normalize the latest device report."""
        try:
            report = await self.api.async_get_report()
        except ZendureApiError as err:
            raise UpdateFailed(str(err)) from err
        return _normalize(report, self.serial)

    async def async_write_property(self, key: str, value: Any) -> None:
        """Write a single property and refresh so state reflects the device."""
        try:
            await self.api.async_write_property(self.serial, key, value)
        except ZendureApiError as err:
            raise HomeAssistantError(
                f"Could not write property {key}: {err}"
            ) from err
        await self.async_request_refresh()
