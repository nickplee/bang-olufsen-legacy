# Bang & Olufsen Legacy

[![Tests](https://github.com/nickplee/bang-olufsen-legacy/actions/workflows/tests.yml/badge.svg)](https://github.com/nickplee/bang-olufsen-legacy/actions/workflows/tests.yml)
[![Open your Home Assistant instance and add this repository to HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=nickplee&repository=bang-olufsen-legacy&category=integration)

`bang-olufsen-legacy` provides a Home Assistant custom integration, async Python
client, and `beo` command-line tool for legacy Bang & Olufsen network products that
expose the older Beo control APIs.

## What Is Included

- Home Assistant custom integration: `custom_components/bang_olufsen_legacy`
- Async protocol client: `custom_components/bang_olufsen_legacy/api`
- CLI entry point: `beo`
- Protocol and CLI tests using `pytest`
- GitHub Actions test runner for CI

## Home Assistant Integration

The Home Assistant integration is named **Bang & Olufsen Legacy** and is designed for
HACS installation as a custom repository.

It currently exposes only capabilities implemented by the local legacy client:

- `media_player`: source selection, play, pause, stop, volume, mute, seek when the
  active queue item supports it, and state-gated power toggle.
- `select`: line-in sensitivity when the device exposes an editable line-in settings
  profile.
- `sensor`: diagnostic software/setup details returned by the device.

Setup is manual by host name or IP address. The integration uses the legacy control API
on port `8090` and setup API on port `80`.

### HACS Installation

1. Open HACS in Home Assistant.
2. Add `https://github.com/nickplee/bang-olufsen-legacy` as a custom integration
   repository.
3. Install **Bang & Olufsen Legacy**.
4. Restart Home Assistant.
5. Go to Settings -> Devices & services -> Add integration.
6. Search for **Bang & Olufsen Legacy** and enter the device host/IP address.

The button at the top of this README opens the HACS custom repository flow directly in
Home Assistant.

## Python Client

The async client is available from:

```python
from custom_components.bang_olufsen_legacy.api import create_beo_client
```

Example:

```python
import asyncio

from custom_components.bang_olufsen_legacy.api import create_beo_client


async def main() -> None:
    async with create_beo_client("192.168.1.25") as client:
        device = await client.device.get_info()
        sources = await client.zone.get_sources()
        print(device["productFriendlyName"])
        print([source["id"] for source in sources])


asyncio.run(main())
```

The client is async-only and uses HTTPX under the hood.

## CLI

The installed command remains `beo`.

```bash
uv run beo --help
uv run beo --host 192.168.1.25 device info --pretty
uv run beo --host 192.168.1.25 zone sources
uv run beo --host 192.168.1.25 volume show
```

The CLI preserves compact JSON by default, supports `--pretty`, and emits JSON-lines
for notification streaming.

## Development

This project is managed with `uv`.

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

Live smoke tests are skipped unless `BEO_HOST` is set. Optional ports can be overridden
with `BEO_CONTROL_PORT` and `BEO_SETUP_PORT`.

```bash
BEO_HOST=192.168.1.25 uv run pytest tests/test_live_smoke.py
```

## Compatibility

- Python: `>=3.14.2,<3.15`
- Home Assistant test target: `2026.4.x`
- HACS minimum Home Assistant version: `2026.4.0`

The project follows the current Home Assistant Python baseline for local development and
CI.
