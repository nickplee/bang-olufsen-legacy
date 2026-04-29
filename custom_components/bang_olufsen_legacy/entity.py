from __future__ import annotations

from typing import Any

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.bang_olufsen_legacy import BangOlufsenLegacyConfigEntry
from custom_components.bang_olufsen_legacy.const import DOMAIN
from custom_components.bang_olufsen_legacy.coordinator import BangOlufsenLegacyCoordinator


class BangOlufsenLegacyEntity(CoordinatorEntity[BangOlufsenLegacyCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, entry: BangOlufsenLegacyConfigEntry, suffix: str) -> None:
        super().__init__(entry.runtime_data)
        self._entry = entry
        serial = self.device_info_data.get("serialNumber", entry.entry_id)
        self._attr_unique_id = f"{serial}_{suffix}"

    @property
    def device_info_data(self) -> dict[str, Any]:
        return self.coordinator.data.get("device", {}) if self.coordinator.data else {}

    @property
    def device_info(self) -> dict[str, Any]:
        device = self.device_info_data
        serial = device.get("serialNumber", self._entry.entry_id)
        return {
            "identifiers": {(DOMAIN, serial)},
            "manufacturer": "Bang & Olufsen",
            "name": device.get("productFriendlyName") or "Bang & Olufsen Legacy",
            "model": device.get("productType") or device.get("typeNumber"),
            "sw_version": device.get("softwareVersion"),
        }
