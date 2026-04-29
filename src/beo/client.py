from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import parse_qs, quote, urlparse

import httpx
from pydantic import RootModel, ValidationError

from beo.errors import BeoError
from beo.models import (
    ActiveSourcesResponse,
    DeviceErrorResponse,
    DeviceInfoResponse,
    FeaturesResponse,
    LineInSettingsProfileResponse,
    PlayQueueResponse,
    ServicesResponse,
    SourcesResponse,
    VolumeLevel,
    VolumeMuted,
)
from beo.notifications import (
    extract_notifications_from_text,
    normalize_notification,
    normalize_volume_output_state,
    normalize_volume_range,
    normalize_volume_state,
)

CONTROL_PORT = 8090
SETUP_PORT = 80
DEFAULT_TIMEOUT_SECONDS = 10.0

TransportCommand = Literal["play", "pause", "stop", "toggle-power"]
TRANSPORT_COMMANDS: dict[TransportCommand, dict[str, str]] = {
    "play": {"feature": "PLAY", "path": "/BeoZone/Zone/Stream/Play"},
    "pause": {"feature": "PAUSE", "path": "/BeoZone/Zone/Stream/Pause"},
    "stop": {"feature": "STOP", "path": "/BeoZone/Zone/Stream/Stop"},
    "toggle-power": {
        "feature": "TOGGLE_POWER",
        "path": "/BeoZone/Zone/Device/TogglePower",
    },
}


@dataclass(frozen=True)
class TextResponse:
    url: str
    status: int
    text: str
    content_type: str | None = None


def _validate_host(host: str) -> str:
    value = host.strip()
    if not value:
        raise BeoError.validation("Host is required.")
    if "://" in value:
        raise BeoError.validation("Host must not include a URL scheme.")
    if "/" in value:
        raise BeoError.validation("Host must not include a path.")
    return value


def _normalize_host(host: str) -> str:
    return (
        f"[{host}]" if ":" in host and not (host.startswith("[") and host.endswith("]")) else host
    )


def _build_url(host: str, port: int, path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"http://{_normalize_host(host)}:{port}{normalized_path}"


def _safe_json_parse(text: str) -> Any:
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _normalize_absolute_url_to_path(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        return parsed.path + (f"?{parsed.query}" if parsed.query else "")
    return value


def _extract_href(value: Any) -> str | None:
    if isinstance(value, str):
        return _normalize_absolute_url_to_path(value)
    if isinstance(value, dict) and isinstance(value.get("href"), str):
        return _normalize_absolute_url_to_path(value["href"])
    return None


def _extract_relation_href(links: dict[str, Any] | None, relation: str) -> str | None:
    return _extract_href(links.get(relation)) if links else None


def _normalize_device_profile_path(path: str) -> str:
    normalized = _normalize_absolute_url_to_path(path)
    if normalized in {".", "./"}:
        raise BeoError.unsupported("Device profile did not include a usable self path.")
    if normalized.startswith("/BeoDevice"):
        return normalized
    if normalized.startswith("/"):
        return f"/BeoDevice{normalized}"
    return f"/BeoDevice/{normalized}"


def _resolve_relative_path(base_path: str, href: str | None) -> str:
    if not href:
        return base_path
    normalized = _normalize_absolute_url_to_path(href)
    if normalized in {".", "./"}:
        return base_path
    if normalized.startswith("/BeoDevice"):
        return normalized
    base = base_path.rstrip("/")
    if normalized.startswith("."):
        return f"{base}{normalized[1:]}"
    if normalized.startswith("/"):
        return f"{base}{normalized}"
    return f"{base}/{normalized}"


def _unwrap_property_record(raw: Any, property_name: str) -> Any:
    if isinstance(raw, dict) and isinstance(raw.get(property_name), dict):
        return raw[property_name]
    return raw


def _parse_offset_link(href: str) -> dict[str, Any]:
    parsed = urlparse(href)
    query = parse_qs(parsed.query)
    result: dict[str, Any] = {"href": href}
    if "offset" in query:
        result["offset"] = int(query["offset"][0])
    if "count" in query:
        result["count"] = int(query["count"][0])
    return result


def _raw_model(model: Any) -> dict[str, Any]:
    return model.model_dump(by_alias=True, exclude_none=True)


def _normalize_source(source_id: str, raw_source: Any) -> dict[str, Any]:
    raw = _raw_model(raw_source) if hasattr(raw_source, "model_dump") else raw_source
    source = raw_source
    output: dict[str, Any] = {
        "id": source.id or source_id,
        "raw": raw,
    }
    for key in (
        "friendlyName",
        "category",
        "profile",
        "borrowed",
        "inUse",
        "signalSensed",
        "linkable",
        "sourceType",
    ):
        value = getattr(source, key)
        if value is not None:
            output[key] = value
    if source.product is not None:
        output["product"] = _raw_model(source.product)
    modify_path = _extract_relation_href(source.links, "/relation/modify")
    if modify_path:
        output["modifyPath"] = modify_path
    return output


def _normalize_experience(raw_experience: dict[str, Any]) -> dict[str, Any]:
    listener_list = raw_experience.get("listenerList")
    listeners = None
    create_path = None
    supported_jids = None
    if isinstance(listener_list, dict):
        if isinstance(listener_list.get("listener"), list):
            listeners = [
                {
                    "jid": listener["jid"],
                    "deletePath": _extract_relation_href(
                        listener.get("_links"), "/relation/delete"
                    ),
                }
                for listener in listener_list["listener"]
                if isinstance(listener, dict) and isinstance(listener.get("jid"), str)
            ]
        create_path = _extract_relation_href(listener_list.get("_links"), "/relation/create")
        capabilities = listener_list.get("_capabilities")
        if isinstance(capabilities, dict):
            values = capabilities.get("value")
            if isinstance(values, dict) and isinstance(values.get("jid"), list):
                supported_jids = [value for value in values["jid"] if isinstance(value, str)]

    source = raw_experience.get("source")
    return {
        "source": _normalize_source_for_experience(source) if isinstance(source, dict) else None,
        "state": raw_experience.get("state")
        if isinstance(raw_experience.get("state"), str)
        else None,
        "listeners": listeners,
        "createPath": create_path,
        "deletePath": _extract_relation_href(raw_experience.get("_links"), "/relation/delete"),
        "supportedJids": supported_jids,
        "raw": raw_experience,
    }


def _normalize_source_for_experience(source: dict[str, Any]) -> dict[str, Any]:
    from beo.models import Source

    parsed = Source.model_validate(source)
    return _normalize_source(parsed.id or "unknown", parsed)


def _normalize_play_queue_item(raw_item: Any) -> dict[str, Any]:
    raw = _raw_model(raw_item)
    content_kind = next(
        (
            key
            for key in (
                "favoriteList",
                "favoriteListStation",
                "station",
                "track",
                "album",
                "playList",
                "playListItem",
                "moodWheelItem",
                "artist",
            )
            if key in raw
        ),
        None,
    )
    output: dict[str, Any] = {
        "id": raw_item.id,
        "raw": raw,
    }
    for key in ("behaviour", "playOrder"):
        value = getattr(raw_item, key)
        if value is not None:
            output[key] = value
    if content_kind:
        output["contentKind"] = content_kind
        if isinstance(raw.get(content_kind), dict):
            output["content"] = raw[content_kind]
    relation_map = {
        "deletePath": "/relation/delete",
        "insertPath": "/relation/insert",
        "movePath": "/relation/move",
        "votePath": "/relation/vote",
        "subitemsPath": "/relation/subitems",
    }
    for key, relation in relation_map.items():
        href = _extract_relation_href(raw_item.links, relation)
        if href:
            output[key] = href
    return output


def _normalize_line_in_settings(
    profile_path: str, response: LineInSettingsProfileResponse
) -> dict[str, Any]:
    raw = _raw_model(response)
    profile = response.profile
    settings = profile.lineInSettings
    capabilities = settings.capabilities
    editable_fields = list(capabilities.editable) if capabilities else []
    allowed = []
    if capabilities and isinstance(capabilities.value.get("sensitivity"), list):
        allowed = [value for value in capabilities.value["sensitivity"] if isinstance(value, str)]
    self_path = _resolve_relative_path(profile_path, _extract_relation_href(profile.links, "self"))
    modify_path = _resolve_relative_path(
        profile_path,
        _extract_relation_href(settings.links, "/relation/modify"),
    )
    return {
        "sensitivity": settings.sensitivity,
        "allowedSensitivities": allowed,
        "editableFields": editable_fields,
        "editable": "sensitivity" in editable_fields,
        "selfPath": self_path,
        "modifyPath": modify_path,
        "raw": raw,
    }


class HttpSession:
    def __init__(
        self,
        *,
        host: str,
        control_port: int,
        setup_port: int,
        timeout_seconds: float,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.host = host
        self.control_port = control_port
        self.setup_port = setup_port
        self.timeout_seconds = timeout_seconds
        self._client = http_client
        self._owns_client = http_client is None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_seconds)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()

    async def text(
        self, port: int, path: str, *, method: str = "GET", body: Any = None
    ) -> TextResponse:
        url = _build_url(self.host, port, path)
        headers = {"accept": "application/json, text/plain;q=0.9, */*;q=0.8"}
        try:
            response = await self.client.request(
                method,
                url,
                headers=headers,
                json=body if body is not None else None,
            )
        except httpx.TimeoutException as exc:
            raise BeoError.network(f"Request timed out for {url}.", url=url) from exc
        except httpx.HTTPError as exc:
            raise BeoError.network(f"Request failed for {url}.", url=url) from exc
        if response.is_error:
            raise BeoError.http(
                f"Device returned HTTP {response.status_code} for {url}.",
                status=response.status_code,
                url=url,
                details={"body": response.text},
            )
        return TextResponse(
            url=str(response.url),
            status=response.status_code,
            content_type=response.headers.get("content-type"),
            text=response.text,
        )

    async def json(
        self, port: int, path: str, model: type[Any], *, method: str = "GET", body: Any = None
    ) -> Any:
        response = await self.text(port, path, method=method, body=body)
        parsed = _safe_json_parse(response.text)
        if not isinstance(parsed, dict):
            raise BeoError.parse(
                f"Expected JSON from {response.url}.",
                url=response.url,
                details={"body": response.text},
            )
        device_error = DeviceErrorResponse.model_validate(parsed) if "error" in parsed else None
        if device_error is not None:
            if device_error.error.type == "NOT_IMPLEMENTED":
                raise BeoError.unsupported(
                    device_error.error.message,
                    status=response.status,
                    url=response.url,
                    details=parsed,
                )
            raise BeoError.http(
                device_error.error.message,
                status=response.status,
                url=response.url,
                details=parsed,
            )
        try:
            return model.model_validate(parsed)
        except ValidationError as exc:
            raise BeoError.validation(
                f"Response from {response.url} did not match the expected schema.",
                url=response.url,
                details=exc.errors(),
            ) from exc

    async def control_json(
        self, path: str, model: type[Any], *, method: str = "GET", body: Any = None
    ) -> Any:
        return await self.json(self.control_port, path, model, method=method, body=body)

    async def control_text(
        self, path: str, *, method: str = "GET", body: Any = None
    ) -> TextResponse:
        return await self.text(self.control_port, path, method=method, body=body)

    async def setup_text(self, path: str) -> TextResponse:
        return await self.text(self.setup_port, path)


class BeoClient:
    def __init__(
        self,
        host: str,
        *,
        control_port: int = CONTROL_PORT,
        setup_port: int = SETUP_PORT,
        timeout_ms: int = int(DEFAULT_TIMEOUT_SECONDS * 1000),
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.host = _validate_host(host)
        self._session = HttpSession(
            host=self.host,
            control_port=control_port,
            setup_port=setup_port,
            timeout_seconds=timeout_ms / 1000,
            http_client=http_client,
        )
        self._cached_services: dict[str, str] | None = None
        self.device = _DeviceNamespace(self)
        self.zone = _ZoneNamespace(self)
        self.volume = _VolumeNamespace(self)
        self.queue = _QueueNamespace(self)
        self.notify = _NotifyNamespace(self)
        self.content = _ContentNamespace(self)
        self.setup = _SetupNamespace(self)

    async def __aenter__(self) -> BeoClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._session.aclose()

    async def services(self) -> dict[str, str]:
        response: ServicesResponse = await self._session.control_json("/", ServicesResponse)
        self._cached_services = {service.name: service.path for service in response.services}
        return self._cached_services

    async def ping(self) -> dict[str, Any]:
        response = await self._session.control_text("/Ping")
        parsed = _safe_json_parse(response.text)
        output: dict[str, Any] = {"ok": True, "status": response.status}
        body = parsed if parsed is not None else response.text.strip()
        if body:
            output["body"] = body
        return output

    async def _features(self) -> dict[str, Any]:
        response: FeaturesResponse = await self._session.control_json(
            "/BeoZone/Zone/?list=recursive+features", FeaturesResponse
        )
        return {"features": list(response.features), "raw": _raw_model(response)}

    async def _notification_paths(self) -> list[str]:
        services = self._cached_services
        if services is None:
            try:
                services = await self.services()
            except BeoError:
                services = None
        candidates: list[str] = []
        if services:
            for service in (services.get("BeoNotify"), services.get("BeoZone")):
                if isinstance(service, str):
                    service = service.rstrip("/")
                    candidates.append(
                        service
                        if service.endswith("/Notifications")
                        else f"{service}/Notifications"
                    )
        return candidates or ["/BeoNotify/Notifications", "/BeoZone/Notifications"]


class _DeviceNamespace:
    def __init__(self, client: BeoClient) -> None:
        self._client = client
        self.line_in = _LineInNamespace(client, self)

    async def get_info(self) -> dict[str, Any]:
        response: DeviceInfoResponse = await self._client._session.control_json(
            "/BeoDevice/", DeviceInfoResponse
        )
        device = response.beoDevice
        output: dict[str, Any] = {
            "typeNumber": str(device.productId.typeNumber),
            "itemNumber": str(device.productId.itemNumber),
            "serialNumber": str(device.productId.serialNumber),
            "softwareVersion": device.software.version,
            "profiles": [
                {
                    "name": profile.name,
                    "version": profile.version,
                    "selfPath": _extract_relation_href(profile.links, "self"),
                    "raw": _raw_model(profile),
                }
                for profile in device.profiles
            ],
            "raw": _raw_model(response),
        }
        optional = {
            "productType": None
            if device.productId.productType is None
            else str(device.productId.productType),
            "productFamily": device.productFamily,
            "productFriendlyName": device.productFriendlyName.productFriendlyName
            if device.productFriendlyName
            else None,
            "proxyMasterLinkType": device.proxyMasterLinkType,
            "softwareUpdateProductTypeId": device.software.softwareUpdateProductTypeId,
            "anonymousProductId": device.anonymousProductId,
        }
        output.update({key: value for key, value in optional.items() if value is not None})
        return output

    async def get_line_in_settings(self) -> dict[str, Any]:
        return await self.line_in.get()

    async def set_line_in_sensitivity(self, value: str) -> dict[str, Any]:
        return await self.line_in.set_sensitivity(value)

    getInfo = get_info
    getLineInSettings = get_line_in_settings
    setLineInSensitivity = set_line_in_sensitivity


class _LineInNamespace:
    def __init__(self, client: BeoClient, device: _DeviceNamespace) -> None:
        self._client = client
        self._device = device

    async def _profile_path(self) -> str:
        info = await self._device.get_info()
        profile = next(
            (
                profile
                for profile in info.get("profiles", [])
                if profile.get("name") == "lineInSettingsProfile"
            ),
            None,
        )
        if not isinstance(profile, dict) or not isinstance(profile.get("selfPath"), str):
            raise BeoError.unsupported("Device does not expose a line-in settings profile.")
        return _normalize_device_profile_path(profile["selfPath"])

    async def _fetch_profile(self) -> tuple[str, dict[str, Any]]:
        path = await self._profile_path()
        response: LineInSettingsProfileResponse = await self._client._session.control_json(
            path, LineInSettingsProfileResponse
        )
        return path, _normalize_line_in_settings(path, response)

    async def get(self) -> dict[str, Any]:
        _path, settings = await self._fetch_profile()
        return settings

    async def set_sensitivity(self, value: str) -> dict[str, Any]:
        path, settings = await self._fetch_profile()
        if not settings["editable"]:
            raise BeoError.unsupported(
                "Line-in sensitivity is not editable.",
                details={"editableFields": settings["editableFields"]},
            )
        if value not in settings["allowedSensitivities"]:
            raise BeoError.validation(
                "Line-in sensitivity must be one of the device-supported values.",
                details={
                    "requested": value,
                    "allowedSensitivities": settings["allowedSensitivities"],
                },
            )
        await self._client._session.control_text(
            settings["modifyPath"],
            method="PUT",
            body={"lineInSettings": {"sensitivity": value}},
        )
        response: LineInSettingsProfileResponse = await self._client._session.control_json(
            path, LineInSettingsProfileResponse
        )
        return _normalize_line_in_settings(path, response)

    setSensitivity = set_sensitivity


class _ZoneNamespace:
    def __init__(self, client: BeoClient) -> None:
        self._client = client

    async def get_sources(self) -> list[dict[str, Any]]:
        response: SourcesResponse = await self._client._session.control_json(
            "/BeoZone/Zone/Sources", SourcesResponse
        )
        return [_normalize_source(source_id, source) for source_id, source in response.sources]

    async def get_active_sources(self) -> dict[str, Any]:
        response: ActiveSourcesResponse = await self._client._session.control_json(
            "/BeoZone/Zone/ActiveSources", ActiveSourcesResponse
        )
        return {
            "primary": response.activeSources.primary if response.activeSources else None,
            "secondary": response.activeSources.secondary if response.activeSources else None,
            "primaryExperience": _normalize_experience(response.primaryExperience)
            if response.primaryExperience
            else None,
            "secondaryExperience": _normalize_experience(response.secondaryExperience)
            if response.secondaryExperience
            else None,
            "raw": _raw_model(response),
        }

    async def get_features(self) -> dict[str, Any]:
        return await self._client._features()

    async def set_active_source(
        self,
        source_id: str,
        source_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        source_meta = source_meta or {}
        source: dict[str, Any] = {"id": source_id}
        if source_meta.get("friendlyName"):
            source["friendlyName"] = source_meta["friendlyName"]
        if source_meta.get("productJabberId") and source_meta.get("productFriendlyName"):
            source["product"] = {
                "jid": source_meta["productJabberId"],
                "friendlyName": source_meta["productFriendlyName"],
            }
        await self._client._session.control_text(
            "/BeoZone/Zone/ActiveSources",
            method="POST",
            body={
                "activeSources": {"primary": source_id},
                "primaryExperience": {"source": source},
            },
        )
        return {
            "ok": True,
            "sourceId": source_id,
            "usedMetadata": bool(source_meta),
        }

    async def command(self, command_type: TransportCommand) -> dict[str, Any]:
        command = TRANSPORT_COMMANDS[command_type]
        features = await self._client._features()
        if command["feature"] not in features["features"]:
            raise BeoError.unsupported(
                f'Transport command "{command_type}" is not supported by '
                "the current zone features.",
                details={
                    "requiredFeature": command["feature"],
                    "availableFeatures": features["features"],
                },
            )
        await self._client._session.control_text(command["path"], method="POST", body={})
        return {"ok": True, "command": command_type}

    getSources = get_sources
    getActiveSources = get_active_sources
    getFeatures = get_features
    setActiveSource = set_active_source


class _VolumeNamespace:
    def __init__(self, client: BeoClient) -> None:
        self._client = client

    async def get(self) -> dict[str, Any]:
        response = await self._client._session.control_json(
            "/BeoZone/Zone/Sound/Volume/", _LooseDict
        )
        return normalize_volume_state(_unwrap_property_record(_raw_model(response), "volume"))

    async def get_speaker(self) -> dict[str, Any]:
        return await self._get_output("/BeoZone/Zone/Sound/Volume/Speaker/", "speaker")

    async def get_headphone(self) -> dict[str, Any]:
        return await self._get_output("/BeoZone/Zone/Sound/Volume/Headphone/", "headphone")

    async def _get_output(self, path: str, property_name: str) -> dict[str, Any]:
        response = await self._client._session.control_json(path, _LooseDict)
        return normalize_volume_output_state(
            _unwrap_property_record(_raw_model(response), property_name)
        )

    async def _get_level(self, path: str) -> int:
        response: VolumeLevel = await self._client._session.control_json(path, VolumeLevel)
        return response.level

    async def _set_level(self, path: str, level: int) -> dict[str, Any]:
        payload = _validate_volume_level(level)
        await self._client._session.control_text(path, method="PUT", body=payload)
        return {"ok": True, "level": payload["level"]}

    async def _get_muted(self, path: str) -> bool:
        response: VolumeMuted = await self._client._session.control_json(path, VolumeMuted)
        return response.muted

    async def _set_muted(self, path: str, muted: bool) -> dict[str, Any]:
        await self._client._session.control_text(path, method="PUT", body={"muted": muted})
        return {"ok": True, "muted": muted}

    async def _get_range(self, path: str) -> dict[str, Any]:
        response = await self._client._session.control_json(path, _LooseDict)
        return normalize_volume_range(_unwrap_property_record(_raw_model(response), "range"))

    async def get_speaker_level(self) -> int:
        return await self._get_level("/BeoZone/Zone/Sound/Volume/Speaker/Level/")

    async def set_speaker_level(self, level: int) -> dict[str, Any]:
        return await self._set_level("/BeoZone/Zone/Sound/Volume/Speaker/Level/", level)

    async def get_speaker_muted(self) -> bool:
        return await self._get_muted("/BeoZone/Zone/Sound/Volume/Speaker/Muted/")

    async def set_speaker_muted(self, muted: bool) -> dict[str, Any]:
        return await self._set_muted("/BeoZone/Zone/Sound/Volume/Speaker/Muted/", muted)

    async def get_speaker_range(self) -> dict[str, Any]:
        return await self._get_range("/BeoZone/Zone/Sound/Volume/Speaker/Range/")

    async def get_headphone_level(self) -> int:
        return await self._get_level("/BeoZone/Zone/Sound/Volume/Headphone/Level/")

    async def set_headphone_level(self, level: int) -> dict[str, Any]:
        return await self._set_level("/BeoZone/Zone/Sound/Volume/Headphone/Level/", level)

    async def get_headphone_muted(self) -> bool:
        return await self._get_muted("/BeoZone/Zone/Sound/Volume/Headphone/Muted/")

    async def set_headphone_muted(self, muted: bool) -> dict[str, Any]:
        return await self._set_muted("/BeoZone/Zone/Sound/Volume/Headphone/Muted/", muted)

    async def get_headphone_range(self) -> dict[str, Any]:
        return await self._get_range("/BeoZone/Zone/Sound/Volume/Headphone/Range/")

    getSpeaker = get_speaker
    getSpeakerLevel = get_speaker_level
    setSpeakerLevel = set_speaker_level
    getSpeakerMuted = get_speaker_muted
    setSpeakerMuted = set_speaker_muted
    getSpeakerRange = get_speaker_range
    getHeadphone = get_headphone
    getHeadphoneLevel = get_headphone_level
    setHeadphoneLevel = set_headphone_level
    getHeadphoneMuted = get_headphone_muted
    setHeadphoneMuted = set_headphone_muted
    getHeadphoneRange = get_headphone_range


class _QueueNamespace:
    def __init__(self, client: BeoClient) -> None:
        self._client = client

    async def get(self) -> dict[str, Any]:
        response: PlayQueueResponse = await self._client._session.control_json(
            "/BeoZone/Zone/PlayQueue", PlayQueueResponse
        )
        queue = response.playQueue
        output: dict[str, Any] = {
            "id": queue.id,
            "offset": queue.offset,
            "count": queue.count,
            "startOffset": queue.startOffset,
            "total": queue.total,
            "revision": queue.revision,
            "items": [_normalize_play_queue_item(item) for item in queue.item],
            "raw": _raw_model(response),
        }
        if queue.playNowId is not None:
            output["playNowId"] = queue.playNowId
        next_href = _extract_relation_href(queue.links, "next")
        previous_href = _extract_relation_href(queue.links, "prev")
        if next_href:
            output["next"] = _parse_offset_link(next_href)
        if previous_href:
            output["previous"] = _parse_offset_link(previous_href)
        return output

    async def seek(self, input: dict[str, Any]) -> dict[str, Any]:
        play_queue_item_id = input.get("playQueueItemId")
        position_seconds = input.get("positionSeconds")
        if not isinstance(play_queue_item_id, str) or not play_queue_item_id:
            raise BeoError.validation("playQueueItemId is required.")
        if not isinstance(position_seconds, int) or position_seconds < 0:
            raise BeoError.validation("positionSeconds must be a non-negative integer.")
        await self._client._session.control_text(
            "/BeoZone/Zone/PlayQueue/PlayPointer",
            method="POST",
            body={
                "playPointer": {
                    "playQueueItemId": play_queue_item_id,
                    "position": position_seconds,
                }
            },
        )
        return {
            "ok": True,
            "playQueueItemId": play_queue_item_id,
            "positionSeconds": position_seconds,
        }


class _NotifyNamespace:
    def __init__(self, client: BeoClient) -> None:
        self._client = client

    async def stream(self, last_id: str | int | None = None) -> AsyncIterator[dict[str, Any]]:
        current_last_id = None if last_id is None else str(last_id)
        paths = await self._client._notification_paths()
        active_path_index = 0
        while True:
            path = paths[min(active_path_index, len(paths) - 1)]
            request_path = (
                path
                if current_last_id is None
                else f"{path}{'&' if '?' in path else '?'}lastId={quote(current_last_id)}"
            )
            try:
                response = await self._client._session.control_text(request_path)
            except BeoError as exc:
                if exc.status == 404 and active_path_index + 1 < len(paths):
                    active_path_index += 1
                    continue
                raise
            for raw_notification in extract_notifications_from_text(response.text):
                notification = normalize_notification(raw_notification)
                if isinstance(notification.get("id"), int):
                    current_last_id = str(notification["id"])
                yield notification


class _ContentNamespace:
    def __init__(self, client: BeoClient) -> None:
        self._client = client

    async def get_netradio_profile(self) -> dict[str, Any]:
        response = await self._client._session.control_json(
            "/BeoContent/netradio/netRadioProfile/", _LooseDict
        )
        raw = _raw_model(response)
        profile_candidate = raw.get("profile")
        profile: dict[str, Any] = profile_candidate if isinstance(profile_candidate, dict) else raw
        links = profile.get("_links") if isinstance(profile.get("_links"), dict) else None
        output = {
            "name": profile.get("name") if isinstance(profile.get("name"), str) else None,
            "version": profile.get("version") if isinstance(profile.get("version"), int) else None,
            "rank": profile.get("rank") if isinstance(profile.get("rank"), int) else None,
            "revision": profile.get("revision")
            if isinstance(profile.get("revision"), int)
            else None,
            "selfPath": _extract_relation_href(links, "self"),
            "favoriteListsPath": _extract_relation_href(links, "/relation/favoritelist"),
            "raw": raw,
        }
        return {key: value for key, value in output.items() if value is not None}

    getNetRadioProfile = get_netradio_profile


class _SetupNamespace:
    def __init__(self, client: BeoClient) -> None:
        self._client = client

    async def get_version(self) -> dict[str, Any]:
        response = await self._client._session.setup_text("/version")
        parsed = _safe_json_parse(response.text)
        if isinstance(parsed, dict) and isinstance(parsed.get("version"), str):
            return {"version": parsed["version"], "raw": parsed}
        return {"version": response.text.strip(), "raw": response.text}

    async def get_index(self) -> dict[str, Any]:
        response = await self._client._session.setup_text("/")
        output: dict[str, Any] = {"status": response.status, "bodySnippet": response.text[:400]}
        if response.content_type is not None:
            output["contentType"] = response.content_type
        return output

    getVersion = get_version
    getIndex = get_index


class _LooseDict(RootModel[dict[str, Any]]):
    pass


def _validate_volume_level(level: int) -> dict[str, int]:
    try:
        parsed = VolumeLevel.model_validate({"level": level})
    except ValidationError as exc:
        raise BeoError.validation(
            "Level must be a non-negative integer.", details=exc.errors()
        ) from exc
    return {"level": parsed.level}


def create_beo_client(
    host: str,
    *,
    control_port: int = CONTROL_PORT,
    setup_port: int = SETUP_PORT,
    timeout_ms: int = int(DEFAULT_TIMEOUT_SECONDS * 1000),
    http_client: httpx.AsyncClient | None = None,
) -> BeoClient:
    return BeoClient(
        host,
        control_port=control_port,
        setup_port=setup_port,
        timeout_ms=timeout_ms,
        http_client=http_client,
    )
