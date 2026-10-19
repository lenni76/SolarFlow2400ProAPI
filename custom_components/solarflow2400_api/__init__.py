"""The SolarFlow2400-API integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .coordinator import ZendureConfigEntry, ZendureCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ZendureConfigEntry) -> bool:
    """Set up SolarFlow2400-API from a config entry."""
    coordinator = ZendureCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    # Pack entities resolve their via_device_id while platforms are being set up.
    # Register the hub first; unchanged identifiers reuse its existing device ID.
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, coordinator.serial)},
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ZendureConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: ZendureConfigEntry
) -> None:
    """Reload after options or connection data change, including the host."""
    await hass.config_entries.async_reload(entry.entry_id)
