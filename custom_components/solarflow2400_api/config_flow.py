"""Config flow for the SolarFlow2400-API integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import ZendureApiError, ZendureLocalApi
from .const import (
    CONF_MODEL,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


def _extract_serial(report: dict[str, Any]) -> str | None:
    """Pull the device serial ("sn") from a /properties/report response."""
    if isinstance(report.get("sn"), str):
        return report["sn"]
    props = report.get("properties")
    if isinstance(props, dict) and isinstance(props.get("sn"), str):
        return props["sn"]
    return None


def _model_from_zeroconf_name(name: str) -> str | None:
    """Parse the model from a Zendure-<Model>-<Last12MAC> service name."""
    # e.g. "Zendure-SolarFlow800-WOB1NHMAMXXXXX3._zendure._tcp.local."
    base = name.split(".", 1)[0]
    parts = base.split("-")
    if len(parts) >= 3 and parts[0].lower() == "zendure":
        return parts[1]
    return None


class ZendureConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SolarFlow2400-API."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize discovered-device state."""
        self._host: str | None = None
        self._model: str | None = None

    async def _async_probe(self, host: str) -> tuple[str, dict[str, Any]]:
        """Contact the device and return (serial, raw report)."""
        session = async_get_clientsession(self.hass)
        api = ZendureLocalApi(host, session)
        report = await api.async_get_report()
        serial = _extract_serial(report)
        if not serial:
            raise ValueError("no_serial")
        return serial, report

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a manual (IP-based) setup."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            try:
                serial, _ = await self._async_probe(host)
            except ZendureApiError:
                errors["base"] = "cannot_connect"
            except ValueError:
                errors["base"] = "no_serial"
            else:
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title=f"SolarFlow {serial}",
                    data={
                        CONF_HOST: host,
                        CONF_SERIAL: serial,
                        CONF_MODEL: self._model or "SolarFlow",
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}),
            errors=errors,
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle discovery via mDNS/zeroconf (_zendure._tcp.local.)."""
        host = discovery_info.host
        self._host = host
        self._model = _model_from_zeroconf_name(discovery_info.name)

        try:
            serial, _ = await self._async_probe(host)
        except ZendureApiError:
            return self.async_abort(reason="cannot_connect")
        except ValueError:
            return self.async_abort(reason="no_serial")

        await self.async_set_unique_id(serial)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        self.context["title_placeholders"] = {
            "name": f"{self._model or 'SolarFlow'} {serial}"
        }
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user to confirm adding a discovered device."""
        assert self._host is not None
        serial = self.unique_id
        assert serial is not None

        if user_input is not None:
            return self.async_create_entry(
                title=f"{self._model or 'SolarFlow'} {serial}",
                data={
                    CONF_HOST: self._host,
                    CONF_SERIAL: serial,
                    CONF_MODEL: self._model or "SolarFlow",
                },
            )

        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={
                "model": self._model or "SolarFlow",
                "serial": serial,
                "host": self._host,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> ZendureOptionsFlow:
        """Return the options flow handler."""
        return ZendureOptionsFlow()


class ZendureOptionsFlow(OptionsFlow):
    """Handle the (single) option: poll interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the poll interval option."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=current
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    )
                }
            ),
        )
