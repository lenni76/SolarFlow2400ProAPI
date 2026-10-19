"""Real HA setup, registry, entity/service and unload tests; simulated HTTP API."""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
from custom_components.solarflow2400_api.const import DOMAIN
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

REPORT = json.loads(
    (
        Path(__file__).parents[1] / "tests/fixtures/solarflow2400pro_report.json"
    ).read_text()
)


def entry_for(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="HUB-TEST",
        title="SolarFlow test",
        data={"serial": "HUB-TEST", "host": "192.0.2.1", "model": "SolarFlow"},
        options={"validation_delay": 1, "auto_recovery": False},
        version=1,
    )
    entry.add_to_hass(hass)
    return entry


def entity_for(hass, entry, unique_id):
    return next(
        entity
        for entity in er.async_entries_for_config_entry(
            er.async_get(hass), entry.entry_id
        )
        if entity.unique_id == unique_id
    )


@pytest.fixture
def simulated_api():
    report = deepcopy(REPORT)

    async def read(*args):
        return deepcopy(report)

    async def write(serial, key, value):
        assert serial == "HUB-TEST"
        report["properties"][key] = value
        return {}

    with (
        patch(
            "custom_components.solarflow2400_api.api.ZendureLocalApi.async_get_report",
            side_effect=read,
        ),
        patch(
            "custom_components.solarflow2400_api.api.ZendureLocalApi.async_write_property",
            side_effect=write,
        ) as post,
    ):
        yield report, post


async def test_real_setup_links_internal_battery_and_unloads(hass, simulated_api):
    entry = entry_for(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = dr.async_get(hass)
    parent = registry.async_get_device_by_identifier(
        (DOMAIN, "HUB-TEST"), config_entry_id=entry.entry_id
    )
    battery = registry.async_get_device_by_identifier(
        (DOMAIN, "PACK-TEST"), config_entry_id=entry.entry_id
    )
    assert parent is not None and battery is not None
    assert battery.via_device_id == parent.id
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert len({item.unique_id for item in entities}) == len(entities)
    voltage = entity_for(hass, entry, "PACK-TEST_totalVol")
    assert float(hass.states.get(voltage.entity_id).state) == 47.8
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_existing_device_identity_and_user_names_survive_setup(
    hass, simulated_api
):
    entry = entry_for(hass)
    registry = dr.async_get(hass)
    parent = registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "HUB-TEST")}
    )
    battery = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "PACK-TEST")},
        via_device_id=parent.id,
    )
    registry.async_update_device(parent.id, name_by_user="Mein Speicher")
    entities = er.async_get(hass)
    old_output = entities.async_get_or_create(
        "number",
        DOMAIN,
        "HUB-TEST_outputLimit",
        config_entry=entry,
        device_id=parent.id,
        suggested_object_id="bisheriges_ausgangslimit",
        original_name="outputLimit",
    )
    entities.async_update_entity(old_output.entity_id, name="Meine Leistungsgrenze")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert (
        registry.async_get_device_by_identifier(
            (DOMAIN, "HUB-TEST"), config_entry_id=entry.entry_id
        ).id
        == parent.id
    )
    assert (
        registry.async_get_device_by_identifier(
            (DOMAIN, "PACK-TEST"), config_entry_id=entry.entry_id
        ).id
        == battery.id
    )
    assert registry.async_get(parent.id).name_by_user == "Mein Speicher"
    after = entity_for(hass, entry, "HUB-TEST_outputLimit")
    assert after.entity_id == old_output.entity_id
    assert after.name == "Meine Leistungsgrenze"


async def test_real_number_service_confirms_write_and_shows_reported_bounds(
    hass, simulated_api
):
    entry = entry_for(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    output = entity_for(hass, entry, "HUB-TEST_outputLimit")
    state = hass.states.get(output.entity_id)
    assert state.attributes["max"] == 1000
    assert state.attributes["step"] == 1
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": output.entity_id, "value": 300},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert entry.runtime_data.diagnostics.command_success is True
    assert float(hass.states.get(output.entity_id).state) == 300
    simulated_api[1].assert_awaited_once_with("HUB-TEST", "outputLimit", 300)


async def test_real_number_service_propagates_ignored_command_error(
    hass, simulated_api
):
    entry = entry_for(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    simulated_api[1].side_effect = None
    simulated_api[1].return_value = {}
    output = entity_for(hass, entry, "HUB-TEST_outputLimit")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": output.entity_id, "value": 300},
            blocking=True,
        )
    assert entry.runtime_data.diagnostics.command_success is False
    assert simulated_api[1].await_count == 2
