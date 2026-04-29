from __future__ import annotations

from typing import Any

from typer.testing import CliRunner

from cli.main import app, set_client_factory
from custom_components.bang_olufsen_legacy.api.errors import BeoError

runner = CliRunner()


class StubClient:
    async def __aenter__(self) -> StubClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def services(self) -> dict[str, str]:
        return {"BeoZone": "/BeoZone"}

    async def ping(self) -> dict[str, Any]:
        return {"ok": True, "status": 200, "body": {"pong": True}}

    class device:
        class line_in:
            @staticmethod
            async def get() -> dict[str, Any]:
                return {
                    "sensitivity": "high",
                    "allowedSensitivities": ["high", "medium", "low"],
                    "editableFields": ["sensitivity"],
                    "editable": True,
                    "selfPath": "/BeoDevice/lineInSettingsProfile/",
                    "modifyPath": "/BeoDevice/lineInSettingsProfile/",
                    "raw": {},
                }

            @staticmethod
            async def set_sensitivity(value: str) -> dict[str, Any]:
                if value == "maximum":
                    raise BeoError.validation(
                        "Line-in sensitivity must be one of the device-supported values.",
                        details={"allowedSensitivities": ["high", "medium", "low"]},
                    )
                return {
                    "sensitivity": value,
                    "allowedSensitivities": ["high", "medium", "low"],
                    "editableFields": ["sensitivity"],
                    "editable": True,
                    "selfPath": "/BeoDevice/lineInSettingsProfile/",
                    "modifyPath": "/BeoDevice/lineInSettingsProfile/",
                    "raw": {},
                }

        @staticmethod
        async def get_info() -> dict[str, Any]:
            return {
                "typeNumber": "1234",
                "itemNumber": "5678",
                "serialNumber": "serial",
                "softwareVersion": "1.0.0",
                "profiles": [],
                "raw": {},
            }

    class zone:
        @staticmethod
        async def get_sources() -> list[dict[str, Any]]:
            return [{"id": "line-in", "friendlyName": "Line-In", "raw": {}}]

        @staticmethod
        async def get_active_sources() -> dict[str, Any]:
            return {"primary": "line-in", "raw": {}}

        @staticmethod
        async def get_features() -> dict[str, Any]:
            return {"features": ["PLAY", "PLAYQUEUE", "TOGGLE_POWER"], "raw": {}}

        @staticmethod
        async def set_active_source(source_id: str, _meta: Any = None) -> dict[str, Any]:
            return {"ok": True, "sourceId": source_id, "usedMetadata": True}

        @staticmethod
        async def command(command_type: str) -> dict[str, Any]:
            if command_type == "pause":
                raise BeoError.unsupported(f'Transport command "{command_type}" is not supported.')
            return {"ok": True, "command": command_type}

    class volume:
        @staticmethod
        async def get() -> dict[str, Any]:
            return {
                "speaker": {"level": 34, "muted": False, "range": {"minimum": 0, "maximum": 90}},
                "headphone": {"level": 18, "muted": True, "range": {"minimum": 0, "maximum": 32}},
            }

        @staticmethod
        async def get_speaker() -> dict[str, Any]:
            return {"level": 34, "muted": False, "range": {"minimum": 0, "maximum": 90}}

        @staticmethod
        async def set_speaker_level(level: int) -> dict[str, Any]:
            if level == 13:
                raise BeoError.http("Speaker level rejected.", status=400, url="http://example")
            return {"ok": True, "level": level}

        @staticmethod
        async def set_speaker_muted(muted: bool) -> dict[str, Any]:
            return {"ok": True, "muted": muted}

        @staticmethod
        async def get_headphone() -> dict[str, Any]:
            return {"level": 18, "muted": True, "range": {"minimum": 0, "maximum": 32}}

        @staticmethod
        async def set_headphone_level(level: int) -> dict[str, Any]:
            return {"ok": True, "level": level}

        @staticmethod
        async def set_headphone_muted(muted: bool) -> dict[str, Any]:
            return {"ok": True, "muted": muted}

    class queue:
        @staticmethod
        async def get() -> dict[str, Any]:
            return {
                "id": "main",
                "offset": 0,
                "count": 1,
                "startOffset": 0,
                "total": 1,
                "revision": 1,
                "items": [],
                "raw": {},
            }

        @staticmethod
        async def seek(input: dict[str, Any]) -> dict[str, Any]:
            return {
                "ok": True,
                "playQueueItemId": input["playQueueItemId"],
                "positionSeconds": input["positionSeconds"],
            }

    class notify:
        @staticmethod
        async def stream(last_id: str | None = None):
            yield {
                "id": 1,
                "timestamp": "2026-04-28T18:00:00Z",
                "type": "VOLUME",
                "data": {},
                "raw": {},
            }

    class content:
        @staticmethod
        async def get_netradio_profile() -> dict[str, Any]:
            return {"name": "netRadioProfile", "version": 1, "raw": {}}

    class setup:
        @staticmethod
        async def get_version() -> dict[str, Any]:
            return {"version": "1.2.3", "raw": "1.2.3"}

        @staticmethod
        async def get_index() -> dict[str, Any]:
            return {"status": 200, "contentType": "text/html", "bodySnippet": "<html>"}


def invoke(args: list[str]):
    set_client_factory(lambda **_kwargs: StubClient())
    return runner.invoke(app, args)


def test_compact_and_pretty_json() -> None:
    compact = invoke(["services", "--host", "192.168.1.2"])
    assert compact.exit_code == 0
    assert compact.stdout.strip() == '{"BeoZone":"/BeoZone"}'

    pretty = invoke(["device", "info", "--host", "192.168.1.2", "--pretty"])
    assert pretty.exit_code == 0
    assert '\n  "typeNumber": "1234"' in pretty.stdout


def test_device_line_in_commands() -> None:
    read = invoke(["device", "line-in", "show", "--host", "192.168.1.2"])
    assert read.exit_code == 0
    assert read.stdout.strip() == (
        '{"sensitivity":"high","allowedSensitivities":["high","medium","low"],'
        '"editableFields":["sensitivity"],"editable":true,'
        '"selfPath":"/BeoDevice/lineInSettingsProfile/",'
        '"modifyPath":"/BeoDevice/lineInSettingsProfile/","raw":{}}'
    )

    pretty = invoke(["device", "line-in", "show", "--host", "192.168.1.2", "--pretty"])
    assert pretty.exit_code == 0
    assert '\n  "sensitivity": "high"' in pretty.stdout

    set_result = invoke(
        [
            "device",
            "line-in",
            "set-sensitivity",
            "--host",
            "192.168.1.2",
            "--value",
            "medium",
        ]
    )
    assert set_result.exit_code == 0
    assert '"sensitivity":"medium"' in set_result.stdout

    bad = invoke(
        [
            "device",
            "line-in",
            "set-sensitivity",
            "--host",
            "192.168.1.2",
            "--value",
            "maximum",
        ]
    )
    assert bad.exit_code == 1
    assert '"code":"VALIDATION_ERROR"' in bad.stderr


def test_volume_and_protocol_errors() -> None:
    volume = invoke(["volume", "show", "--host", "192.168.1.2"])
    assert volume.exit_code == 0
    assert volume.stdout.strip() == (
        '{"speaker":{"level":34,"muted":false,"range":{"minimum":0,"maximum":90}},'
        '"headphone":{"level":18,"muted":true,"range":{"minimum":0,"maximum":32}}}'
    )

    error = invoke(["transport", "pause", "--host", "192.168.1.2"])
    assert error.exit_code == 1
    assert '"code":"UNSUPPORTED_OPERATION"' in error.stderr

    http_error = invoke(["volume", "set-speaker", "--host", "192.168.1.2", "--level", "13"])
    assert http_error.exit_code == 1
    assert '"status":400' in http_error.stderr


def test_validation_and_headphone_commands() -> None:
    bad_position = invoke(
        [
            "queue",
            "seek",
            "--host",
            "192.168.1.2",
            "--item-id",
            "item-1",
            "--position",
            "-1",
        ]
    )
    assert bad_position.exit_code == 2
    assert "Invalid value" in bad_position.stderr

    read = invoke(["volume", "headphone", "--host", "192.168.1.2"])
    mute = invoke(["volume", "mute-headphone", "--host", "192.168.1.2", "--muted", "false"])
    set_level = invoke(["volume", "set-headphone", "--host", "192.168.1.2", "--level", "12"])
    assert read.stdout.strip() == '{"level":18,"muted":true,"range":{"minimum":0,"maximum":32}}'
    assert mute.stdout.strip() == '{"ok":true,"muted":false}'
    assert set_level.stdout.strip() == '{"ok":true,"level":12}'


def test_notify_stream_json_lines_and_help() -> None:
    stream = invoke(["notify", "stream", "--host", "192.168.1.2"])
    assert stream.exit_code == 0
    assert stream.stdout.strip() == (
        '{"id":1,"timestamp":"2026-04-28T18:00:00Z","type":"VOLUME","data":{},"raw":{}}'
    )

    help_result = invoke(["--help"])
    assert help_result.exit_code == 0
    assert "BeoSound Essence Mk1 control CLI" in help_result.stdout
