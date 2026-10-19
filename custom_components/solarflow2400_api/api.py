"""Thin async client for the SolarFlow2400-API local HTTP API.

Implements exactly the two endpoints documented in the zenSDK README:

    GET  http://<device-ip>/properties/report      -> full property JSON
    POST http://<device-ip>/properties/write       -> {"sn": ..., "properties": {...}}

Everything runs against the device's LAN IP; no cloud/internet is used, so
the integration works fully offline once the device IP is known.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .const import REPORT_PATH, REQUEST_TIMEOUT, WRITE_PATH

_LOGGER = logging.getLogger(__name__)


class ZendureApiError(Exception):
    """Raised when the device cannot be reached or returns invalid data."""


class ZendureLocalApi:
    """Talk to a single SolarFlow device over its local HTTP API."""

    def __init__(self, host: str, session: aiohttp.ClientSession) -> None:
        """Initialize with the device IP/host and a shared aiohttp session."""
        self._host = host
        self._session = session

    @property
    def host(self) -> str:
        """Return the configured host."""
        return self._host

    def _url(self, path: str) -> str:
        return f"http://{self._host}{path}"

    async def async_get_report(self) -> dict[str, Any]:
        """GET /properties/report and return the parsed JSON as a dict."""
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.get(self._url(REPORT_PATH)) as resp:
                    resp.raise_for_status()
                    # The device sets Content-Type inconsistently across firmware,
                    # so parse the body ourselves instead of trusting the header.
                    data = await resp.json(content_type=None)
        except (TimeoutError, aiohttp.ClientError, ValueError) as err:
            raise ZendureApiError(
                f"Error contacting {self._url(REPORT_PATH)}: {err}"
            ) from err

        if not isinstance(data, dict):
            raise ZendureApiError(
                "Unexpected /properties/report response (not a JSON object)"
            )
        return data

    async def async_write_property(
        self, serial: str, key: str, value: Any
    ) -> dict[str, Any]:
        """POST a single writable property.

        Body shape is exactly as documented:
            {"sn": "<serial>", "properties": {"<key>": <value>}}

        The device's local API receive buffer is only 512 bytes (zenSDK
        README -> Updates), which is far larger than a single-property write,
        so we always write one property at a time.
        """
        payload = {"sn": serial, "properties": {key: value}}
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.post(
                    self._url(WRITE_PATH), json=payload
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json(content_type=None)
        except (TimeoutError, aiohttp.ClientError, ValueError) as err:
            raise ZendureApiError(
                f"Error writing {key}={value} to {self._url(WRITE_PATH)}: {err}"
            ) from err

        _LOGGER.debug("Wrote %s=%s -> %s", key, value, data)
        return data if isinstance(data, dict) else {}
