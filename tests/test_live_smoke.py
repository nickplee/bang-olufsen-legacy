from __future__ import annotations

import os

import pytest

from beo import create_beo_client

pytestmark = pytest.mark.skipif(not os.environ.get("BEO_HOST"), reason="BEO_HOST not set")


@pytest.mark.asyncio
async def test_live_control_root() -> None:
    async with create_beo_client(
        os.environ["BEO_HOST"],
        control_port=int(os.environ.get("BEO_CONTROL_PORT", "8090")),
        setup_port=int(os.environ.get("BEO_SETUP_PORT", "80")),
    ) as client:
        assert len(await client.services()) > 0


@pytest.mark.asyncio
async def test_live_device_and_volume() -> None:
    async with create_beo_client(
        os.environ["BEO_HOST"],
        control_port=int(os.environ.get("BEO_CONTROL_PORT", "8090")),
        setup_port=int(os.environ.get("BEO_SETUP_PORT", "80")),
    ) as client:
        assert len((await client.device.get_info())["serialNumber"]) > 0
        assert (await client.volume.get())["speaker"]["level"] >= 0
