from __future__ import annotations

from typing import Any

from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.components.media_player.const import MediaPlayerEntityFeature, MediaPlayerState
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.bang_olufsen_legacy import BangOlufsenLegacyConfigEntry
from custom_components.bang_olufsen_legacy.api.errors import BeoError
from custom_components.bang_olufsen_legacy.entity import BangOlufsenLegacyEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([BangOlufsenLegacyMediaPlayer(entry)])  # type: ignore[arg-type]


class BangOlufsenLegacyMediaPlayer(BangOlufsenLegacyEntity, MediaPlayerEntity):
    _attr_name = None

    def __init__(self, entry: BangOlufsenLegacyConfigEntry) -> None:
        super().__init__(entry, "media_player")

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        features = MediaPlayerEntityFeature.SELECT_SOURCE | MediaPlayerEntityFeature.VOLUME_SET
        features |= MediaPlayerEntityFeature.VOLUME_MUTE
        zone_features = set(self._zone_features)
        if "PLAY" in zone_features:
            features |= MediaPlayerEntityFeature.PLAY
        if "PAUSE" in zone_features:
            features |= MediaPlayerEntityFeature.PAUSE
        if "STOP" in zone_features:
            features |= MediaPlayerEntityFeature.STOP
        if "TOGGLE_POWER" in zone_features:
            features |= MediaPlayerEntityFeature.TURN_ON | MediaPlayerEntityFeature.TURN_OFF
        if self._progress.get("seekSupported") and self._progress.get("playQueueItemId"):
            features |= MediaPlayerEntityFeature.SEEK
        return features

    @property
    def _zone_features(self) -> list[str]:
        return self.coordinator.data.get("features", {}).get("features", [])

    @property
    def _active_sources(self) -> dict[str, Any]:
        return self.coordinator.data.get("active_sources", {})

    @property
    def _speaker(self) -> dict[str, Any]:
        return self.coordinator.data.get("speaker", {})

    @property
    def _progress(self) -> dict[str, Any]:
        return self.coordinator.data.get("progress", {})

    @property
    def state(self) -> MediaPlayerState:
        primary_experience = self._active_sources.get("primaryExperience") or {}
        state = self._progress.get("state") or primary_experience.get("state")
        if state == "PLAY":
            return MediaPlayerState.PLAYING
        if state == "PAUSE":
            return MediaPlayerState.PAUSED
        if state == "STOP":
            return MediaPlayerState.IDLE
        if self._active_sources.get("primary"):
            return MediaPlayerState.ON
        return MediaPlayerState.OFF

    @property
    def source_list(self) -> list[str]:
        return [source["id"] for source in self.coordinator.data.get("sources", [])]

    @property
    def source(self) -> str | None:
        return self._active_sources.get("primary")

    @property
    def volume_level(self) -> float | None:
        level = self._speaker.get("level")
        volume_range = self._speaker.get("range")
        if not isinstance(level, int) or not isinstance(volume_range, dict):
            return None
        minimum = volume_range.get("minimum", 0)
        maximum = volume_range.get("maximum", 100)
        if maximum <= minimum:
            return None
        return (level - minimum) / (maximum - minimum)

    @property
    def is_volume_muted(self) -> bool | None:
        muted = self._speaker.get("muted")
        return muted if isinstance(muted, bool) else None

    @property
    def media_position(self) -> float | None:
        position = self._progress.get("position")
        return position if isinstance(position, int | float) else None

    @property
    def media_duration(self) -> float | None:
        duration = self._progress.get("totalDuration")
        return duration if isinstance(duration, int | float) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "active_source": self.source,
            "play_queue_id": self._progress.get("playQueueId"),
            "play_queue_item_id": self._progress.get("playQueueItemId"),
        }

    async def async_media_play(self) -> None:
        await self.coordinator.client.zone.command("play")
        await self.coordinator.async_request_refresh()

    async def async_media_pause(self) -> None:
        await self.coordinator.client.zone.command("pause")
        await self.coordinator.async_request_refresh()

    async def async_media_stop(self) -> None:
        await self.coordinator.client.zone.command("stop")
        await self.coordinator.async_request_refresh()

    async def async_select_source(self, source: str) -> None:
        sources = self.coordinator.data.get("sources", [])
        match = next((item for item in sources if item.get("id") == source), {})
        product = match.get("product") if isinstance(match, dict) else None
        await self.coordinator.client.zone.set_active_source(
            source,
            {
                "friendlyName": match.get("friendlyName"),
                "productJabberId": product.get("jid") if isinstance(product, dict) else None,
                "productFriendlyName": (
                    product.get("friendlyName") if isinstance(product, dict) else None
                ),
            },
        )
        await self.coordinator.async_request_refresh()

    async def async_set_volume_level(self, volume: float) -> None:
        volume_range = self._speaker.get("range", {})
        minimum = volume_range.get("minimum", 0)
        maximum = volume_range.get("maximum", 100)
        level = round(minimum + (maximum - minimum) * volume)
        await self.coordinator.client.volume.set_speaker_level(level)
        await self.coordinator.async_request_refresh()

    async def async_mute_volume(self, mute: bool) -> None:
        await self.coordinator.client.volume.set_speaker_muted(mute)
        await self.coordinator.async_request_refresh()

    async def async_media_seek(self, position: float) -> None:
        play_queue_item_id = self._progress.get("playQueueItemId")
        if not isinstance(play_queue_item_id, str):
            raise BeoError.unsupported("Current media item does not support seeking.")
        await self.coordinator.client.queue.seek(
            {"playQueueItemId": play_queue_item_id, "positionSeconds": round(position)}
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        if self.state == MediaPlayerState.OFF:
            await self.coordinator.client.zone.command("toggle-power")
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        if self.state != MediaPlayerState.OFF:
            await self.coordinator.client.zone.command("toggle-power")
            await self.coordinator.async_request_refresh()
