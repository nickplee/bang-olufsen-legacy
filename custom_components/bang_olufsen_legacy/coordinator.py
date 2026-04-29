from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from custom_components.bang_olufsen_legacy.api import BeoClient, BeoError, create_beo_client
from custom_components.bang_olufsen_legacy.const import (
    CONTROL_PORT,
    DOMAIN,
    SETUP_PORT,
    UPDATE_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


class BangOlufsenLegacyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        *,
        client_factory: Callable[..., BeoClient] = create_beo_client,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.host = host
        self.client = client_factory(host=host, control_port=CONTROL_PORT, setup_port=SETUP_PORT)
        self._notify_task: asyncio.Task[None] | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data: dict[str, Any] = {
                "services": await self.client.services(),
                "device": await self.client.device.get_info(),
                "features": await self.client.zone.get_features(),
                "sources": await self.client.zone.get_sources(),
                "active_sources": await self.client.zone.get_active_sources(),
                "speaker": await self.client.volume.get_speaker(),
            }
            await self._optional(data, "queue", self.client.queue.get)
            await self._optional(data, "netradio", self.client.content.get_netradio_profile)
            await self._optional(data, "setup_version", self.client.setup.get_version)
            await self._optional(data, "setup_health", self.client.setup.get_index)
            await self._optional(data, "line_in", self.client.device.line_in.get)
            if self._notify_task is None or self._notify_task.done():
                self._notify_task = asyncio.create_task(self._listen_for_notifications())
            return data
        except BeoError as exc:
            raise UpdateFailed(exc.message) from exc

    async def _optional(
        self,
        data: dict[str, Any],
        key: str,
        getter: Callable[[], Awaitable[dict[str, Any]]],
    ) -> None:
        try:
            data[key] = await getter()
        except BeoError as exc:
            data[f"{key}_error"] = exc.to_dict()

    async def _listen_for_notifications(self) -> None:
        try:
            async for notification in self.client.notify.stream():
                data = dict(self.data or {})
                data["last_notification"] = notification
                notification_type = notification.get("type")
                if notification_type == "VOLUME" and notification.get("volume"):
                    data["speaker"] = notification["volume"]["speaker"]
                if notification_type == "SOURCE" and notification.get("source"):
                    data["active_sources"] = notification["source"]
                if notification_type == "PROGRESS_INFORMATION" and notification.get("progress"):
                    data["progress"] = notification["progress"]
                self.async_set_updated_data(data)
        except asyncio.CancelledError:
            raise
        except BeoError:
            return

    async def async_shutdown(self) -> None:
        if self._notify_task is not None:
            self._notify_task.cancel()
            await asyncio.gather(self._notify_task, return_exceptions=True)
        await self.client.aclose()
