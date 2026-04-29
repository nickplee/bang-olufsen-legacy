from __future__ import annotations

import json
from pathlib import Path

import pytest

from beo import BeoError, create_beo_client
from beo.notifications import extract_notifications_from_text, normalize_notification

FIXTURES = Path(__file__).parent / "fixtures"
HOST = "192.168.1.2"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


@pytest.mark.asyncio
async def test_loads_service_map(httpx_mock) -> None:
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/",
        json=json.loads(fixture("services.json")),
    )
    async with create_beo_client(HOST) as client:
        assert await client.services() == {
            "Ping": "/Ping",
            "BeoZone": "/BeoZone",
            "BeoDevice": "/BeoDevice",
            "BeoContent": "/BeoContent",
            "BeoNotify": "/BeoNotify",
        }


@pytest.mark.asyncio
async def test_normalizes_device_info(httpx_mock) -> None:
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/BeoDevice/",
        json=json.loads(fixture("device-info.json")),
    )
    async with create_beo_client(HOST) as client:
        info = await client.device.get_info()
    assert info["serialNumber"] == "2990.0000000.12345678@products.bang-olufsen.com"
    assert info["productFriendlyName"] == "BeoSound Essence"
    assert len(info["profiles"]) == 2


@pytest.mark.asyncio
async def test_reads_line_in_settings_profile(httpx_mock) -> None:
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/BeoDevice/",
        json=json.loads(fixture("device-info.json")),
    )
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/BeoDevice/lineInSettingsProfile/",
        json=json.loads(fixture("line-in-settings-profile.json")),
    )
    async with create_beo_client(HOST) as client:
        settings = await client.device.line_in.get()
    assert settings["sensitivity"] == "high"
    assert settings["allowedSensitivities"] == ["high", "medium", "low"]
    assert settings["editableFields"] == ["sensitivity"]
    assert settings["editable"] is True
    assert settings["selfPath"] == "/BeoDevice/lineInSettingsProfile/"
    assert settings["modifyPath"] == "/BeoDevice/lineInSettingsProfile/"


@pytest.mark.asyncio
async def test_sets_line_in_sensitivity_and_returns_updated_profile(httpx_mock) -> None:
    updated = json.loads(fixture("line-in-settings-profile.json"))
    updated["profile"]["lineInSettings"]["sensitivity"] = "medium"
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/BeoDevice/",
        json=json.loads(fixture("device-info.json")),
    )
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/BeoDevice/lineInSettingsProfile/",
        json=json.loads(fixture("line-in-settings-profile.json")),
    )
    httpx_mock.add_response(
        method="PUT",
        url=f"http://{HOST}:8090/BeoDevice/lineInSettingsProfile/",
        json={},
    )
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/BeoDevice/lineInSettingsProfile/",
        json=updated,
    )
    async with create_beo_client(HOST) as client:
        settings = await client.device.line_in.set_sensitivity("medium")
    assert settings["sensitivity"] == "medium"
    assert json.loads(httpx_mock.get_requests()[2].content) == {
        "lineInSettings": {"sensitivity": "medium"}
    }


@pytest.mark.asyncio
async def test_rejects_unsupported_line_in_sensitivity(httpx_mock) -> None:
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/BeoDevice/",
        json=json.loads(fixture("device-info.json")),
    )
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/BeoDevice/lineInSettingsProfile/",
        json=json.loads(fixture("line-in-settings-profile.json")),
    )
    async with create_beo_client(HOST) as client:
        with pytest.raises(BeoError) as error:
            await client.device.line_in.set_sensitivity("maximum")
    assert error.value.code == "VALIDATION_ERROR"
    assert error.value.details["allowedSensitivities"] == ["high", "medium", "low"]


@pytest.mark.asyncio
async def test_rejects_uneditable_line_in_sensitivity(httpx_mock) -> None:
    profile = json.loads(fixture("line-in-settings-profile.json"))
    profile["profile"]["lineInSettings"]["_capabilities"]["editable"] = []
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/BeoDevice/",
        json=json.loads(fixture("device-info.json")),
    )
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/BeoDevice/lineInSettingsProfile/",
        json=profile,
    )
    async with create_beo_client(HOST) as client:
        with pytest.raises(BeoError) as error:
            await client.device.line_in.set_sensitivity("medium")
    assert error.value.code == "UNSUPPORTED_OPERATION"


@pytest.mark.asyncio
async def test_line_in_settings_missing_profile_is_unsupported(httpx_mock) -> None:
    response = json.loads(fixture("device-info.json"))
    response["beoDevice"]["profiles"] = []
    httpx_mock.add_response(url=f"http://{HOST}:8090/BeoDevice/", json=response)
    async with create_beo_client(HOST) as client:
        with pytest.raises(BeoError) as error:
            await client.device.line_in.get()
    assert error.value.code == "UNSUPPORTED_OPERATION"


@pytest.mark.asyncio
async def test_normalizes_sources(httpx_mock) -> None:
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/BeoZone/Zone/Sources",
        json=json.loads(fixture("sources.json")),
    )
    async with create_beo_client(HOST) as client:
        sources = await client.zone.get_sources()
    assert sources[0]["id"] == "line-in:2990.0000000.12345678@products.bang-olufsen.com"
    assert sources[0]["product"]["jid"] == "2990.0000000.12345678@products.bang-olufsen.com"
    assert sources[1]["id"] == "netRadio"


@pytest.mark.asyncio
async def test_normalizes_active_sources(httpx_mock) -> None:
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/BeoZone/Zone/ActiveSources",
        json=json.loads(fixture("active-sources.json")),
    )
    async with create_beo_client(HOST) as client:
        active = await client.zone.get_active_sources()
    assert active["primary"] == "line-in:2990.0000000.12345678@products.bang-olufsen.com"
    assert active["primaryExperience"]["listeners"][0]["jid"] == (
        "3000.0000000.87654321@products.bang-olufsen.com"
    )


@pytest.mark.asyncio
async def test_active_source_payload_shape(httpx_mock) -> None:
    httpx_mock.add_response(url=f"http://{HOST}:8090/BeoZone/Zone/ActiveSources", json={})
    async with create_beo_client(HOST) as client:
        result = await client.zone.set_active_source(
            "line-in:2990.0000000.12345678@products.bang-olufsen.com",
            {
                "friendlyName": "Line-In",
                "productJabberId": "2990.0000000.12345678@products.bang-olufsen.com",
                "productFriendlyName": "BeoSound Essence",
            },
        )
    request = httpx_mock.get_request()
    assert request is not None
    assert json.loads(request.content) == {
        "activeSources": {"primary": "line-in:2990.0000000.12345678@products.bang-olufsen.com"},
        "primaryExperience": {
            "source": {
                "id": "line-in:2990.0000000.12345678@products.bang-olufsen.com",
                "friendlyName": "Line-In",
                "product": {
                    "jid": "2990.0000000.12345678@products.bang-olufsen.com",
                    "friendlyName": "BeoSound Essence",
                },
            }
        },
    }
    assert result == {
        "ok": True,
        "sourceId": "line-in:2990.0000000.12345678@products.bang-olufsen.com",
        "usedMetadata": True,
    }


@pytest.mark.asyncio
async def test_volume_endpoints_and_mutations(httpx_mock) -> None:
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/BeoZone/Zone/Sound/Volume/",
        json=json.loads(fixture("volume.json")),
    )
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/BeoZone/Zone/Sound/Volume/Speaker/",
        json=json.loads(fixture("speaker-volume.json")),
    )
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/BeoZone/Zone/Sound/Volume/Speaker/Level/",
        json={"level": 34},
    )
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/BeoZone/Zone/Sound/Volume/Speaker/Level/",
        json={},
    )
    async with create_beo_client(HOST) as client:
        assert (await client.volume.get())["speaker"]["level"] == 34
        assert await client.volume.get_speaker() == {
            "level": 34,
            "muted": False,
            "range": {"minimum": 0, "maximum": 90},
        }
        assert await client.volume.get_speaker_level() == 34
        assert await client.volume.set_speaker_level(41) == {"ok": True, "level": 41}
    assert json.loads(httpx_mock.get_requests()[-1].content) == {"level": 41}


@pytest.mark.asyncio
async def test_unsupported_device_error(httpx_mock) -> None:
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/BeoZone/Zone/Sound/Volume/Headphone/",
        json={
            "error": {
                "message": "Sound/Volume/Headphone is not supported",
                "type": "NOT_IMPLEMENTED",
            }
        },
    )
    async with create_beo_client(HOST) as client:
        with pytest.raises(BeoError) as error:
            await client.volume.get_headphone()
    assert error.value.code == "UNSUPPORTED_OPERATION"


@pytest.mark.asyncio
async def test_queue_seek_and_netradio_and_setup(httpx_mock) -> None:
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/BeoZone/Zone/PlayQueue",
        json=json.loads(fixture("play-queue.json")),
    )
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/BeoZone/Zone/PlayQueue/PlayPointer",
        json={},
    )
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/BeoContent/netradio/netRadioProfile/",
        json=json.loads(fixture("netradio-profile.json")),
    )
    httpx_mock.add_response(url=f"http://{HOST}/version", text="1.2.3-test")
    async with create_beo_client(HOST) as client:
        queue = await client.queue.get()
        assert queue["items"][0]["contentKind"] == "station"
        assert queue["items"][0]["movePath"] == "/BeoZone/Zone/PlayQueue/item-1/move"
        assert await client.queue.seek({"playQueueItemId": "item-1", "positionSeconds": 73}) == {
            "ok": True,
            "playQueueItemId": "item-1",
            "positionSeconds": 73,
        }
        assert (await client.content.get_netradio_profile())["favoriteListsPath"] == (
            "/BeoContent/netradio/favoriteList/"
        )
        assert await client.setup.get_version() == {"version": "1.2.3-test", "raw": "1.2.3-test"}


@pytest.mark.asyncio
async def test_notify_path_fallback_and_parsing(httpx_mock) -> None:
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/", json={"services": [{"name": "BeoZone", "path": "/BeoZone"}]}
    )
    httpx_mock.add_response(
        url=f"http://{HOST}:8090/BeoZone/Notifications",
        text='{"id":1,"type":"VOLUME","data":{"speaker":{"level":1,"muted":false}}}',
    )
    async with create_beo_client(HOST) as client:
        stream = client.notify.stream()
        notification = await anext(stream)
    assert notification["id"] == 1
    assert notification["volume"]["speaker"]["level"] == 1


def test_notification_parser_accepts_concatenated_payloads() -> None:
    payload = (
        '{"id":1,"timestamp":"2026-04-28T18:00:00Z","type":"PROGRESS_INFORMATION",'
        '"data":{"state":"PLAY","position":12,"totalDuration":123,"playQueueItemId":"pq1"}}'
        '{"id":2,"timestamp":"2026-04-28T18:00:01Z","type":"VOLUME",'
        '"data":{"speaker":{"level":34,"muted":false,"range":{"minimum":0,"maximum":90}},'
        '"headphone":{"level":18,"muted":true,"range":{"minimum":0,"maximum":32}}}}'
    )
    notifications = [
        normalize_notification(item) for item in extract_notifications_from_text(payload)
    ]
    assert notifications[0]["progress"]["state"] == "PLAY"
    assert notifications[1]["volume"]["headphone"]["muted"] is True


def test_notification_parser_rejects_incomplete_payload() -> None:
    with pytest.raises(BeoError, match="incomplete JSON payload"):
        extract_notifications_from_text('{"id":1')


def test_host_validation_rejects_scheme_and_normalizes_ipv6() -> None:
    with pytest.raises(BeoError, match="URL scheme"):
        create_beo_client("http://192.168.1.2")
    client = create_beo_client("fe80::1")
    assert client.host == "fe80::1"
