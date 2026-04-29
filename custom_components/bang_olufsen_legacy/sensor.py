from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.bang_olufsen_legacy import BangOlufsenLegacyConfigEntry
from custom_components.bang_olufsen_legacy.entity import BangOlufsenLegacyEntity


@dataclass(frozen=True, kw_only=True)
class BangOlufsenLegacySensorDescription(SensorEntityDescription):
    value_key: str


SENSORS = (
    BangOlufsenLegacySensorDescription(
        key="software_version",
        translation_key="software_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_key="softwareVersion",
    ),
    BangOlufsenLegacySensorDescription(
        key="setup_version",
        translation_key="setup_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_key="setup_version",
    ),
    BangOlufsenLegacySensorDescription(
        key="setup_health",
        translation_key="setup_health",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_key="setup_health",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([BangOlufsenLegacySensor(entry, description) for description in SENSORS])  # type: ignore[arg-type]


class BangOlufsenLegacySensor(BangOlufsenLegacyEntity, SensorEntity):
    entity_description: BangOlufsenLegacySensorDescription

    def __init__(
        self,
        entry: BangOlufsenLegacyConfigEntry,
        description: BangOlufsenLegacySensorDescription,
    ) -> None:
        super().__init__(entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | int | None:
        data = self.coordinator.data
        if not data:
            return None
        key = self.entity_description.value_key
        if key == "softwareVersion":
            return data.get("device", {}).get("softwareVersion")
        value: Any = data.get(key)
        if isinstance(value, dict):
            return value.get("version") or value.get("status")
        if isinstance(value, str | int):
            return value
        return None
