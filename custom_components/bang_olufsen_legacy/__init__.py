from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant

from custom_components.bang_olufsen_legacy.coordinator import BangOlufsenLegacyCoordinator

type BangOlufsenLegacyConfigEntry = ConfigEntry[BangOlufsenLegacyCoordinator]

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER, Platform.SELECT, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: BangOlufsenLegacyConfigEntry) -> bool:
    coordinator = BangOlufsenLegacyCoordinator(hass, entry.data[CONF_HOST])
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BangOlufsenLegacyConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok
