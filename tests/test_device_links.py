"""Isolated device-link regression tests; no running HA instance is required.

Executes the integration's complete setup and entity modules against minimal HA
test doubles. This checks identity, lookup scope, ordering and API usage; it does
not replace a live Home Assistant device-registry integration test.

Run: python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import unittest
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "custom_components/solarflow2400_api"
DOMAIN = "solarflow2400_api"
PACKAGE = "_solarflow_device_link_subject"


class Platform(StrEnum):
    BINARY_SENSOR = "binary_sensor"
    NUMBER = "number"
    SELECT = "select"
    SENSOR = "sensor"
    SWITCH = "switch"


@dataclass(kw_only=True)
class DeviceInfoDataclass:
    """Accept current fields only, without dict-compatible unpacking."""

    identifiers: set[tuple[str, str]]
    manufacturer: str | None = None
    model: str | None = None
    name: str | None = None
    serial_number: str | None = None
    configuration_url: str | None = None
    via_device_id: str | None = None


class Registry:
    def __init__(self):
        self.devices = {}
        self.lookups = []

    def async_get_or_create(self, *, config_entry_id, identifiers, **metadata):
        if "via_device" in metadata:
            raise AssertionError("deprecated via_device used")
        key = (config_entry_id, frozenset(identifiers))
        if key not in self.devices:
            self.devices[key] = SimpleNamespace(
                id=f"registry-{len(self.devices) + 1}",
                identifiers=identifiers,
                config_entry_id=config_entry_id,
                name_by_user=None,
            )
        device = self.devices[key]
        for field, value in metadata.items():
            setattr(device, field, value)
        return device

    def get_id(self, identifier, *, config_entry_id):
        self.lookups.append((config_entry_id, identifier))
        try:
            return self.devices[(config_entry_id, frozenset({identifier}))].id
        except KeyError as error:
            raise ValueError("parent must be registered first") from error


class Entry:
    def __init__(self, entry_id):
        self.entry_id = entry_id
        self.data = {"serial": "HUB-TEST", "host": "192.0.2.1", "model": "SolarFlow"}
        self.cleanup = []
        self.listeners = []

    def add_update_listener(self, listener):
        self.listeners.append(listener)
        return lambda: None

    def async_on_unload(self, callback):
        self.cleanup.append(callback)


class Coordinator:
    def __init__(self, hass, entry):
        self.hass = hass
        self.config_entry = entry
        self.serial = entry.data["serial"]
        self.model = entry.data["model"]
        self.api = SimpleNamespace(host=entry.data["host"])
        self.last_update_success = True
        self.data = SimpleNamespace(device={"electricLevel": 50}, packs={})

    async def async_config_entry_first_refresh(self):
        if self.hass.fail_refresh:
            raise RuntimeError("simulated first refresh failure")


class CoordinatorEntity:
    @classmethod
    def __class_getitem__(cls, _):
        return cls

    def __init__(self, coordinator):
        self.coordinator = coordinator

    @property
    def available(self):
        return self.coordinator.last_update_success


def module(name, **attributes):
    result = ModuleType(name)
    result.__dict__.update(attributes)
    return result


def device_metadata(info):
    if isinstance(info, dict):
        return info
    return {key: value for key, value in vars(info).items() if value is not None}


class IntegrationTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.registry = Registry()
        self.device_info_factory = dict

        def make_info(**kwargs):
            if "via_device" in kwargs:
                raise AssertionError("deprecated DeviceInfo field")
            return self.device_info_factory(**kwargs)

        modules = {
            "homeassistant": module("homeassistant"),
            "homeassistant.const": module("homeassistant.const", Platform=Platform),
            "homeassistant.core": module("homeassistant.core", HomeAssistant=object),
            "homeassistant.helpers": module("homeassistant.helpers"),
            "homeassistant.helpers.device_registry": module(
                "homeassistant.helpers.device_registry",
                DeviceInfo=make_info,
                async_get=lambda hass: self.registry,
                async_get_device_id_by_identifier=(
                    lambda hass, identifier, *, config_entry_id: self.registry.get_id(
                        identifier, config_entry_id=config_entry_id
                    )
                ),
            ),
            "homeassistant.helpers.update_coordinator": module(
                "homeassistant.helpers.update_coordinator",
                CoordinatorEntity=CoordinatorEntity,
            ),
            f"{PACKAGE}.coordinator": module(
                f"{PACKAGE}.coordinator",
                ZendureConfigEntry=Entry,
                ZendureCoordinator=Coordinator,
            ),
        }
        self.patcher = patch.dict(sys.modules, modules)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        spec = importlib.util.spec_from_file_location(
            PACKAGE, SOURCE / "__init__.py", submodule_search_locations=[str(SOURCE)]
        )
        self.integration = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = self.integration
        self.addCleanup(self.remove_subject_modules)
        spec.loader.exec_module(self.integration)
        entity_spec = importlib.util.spec_from_file_location(
            f"{PACKAGE}.entity", SOURCE / "entity.py"
        )
        self.entities = importlib.util.module_from_spec(entity_spec)
        sys.modules[entity_spec.name] = self.entities
        entity_spec.loader.exec_module(self.entities)
        self.forwarded = []
        self.battery_keys = (
            "socLevel",
            "power",
            "totalVol",
            "maxVol",
            "minVol",
            "maxTemp",
            "batcur",
            "state",
            "softVersion",
        )

    def remove_subject_modules(self):
        for name in list(sys.modules):
            if name == PACKAGE or name.startswith(f"{PACKAGE}."):
                del sys.modules[name]

    def hass(self):
        async def forward(entry, platforms):
            self.assertEqual(len(platforms), 5)
            coordinator = entry.runtime_data
            # Deliberately process batteries before any main-device entity.
            for key in self.battery_keys:
                battery = self.entities.ZendurePackEntity(coordinator, "PACK-TEST", key)
                info = device_metadata(battery.device_info)
                registered = self.registry.async_get_or_create(
                    config_entry_id=entry.entry_id, **info
                )
                self.forwarded.append((battery._attr_unique_id, registered.id))
            main = self.entities.ZendureDeviceEntity(coordinator, "electricLevel")
            self.registry.async_get_or_create(
                config_entry_id=entry.entry_id, **device_metadata(main.device_info)
            )

        return SimpleNamespace(
            fail_refresh=False,
            config_entries=SimpleNamespace(async_forward_entry_setups=forward),
        )


class DeviceLinkTests(IntegrationTestCase):
    async def test_first_install_registers_parent_before_battery_entities(self):
        entry = Entry("entry-a")
        self.assertTrue(await self.integration.async_setup_entry(self.hass(), entry))
        self.assertEqual(len(self.registry.devices), 2)
        parent = self.registry.devices[("entry-a", frozenset({(DOMAIN, "HUB-TEST")}))]
        battery = self.registry.devices[("entry-a", frozenset({(DOMAIN, "PACK-TEST")}))]
        self.assertEqual(battery.via_device_id, parent.id)
        self.assertEqual(len(self.forwarded), 9)

    async def test_existing_devices_and_unique_ids_survive_update(self):
        parent = self.registry.async_get_or_create(
            config_entry_id="entry-a", identifiers={(DOMAIN, "HUB-TEST")}
        )
        parent.name_by_user = "Mein Speicher"
        battery = self.registry.async_get_or_create(
            config_entry_id="entry-a",
            identifiers={(DOMAIN, "PACK-TEST")},
            via_device_id=parent.id,
        )
        battery.name_by_user = "Interne Batterie"
        existing_ids = (parent.id, battery.id)
        await self.integration.async_setup_entry(self.hass(), Entry("entry-a"))
        self.assertEqual((parent.id, battery.id), existing_ids)
        self.assertEqual(
            (parent.name_by_user, battery.name_by_user),
            ("Mein Speicher", "Interne Batterie"),
        )
        self.assertEqual(len(self.registry.devices), 2)
        self.assertEqual(
            self.forwarded,
            [(f"PACK-TEST_{key}", battery.id) for key in self.battery_keys],
        )

    async def test_lookup_is_scoped_to_owning_config_entry(self):
        wrong = self.registry.async_get_or_create(
            config_entry_id="other-entry", identifiers={(DOMAIN, "HUB-TEST")}
        )
        await self.integration.async_setup_entry(self.hass(), Entry("entry-a"))
        battery = self.registry.devices[("entry-a", frozenset({(DOMAIN, "PACK-TEST")}))]
        self.assertNotEqual(battery.via_device_id, wrong.id)
        self.assertTrue(all(entry == "entry-a" for entry, _ in self.registry.lookups))

    async def test_reload_reuses_devices(self):
        entry = Entry("entry-a")
        hass = self.hass()
        await self.integration.async_setup_entry(hass, entry)
        ids = {key: value.id for key, value in self.registry.devices.items()}
        await self.integration.async_setup_entry(hass, entry)
        self.assertEqual(
            {key: value.id for key, value in self.registry.devices.items()}, ids
        )

    async def test_future_dataclass_device_info_needs_no_mapping_operations(self):
        self.device_info_factory = DeviceInfoDataclass
        await self.integration.async_setup_entry(self.hass(), Entry("entry-a"))
        self.assertEqual(len(self.registry.devices), 2)

    async def test_failed_first_refresh_does_not_register_or_forward(self):
        hass = self.hass()
        hass.fail_refresh = True
        with self.assertRaisesRegex(RuntimeError, "first refresh"):
            await self.integration.async_setup_entry(hass, Entry("entry-a"))
        self.assertEqual(self.registry.devices, {})
        self.assertEqual(self.forwarded, [])

    async def test_dynamically_discovered_pack_uses_same_parent(self):
        entry = Entry("entry-a")
        await self.integration.async_setup_entry(self.hass(), entry)
        new_pack = self.entities.ZendurePackEntity(
            entry.runtime_data, "NEW-PACK", "socLevel"
        )
        info = device_metadata(new_pack.device_info)
        parent = self.registry.devices[("entry-a", frozenset({(DOMAIN, "HUB-TEST")}))]
        self.assertEqual(info["via_device_id"], parent.id)
        self.assertEqual(new_pack._attr_unique_id, "NEW-PACK_socLevel")

    def test_no_deprecated_via_device_keyword_remains(self):
        tree = ast.parse((SOURCE / "entity.py").read_text())
        keywords = [
            node.arg for node in ast.walk(tree) if isinstance(node, ast.keyword)
        ]
        self.assertIn("via_device_id", keywords)
        self.assertNotIn("via_device", keywords)


if __name__ == "__main__":
    unittest.main()
