# beo

Async Python client and CLI for BeoSound Essence Mk1 control APIs.

## Bang & Olufsen Legacy for Home Assistant

This repository also contains a self-contained HACS custom integration at
`custom_components/bang_olufsen_legacy`.

The integration exposes only the capabilities implemented by the local legacy client:

- `media_player` for source selection, play/pause/stop, volume, mute, seek when the
  current queue item supports it, and state-gated power toggle.
- `select` for line-in sensitivity when the device exposes an editable line-in settings
  profile.
- Diagnostic `sensor` entities for software/setup details available through the client.

Setup is manual by host/IP address. The integration uses the legacy control API on port
`8090` and setup API on port `80`.

## CLI

After installing the project, the `beo` command remains available:

```bash
uv run beo --help
```
