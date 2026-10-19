"""Exercise real integration flows with the HA 2026.10.2 abort/reload helper.

HA services, schemas and device probes are test doubles. The copied HA helper
keeps its control flow; its deprecation reporter raises to model enforcement.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import test_device_links as shared


class AbortFlow(Exception):
    def __init__(self, reason, placeholders=None):
        self.reason = reason
        super().__init__(reason)


class ApiError(Exception):
    pass


class BaseFlow:
    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.handler = domain

    @property
    def source(self):
        return self.context["source"]

    async def async_set_unique_id(self, unique_id):
        self.unique_id = unique_id

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}

    def async_abort(self, *, reason):
        return {"type": "abort", "reason": reason}


class ConfigFlowTests(shared.IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.ha = self.hass()
        self.entries = []
        self.reloads = []
        self.flow_reload_requests = []
        self.tasks = []
        self.options = {}

        def find_entry(domain, unique_id):
            self.assertEqual(domain, shared.DOMAIN)
            return next((e for e in self.entries if e.unique_id == unique_id), None)

        def update_entry(entry, **updates):
            changed = False
            for key, value in updates.items():
                if getattr(entry, key, None) != value:
                    setattr(entry, key, value)
                    changed = True
            if changed:
                for listener in entry.update_listeners:
                    self.tasks.append(asyncio.create_task(listener(self.ha, entry)))
            return changed

        def schedule_reload(entry_id):
            self.flow_reload_requests.append(entry_id)
            self.reloads.append(entry_id)

        async def reload_entry(entry_id):
            self.reloads.append(entry_id)

        self.ha.config_entries.async_entry_for_domain_unique_id = find_entry
        self.ha.config_entries.async_update_entry = update_entry
        self.ha.config_entries.async_schedule_reload = schedule_reload
        self.ha.config_entries.async_reload = reload_entry

        def reject_deprecated_combination(*args, **kwargs):
            raise RuntimeError("config-flow reload combined with update listener")

        fixture = json.loads(
            (
                shared.SOURCE.parents[1] / "tests/fixtures/ha_2026_10_2_abort.json"
            ).read_text()
        )
        reference = ast.parse(fixture["source"])
        reference.body.insert(
            0,
            ast.ImportFrom(
                module="__future__", names=[ast.alias(name="annotations")], level=0
            ),
        )
        namespace = {
            "callback": lambda func: func,
            "ConfigEntryState": SimpleNamespace(LOADED="loaded", SETUP_RETRY="retry"),
            "ReportBehavior": SimpleNamespace(LOG="log"),
            "report_usage": reject_deprecated_combination,
            "DISCOVERY_SOURCES": {"zeroconf"},
            "SOURCE_IGNORE": "ignore",
            "SOURCE_USER": "user",
            "data_entry_flow": SimpleNamespace(AbortFlow=AbortFlow),
        }
        exec(
            compile(ast.fix_missing_locations(reference), fixture["url"], "exec"),
            namespace,
        )
        BaseFlow._abort_if_unique_id_configured = namespace[
            "_abort_if_unique_id_configured"
        ]

        sys.modules.update(
            {
                "voluptuous": shared.module(
                    "voluptuous",
                    Schema=lambda value: value,
                    Required=lambda key, **kwargs: key,
                    All=lambda *values: values,
                    Coerce=lambda value: value,
                    Range=lambda **kwargs: kwargs,
                ),
                "homeassistant.config_entries": shared.module(
                    "homeassistant.config_entries",
                    ConfigEntry=shared.Entry,
                    ConfigFlow=BaseFlow,
                    ConfigFlowResult=dict,
                    OptionsFlow=BaseFlow,
                ),
                "homeassistant.helpers.aiohttp_client": shared.module(
                    "homeassistant.helpers.aiohttp_client",
                    async_get_clientsession=lambda hass: None,
                ),
                "homeassistant.helpers.service_info": shared.module(
                    "homeassistant.helpers.service_info"
                ),
                "homeassistant.helpers.service_info.zeroconf": shared.module(
                    "homeassistant.helpers.service_info.zeroconf",
                    ZeroconfServiceInfo=SimpleNamespace,
                ),
                f"{shared.PACKAGE}.api": shared.module(
                    f"{shared.PACKAGE}.api",
                    ZendureApiError=ApiError,
                    ZendureLocalApi=object,
                ),
            }
        )
        sys.modules["homeassistant.const"].CONF_HOST = "host"
        sys.modules["homeassistant.core"].callback = lambda func: func
        spec = importlib.util.spec_from_file_location(
            f"{shared.PACKAGE}.config_flow", shared.SOURCE / "config_flow.py"
        )
        self.flow_module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.flow_module
        spec.loader.exec_module(self.flow_module)

    async def asyncTearDown(self):
        if self.tasks:
            await asyncio.gather(*self.tasks)

    async def installed_entry(self):
        entry = shared.Entry("entry-a")
        entry.unique_id = "HUB-TEST"
        entry.state = "loaded"
        entry.source = "user"
        entry.options = {"scan_interval": 30}
        entry.update_listeners = entry.listeners
        await self.integration.async_setup_entry(self.ha, entry)
        self.entries.append(entry)
        return entry

    def flow(self, source):
        flow = self.flow_module.ZendureConfigFlow()
        flow.hass = self.ha
        flow.context = {"source": source}
        flow.unique_id = None
        flow._async_probe = AsyncMock(return_value=("HUB-TEST", {"sn": "HUB-TEST"}))
        return flow

    async def discover(self, flow, host):
        if flow.source == "user":
            return await flow.async_step_user({"host": host})
        return await flow.async_step_zeroconf(
            SimpleNamespace(
                host=host,
                port=80,
                name="Zendure-SolarFlow2400Pro-ABC._zendure._tcp.local.",
            )
        )

    def test_zeroconf_honors_advertised_http_port_and_ipv6(self):
        for host, port, expected in (
            ("192.0.2.1", None, "192.0.2.1"),
            ("192.0.2.1", 80, "192.0.2.1"),
            ("192.0.2.1", 8080, "192.0.2.1:8080"),
            ("2001:db8::1", 80, "[2001:db8::1]"),
            ("2001:db8::1", 8080, "[2001:db8::1]:8080"),
        ):
            with self.subTest(host=host, port=port):
                self.assertEqual(
                    self.flow_module._host_from_zeroconf(
                        SimpleNamespace(host=host, port=port)
                    ),
                    expected,
                )

    async def test_zeroconf_port_change_reloads_once_and_probes_advertised_port(self):
        entry = await self.installed_entry()
        flow = self.flow("zeroconf")
        with self.assertRaises(AbortFlow):
            await flow.async_step_zeroconf(
                SimpleNamespace(
                    host="192.0.2.1",
                    port=8080,
                    name="Zendure-SolarFlow2400Pro-ABC._zendure._tcp.local.",
                )
            )
        await asyncio.gather(*self.tasks)
        flow._async_probe.assert_awaited_once_with("192.0.2.1:8080")
        self.assertEqual(entry.data["host"], "192.0.2.1:8080")
        self.assertEqual(self.reloads, [entry.entry_id])

    async def test_manual_ip_change_reloads_once_via_listener(self):
        entry = await self.installed_entry()
        with self.assertRaises(AbortFlow) as raised:
            await self.discover(self.flow("user"), "192.0.2.2")
        await asyncio.gather(*self.tasks)
        self.assertEqual(raised.exception.reason, "already_configured")
        self.assertEqual(entry.data["host"], "192.0.2.2")
        self.assertEqual(entry.unique_id, "HUB-TEST")
        self.assertEqual(entry.options, {"scan_interval": 30})
        self.assertEqual(self.reloads, [entry.entry_id])
        self.assertEqual(self.flow_reload_requests, [])

    async def test_zeroconf_ip_change_reloads_once_via_listener(self):
        entry = await self.installed_entry()
        with self.assertRaises(AbortFlow):
            await self.discover(self.flow("zeroconf"), "192.0.2.2")
        await asyncio.gather(*self.tasks)
        self.assertEqual(entry.data["host"], "192.0.2.2")
        self.assertEqual(self.reloads, [entry.entry_id])
        self.assertEqual(self.flow_reload_requests, [])

    async def test_same_ip_does_not_reload_in_either_flow(self):
        entry = await self.installed_entry()
        for source in ("user", "zeroconf"):
            with self.subTest(source=source), self.assertRaises(AbortFlow):
                await self.discover(self.flow(source), entry.data["host"])
        self.assertEqual(self.reloads, [])
        self.assertEqual(self.tasks, [])

    async def test_probe_failure_preserves_existing_entry_and_does_not_reload(self):
        entry = await self.installed_entry()
        for source in ("user", "zeroconf"):
            flow = self.flow(source)
            flow._async_probe.side_effect = ApiError("offline")
            result = await self.discover(flow, "192.0.2.2")
            self.assertIn(result["type"], ("form", "abort"))
        self.assertEqual(entry.data["host"], "192.0.2.1")
        self.assertEqual(self.reloads, [])

    async def test_new_manual_device_still_creates_entry(self):
        result = await self.discover(self.flow("user"), "192.0.2.2")
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["serial"], "HUB-TEST")
        self.assertEqual(result["data"]["host"], "192.0.2.2")
        self.assertEqual(self.reloads, [])

    async def test_new_zeroconf_device_still_requires_confirmation(self):
        flow = self.flow("zeroconf")
        result = await self.discover(flow, "192.0.2.2")
        self.assertEqual(
            (result["type"], result["step_id"]), ("form", "zeroconf_confirm")
        )
        result = await flow.async_step_zeroconf_confirm({})
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["serial"], "HUB-TEST")
        self.assertEqual(result["data"]["model"], "SolarFlow2400Pro")

    async def test_options_update_still_reloads_via_existing_listener(self):
        entry = await self.installed_entry()
        flow = self.flow_module.ZendureConfigFlow.async_get_options_flow(entry)
        flow.config_entry = entry
        options = {
            "scan_interval": 60,
            "command_validation": True,
            "skip_unchanged": False,
        }
        result = await flow.async_step_init(options)
        self.ha.config_entries.async_update_entry(entry, options=result["data"])
        await asyncio.gather(*self.tasks)
        self.assertEqual(entry.options, options)
        self.assertEqual(self.reloads, [entry.entry_id])

    async def test_options_form_exposes_duplicate_suppression_without_target_import(
        self,
    ):
        entry = await self.installed_entry()
        flow = self.flow_module.ZendureConfigFlow.async_get_options_flow(entry)
        flow.config_entry = entry
        result = await flow.async_step_init()
        self.assertIn("skip_unchanged", result["data_schema"])
        self.assertNotIn("target_import", result["data_schema"])

    async def test_discovery_of_retrying_entry_still_schedules_reload(self):
        entry = await self.installed_entry()
        entry.state = "retry"
        entry.update_listeners.clear()
        with self.assertRaises(AbortFlow):
            await self.discover(self.flow("zeroconf"), entry.data["host"])
        self.assertEqual(self.reloads, [entry.entry_id])
        self.assertEqual(self.flow_reload_requests, [entry.entry_id])

    async def test_reference_helper_detects_old_double_reload_combination(self):
        await self.installed_entry()
        flow = self.flow("user")
        await flow.async_set_unique_id("HUB-TEST")
        with self.assertRaisesRegex(RuntimeError, "combined with update listener"):
            flow._abort_if_unique_id_configured(updates={"host": "192.0.2.2"})
