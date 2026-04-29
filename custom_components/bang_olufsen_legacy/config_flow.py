from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST

from custom_components.bang_olufsen_legacy.api import BeoError, create_beo_client
from custom_components.bang_olufsen_legacy.const import CONTROL_PORT, DOMAIN, SETUP_PORT


class BangOlufsenLegacyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            try:
                device_info = await _validate_host(host)
            except BeoError as exc:
                errors["base"] = (
                    "unsupported" if exc.code == "UNSUPPORTED_OPERATION" else "cannot_connect"
                )
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                serial = device_info["serialNumber"]
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                title = device_info.get("productFriendlyName") or f"Bang & Olufsen {serial}"
                return self.async_create_entry(title=title, data={CONF_HOST: host})

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}),
            errors=errors,
        )


async def _validate_host(host: str) -> dict[str, Any]:
    async with create_beo_client(
        host,
        control_port=CONTROL_PORT,
        setup_port=SETUP_PORT,
    ) as client:
        await client.services()
        return await client.device.get_info()
