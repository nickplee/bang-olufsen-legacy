from __future__ import annotations

import json
from contextlib import suppress
from typing import Any

from pydantic import ValidationError

from custom_components.bang_olufsen_legacy.api.errors import BeoError
from custom_components.bang_olufsen_legacy.api.models import (
    NotificationEnvelope,
    VolumeOutputState,
    VolumeRange,
    VolumeState,
)


def normalize_volume_range(raw: Any) -> dict[str, int]:
    parsed = VolumeRange.model_validate(raw)
    return {"minimum": parsed.minimum, "maximum": parsed.maximum}


def normalize_volume_output_state(raw: Any) -> dict[str, Any]:
    parsed = VolumeOutputState.model_validate(raw)
    output: dict[str, Any] = {"level": parsed.level, "muted": parsed.muted}
    if parsed.range is not None:
        output["range"] = normalize_volume_range(parsed.range)
    return output


def normalize_volume_state(raw: Any) -> dict[str, Any]:
    parsed = VolumeState.model_validate(raw)
    output: dict[str, Any] = {"speaker": normalize_volume_output_state(parsed.speaker)}
    if parsed.headphone is not None:
        output["headphone"] = normalize_volume_output_state(parsed.headphone)
    return output


def _extract_link_href(value: Any) -> str | None:
    if isinstance(value, dict) and isinstance(value.get("href"), str):
        return value["href"]
    return None


def _normalize_notification_experience(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    listener_list = value.get("listenerList")
    listeners = None
    create_path = None
    if isinstance(listener_list, dict):
        raw_listeners = listener_list.get("listener")
        if isinstance(raw_listeners, list):
            listeners = [
                {
                    "jid": listener["jid"],
                    "deletePath": _extract_link_href(
                        listener.get("_links", {}).get("/relation/delete")
                    ),
                }
                for listener in raw_listeners
                if isinstance(listener, dict) and isinstance(listener.get("jid"), str)
            ]
        create_path = _extract_link_href(listener_list.get("_links", {}).get("/relation/create"))
    return {
        "source": value.get("source"),
        "state": value.get("state"),
        "listeners": listeners,
        "createPath": create_path,
        "deletePath": _extract_link_href(value.get("_links", {}).get("/relation/delete")),
        "raw": value,
    }


def split_json_payloads(text: str) -> list[str]:
    payloads: list[str] = []
    depth = 0
    in_string = False
    escape = False
    start = -1

    for index, char in enumerate(text):
        if start == -1:
            if char in "{[":
                start = index
                depth = 1
            continue
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
            if depth == 0:
                payloads.append(text[start : index + 1])
                start = -1

    trailing = "" if start == -1 else text[start:].strip()
    if trailing:
        raise BeoError.parse(
            "Notification response ended with an incomplete JSON payload.",
            details={"trailing": trailing},
        )
    return payloads


def extract_notifications_from_text(text: str) -> list[dict[str, Any]]:
    notifications: list[dict[str, Any]] = []
    for payload in split_json_payloads(text):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise BeoError.parse(
                "Failed to parse notification JSON payload.",
                details={"payload": payload},
            ) from exc
        if isinstance(parsed, list):
            notifications.extend(item for item in parsed if isinstance(item, dict))
        elif isinstance(parsed, dict):
            notifications.append(parsed)
    return notifications


def normalize_notification(raw: dict[str, Any]) -> dict[str, Any]:
    try:
        envelope = NotificationEnvelope.model_validate(raw)
    except ValidationError as exc:
        raise BeoError.validation(
            "Notification payload did not match the expected envelope.",
            details=exc.errors(),
        ) from exc
    notification: dict[str, Any] = {
        "id": envelope.id,
        "timestamp": envelope.timestamp,
        "type": envelope.type,
        "data": envelope.data,
        "raw": envelope.model_dump(by_alias=True, exclude_none=True),
    }
    if envelope.id is None:
        notification.pop("id")
    if envelope.timestamp is None:
        notification.pop("timestamp")
    if envelope.type == "VOLUME":
        with suppress(ValidationError):
            notification["volume"] = normalize_volume_state(envelope.data)
    if envelope.type == "SOURCE" and isinstance(envelope.data, dict):
        notification["source"] = {
            "primary": envelope.data.get("primary"),
            "secondary": envelope.data.get("secondary"),
            "primaryExperience": _normalize_notification_experience(
                envelope.data.get("primaryExperience")
            ),
            "secondaryExperience": _normalize_notification_experience(
                envelope.data.get("secondaryExperience")
            ),
        }
    if envelope.type == "PROGRESS_INFORMATION" and isinstance(envelope.data, dict):
        notification["progress"] = envelope.data
    return notification
