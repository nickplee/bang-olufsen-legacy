from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.bang_olufsen_legacy import BangOlufsenLegacyConfigEntry
from custom_components.bang_olufsen_legacy.entity import BangOlufsenLegacyEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data  # type: ignore[attr-defined]
    line_in = coordinator.data.get("line_in", {}) if coordinator.data else {}
    if line_in.get("editable"):
        async_add_entities([BangOlufsenLegacyLineInSensitivitySelect(entry)])  # type: ignore[arg-type]


class BangOlufsenLegacyLineInSensitivitySelect(BangOlufsenLegacyEntity, SelectEntity):
    _attr_name = "Line-in sensitivity"

    def __init__(self, entry: BangOlufsenLegacyConfigEntry) -> None:
        super().__init__(entry, "line_in_sensitivity")

    @property
    def current_option(self) -> str | None:
        return self.coordinator.data.get("line_in", {}).get("sensitivity")

    @property
    def options(self) -> list[str]:
        return self.coordinator.data.get("line_in", {}).get("allowedSensitivities", [])

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.client.device.line_in.set_sensitivity(option)
        await self.coordinator.async_request_refresh()
