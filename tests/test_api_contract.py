"""Isolated contract tests against zenSDK 1.0.2 and a real anonymized report.

HA platform services are doubles. HTTP decoding uses aiohttp's real JSON decoder
with response bytes, without opening a network connection or writing a device.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import aiohttp
import test_device_links as shared

FIXTURES = shared.SOURCE.parents[1] / "tests/fixtures"


@dataclass(frozen=True, kw_only=True)
class Description:
    key: str
    name: str | None = None
    native_unit_of_measurement: Any = None
    device_class: Any = None
    state_class: Any = None
    entity_category: Any = None
    entity_registry_enabled_default: bool = True
    suggested_display_precision: int | None = None
    native_min_value: float = 0
    native_max_value: float = 100
    native_step: float = 1
    mode: Any = None


class ApiContractTests(shared.IntegrationTestCase):
    def load(self, name):
        spec = importlib.util.spec_from_file_location(
            f"{shared.PACKAGE}.{name}", shared.SOURCE / f"{name}.py"
        )
        loaded = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = loaded
        spec.loader.exec_module(loaded)
        return loaded

    def setUp(self):
        super().setUp()
        const = sys.modules["homeassistant.const"]
        const.EntityCategory = SimpleNamespace(DIAGNOSTIC="diagnostic", CONFIG="config")
        const.PERCENTAGE = "%"
        const.SIGNAL_STRENGTH_DECIBELS_MILLIWATT = "dBm"
        for name, unit, symbol in (
            ("UnitOfPower", "WATT", "W"),
            ("UnitOfElectricCurrent", "AMPERE", "A"),
            ("UnitOfElectricPotential", "VOLT", "V"),
            ("UnitOfTemperature", "CELSIUS", "°C"),
            ("UnitOfTime", "MINUTES", "min"),
        ):
            setattr(const, name, SimpleNamespace(**{unit: symbol}))
        sys.modules["homeassistant.core"].callback = lambda func: func
        sys.modules["homeassistant.helpers.entity_platform"] = shared.module(
            "homeassistant.helpers.entity_platform",
            AddConfigEntryEntitiesCallback=object,
        )
        classes = SimpleNamespace(
            POWER="power",
            BATTERY="battery",
            TEMPERATURE="temperature",
            DURATION="duration",
            VOLTAGE="voltage",
            SIGNAL_STRENGTH="signal_strength",
            CURRENT="current",
            SWITCH="switch",
        )
        for platform in ("sensor", "number", "select", "switch"):
            title = platform.title()
            sys.modules[f"homeassistant.components.{platform}"] = shared.module(
                f"homeassistant.components.{platform}",
                **{
                    f"{title}Entity": type(f"{title}Entity", (), {}),
                    f"{title}EntityDescription": Description,
                    f"{title}DeviceClass": classes,
                    f"{title}StateClass": SimpleNamespace(
                        MEASUREMENT="measurement", TOTAL_INCREASING="total_increasing"
                    ),
                    f"{title}Mode": SimpleNamespace(BOX="box", SLIDER="slider"),
                },
            )
        self.sensor = self.load("sensor")
        self.number = self.load("number")
        self.select = self.load("select")
        self.switch = self.load("switch")
        self.api = self.load("api")
        self.contract = json.loads((FIXTURES / "zendure_api_1_0_2.json").read_text())
        self.report = json.loads(
            (FIXTURES / "solarflow2400pro_report.json").read_text()
        )
        # Execute the unchanged normalizer and data class from the real module.
        tree = ast.parse((shared.SOURCE / "coordinator.py").read_text())
        selected = [
            node
            for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef))
            and node.name in {"ZendureData", "_normalize"}
        ]
        namespace = sys.modules[f"{shared.PACKAGE}.coordinator"].__dict__
        namespace.update(dataclass=dataclass, field=field, Any=Any)
        exec(
            compile(
                ast.Module(body=selected, type_ignores=[]), "coordinator.py", "exec"
            ),
            namespace,
        )
        self.normalized = namespace["_normalize"](self.report, "HUB-TEST")
        self.coordinator = shared.Coordinator(self.hass(), shared.Entry("entry-a"))
        self.coordinator.data = self.normalized
        self.coordinator.async_write_property = AsyncMock()

    def test_all_documented_write_properties_have_controls(self):
        descriptions = self.number.NUMBERS + self.select.SELECTS + self.switch.SWITCHES
        self.assertEqual(
            {d.key for d in descriptions}, set(self.contract["write_keys"])
        )
        for description in descriptions:
            bounds = self.contract["write_ranges"][description.key]
            if not bounds:
                continue  # Device-specific UI limits are not manufacturer ranges.
            if hasattr(description, "value_map"):
                values = set(description.value_map.values())
                self.assertEqual(
                    values, set(range(bounds["minimum"], bounds["maximum"] + 1))
                )
            elif hasattr(description, "read_scale"):
                self.assertEqual(description.native_min_value, bounds["minimum"])
                self.assertEqual(description.native_max_value, bounds["maximum"])

    def test_all_documented_battery_fields_have_sensors_or_device_identity(self):
        self.assertEqual(
            {d.key for d in self.sensor.PACK_SENSORS} | {"sn"},
            set(self.contract["pack_report_keys"]),
        )

    async def test_device_report_fields_use_typed_controls_or_disabled_fallback(self):
        self.coordinator.data = SimpleNamespace(
            device=dict.fromkeys(self.contract["device_report_keys"], 0), packs={}
        )
        self.coordinator.async_add_listener = lambda callback: lambda: None
        added = []
        entry = shared.Entry("entry-a")
        entry.runtime_data = self.coordinator
        await self.sensor.async_setup_entry(
            None, entry, lambda entities: added.extend(entities)
        )
        present = {e._key for e in added}
        handled_elsewhere = self.sensor._WRITABLE_KEYS | self.sensor._BINARY_KEYS
        self.assertTrue(
            set(self.contract["device_report_keys"]) <= present | handled_elsewhere
        )
        fallback = {
            e._key: e.entity_description for e in added if e._key == "acCouplingState"
        }
        self.assertFalse(fallback["acCouplingState"].entity_registry_enabled_default)

    def test_real_report_internal_battery_and_unknown_scalars_are_preserved(self):
        self.assertEqual(set(self.normalized.packs), {"PACK-TEST"})
        self.assertEqual(self.normalized.device["socCompSwitch"], 0)
        self.assertEqual(self.normalized.device["offGridState"], 0)
        self.assertEqual(self.normalized.device["acCouplingState"], 57346)
        self.assertEqual(self.normalized.device["oldMode"], 0)
        self.assertEqual(self.normalized.device["smartMode"], 1)

    def test_real_report_sensor_values_and_existing_unique_ids(self):
        device = {d.key: d for d in self.sensor.DEVICE_SENSORS}
        packs = {d.key: d for d in self.sensor.PACK_SENSORS}
        for key, expected in {"hyperTmp": 24.0, "BatVolt": 47.77}.items():
            entity = self.sensor.ZendureDeviceSensor(self.coordinator, device[key])
            self.assertEqual(entity.native_value, expected)
            self.assertEqual(entity._attr_unique_id, f"HUB-TEST_{key}")
        for key, expected in {
            "totalVol": 47.80,
            "batcur": -0.2,
            "maxTemp": 17.0,
            "maxVol": 3.19,
            "minVol": 3.16,
            "packType": 500,
        }.items():
            entity = self.sensor.ZendurePackSensor(
                self.coordinator, "PACK-TEST", packs[key]
            )
            self.assertEqual(entity.native_value, expected)
            self.assertEqual(entity._attr_unique_id, f"PACK-TEST_{key}")
        self.coordinator.async_write_property.assert_not_called()

    def test_current_signed_unsigned_boundaries_and_invalid_values(self):
        for raw, expected in (
            (65534, -0.2),
            (-2, -0.2),
            (0, 0),
            (32767, 3276.7),
            (32768, -3276.8),
            (65535, -0.1),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(self.sensor._battery_current_to_a(raw), expected)
        for raw in (
            None,
            True,
            "invalid",
            1.5,
            65536,
            -32769,
            float("nan"),
            float("inf"),
        ):
            with self.subTest(raw=raw):
                self.assertIsNone(self.sensor._battery_current_to_a(raw))

    async def test_soc_read_and_write_scaling_matches_device_report(self):
        for key, percent, wire in (("socSet", 99, 990), ("minSoc", 6, 60)):
            description = next(d for d in self.number.NUMBERS if d.key == key)
            entity = self.number.ZendureNumber(self.coordinator, description)
            self.assertEqual(entity.native_value, percent)
            await entity.async_set_native_value(percent)
            self.coordinator.async_write_property.assert_awaited_with(key, wire)

    def test_absent_pack_fields_do_not_fabricate_values(self):
        description = next(d for d in self.sensor.PACK_SENSORS if d.key == "heatState")
        entity = self.sensor.ZendurePackSensor(
            self.coordinator, "PACK-TEST", description
        )
        self.assertIsNone(entity.native_value)
        self.assertFalse(entity.available)

    async def test_http_write_uses_real_decoder_and_exact_single_property_payload(self):
        for body in (b"", b" \n", b'{"ok":true}'):
            with self.subTest(body=body):
                response = Response(body)
                session = Session(response)
                api = self.api.ZendureLocalApi("192.0.2.1:8080", session)
                result = await api.async_write_property("HUB-TEST", "socSet", 990)
                self.assertEqual(result, {"ok": True} if body.startswith(b"{") else {})
                self.assertEqual(
                    session.call,
                    (
                        "post",
                        "http://192.0.2.1:8080/properties/write",
                        {"sn": "HUB-TEST", "properties": {"socSet": 990}},
                    ),
                )

    async def test_http_report_accepts_json_with_unreliable_content_type(self):
        session = Session(Response(json.dumps(self.report).encode()))
        api = self.api.ZendureLocalApi("192.0.2.1", session)
        self.assertEqual(await api.async_get_report(), self.report)
        self.assertEqual(
            session.call[:2], ("get", "http://192.0.2.1/properties/report")
        )

    async def test_http_errors_and_invalid_report_are_rejected(self):
        for body, status in (
            (b"[]", 200),
            (b"", 200),
            (b"not json", 200),
            (b"{}", 400),
            (b"{}", 401),
        ):
            with self.subTest(body=body, status=status):
                api = self.api.ZendureLocalApi(
                    "192.0.2.1", Session(Response(body, status))
                )
                with self.assertRaises(self.api.ZendureApiError):
                    await api.async_get_report()

    def test_ui_power_bounds_follow_reported_limits_with_safe_fallback(self):
        for key, limit_key, expected in (
            ("outputLimit", "inverseMaxPower", 1000),
            ("inputLimit", "chargeMaxLimit", 2400),
        ):
            description = next(d for d in self.number.NUMBERS if d.key == key)
            entity = self.number.ZendureNumber(self.coordinator, description)
            self.assertEqual(entity.native_max_value, expected)
            self.assertEqual(description.native_step, 1)
            for raw in (None, 0, -100, float("nan"), "unknown"):
                self.coordinator.data.device[limit_key] = raw
                self.assertEqual(entity.native_max_value, 2400)

    def test_control_names_are_translated_without_changing_unique_ids_or_options(self):
        de = json.loads((shared.SOURCE / "translations/de.json").read_text())
        for platform, descriptions, entity_type in (
            ("number", self.number.NUMBERS, self.number.ZendureNumber),
            ("select", self.select.SELECTS, self.select.ZendureSelect),
            ("switch", self.switch.SWITCHES, self.switch.ZendureSwitch),
        ):
            for description in descriptions:
                entity = entity_type(self.coordinator, description)
                self.assertIn(entity._attr_translation_key, de["entity"][platform])
                self.assertEqual(entity._attr_unique_id, f"HUB-TEST_{description.key}")
        reverse = next(d for d in self.select.SELECTS if d.key == "gridReverse")
        self.assertEqual(reverse.value_map, {"0": 0, "1": 1, "2": 2})

    def test_smartmode_explanation_does_not_write_or_toggle_the_device(self):
        description = next(d for d in self.switch.SWITCHES if d.key == "smartMode")
        entity = self.switch.ZendureSwitch(self.coordinator, description)
        self.assertTrue(entity.extra_state_attributes["flash_speicherung_unterdrueckt"])
        self.coordinator.async_write_property.assert_not_called()

    def test_write_counter_sensors_expose_separate_metrics_and_stable_ids(self):
        self.coordinator.diagnostics = SimpleNamespace(
            write_count=12,
            skipped_write_count=8,
            total_retry_count=2,
            recovery_write_count=3,
        )
        for key, attribute, expected in (
            ("api_write_count", "write_count", 12),
            ("skipped_write_count", "skipped_write_count", 8),
            ("retry_write_count", "total_retry_count", 2),
            ("recovery_write_count", "recovery_write_count", 3),
        ):
            entity = self.sensor.ZendureCounterSensor(self.coordinator, key, attribute)
            self.assertEqual(entity.native_value, expected)
            self.assertEqual(entity._attr_unique_id, f"HUB-TEST_{key}")

    def test_translation_structures_match_in_both_languages_and_source(self):
        documents = [
            json.loads((shared.SOURCE / name).read_text())
            for name in ("strings.json", "translations/en.json", "translations/de.json")
        ]

        def keys(value):
            if isinstance(value, dict):
                return {key: keys(item) for key, item in value.items()}
            return "text"

        self.assertEqual(keys(documents[0]), keys(documents[1]))
        self.assertEqual(keys(documents[0]), keys(documents[2]))


class Response:
    """Supply response bytes to aiohttp's actual JSON implementation."""

    json = aiohttp.ClientResponse.json

    def __init__(self, body, status=200):
        self._body = body
        self.status = status
        self.headers = {"Content-Type": "text/plain"}

    def get_encoding(self):
        return "utf-8"

    async def read(self):
        return self._body

    def raise_for_status(self):
        if self.status >= 400:
            raise aiohttp.ClientResponseError(
                SimpleNamespace(real_url="http://test.invalid"), (), status=self.status
            )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class Session:
    def __init__(self, response):
        self.response = response

    def get(self, url):
        self.call = ("get", url, None)
        return self.response

    def post(self, url, *, json):
        self.call = ("post", url, json)
        return self.response
