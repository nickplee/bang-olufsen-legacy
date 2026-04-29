from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Awaitable, Callable, Coroutine
from typing import Annotated, Any

import typer

from custom_components.bang_olufsen_legacy.api.client import (
    BeoClient,
    TransportCommand,
    create_beo_client,
)
from custom_components.bang_olufsen_legacy.api.errors import BeoError

app = typer.Typer(help="BeoSound Essence Mk1 control CLI", no_args_is_help=True)
device_app = typer.Typer(help="Device operations")
device_line_in_app = typer.Typer(help="Line-in settings")
zone_app = typer.Typer(help="Zone operations")
transport_app = typer.Typer(help="Transport and power commands")
volume_app = typer.Typer(help="Volume operations")
queue_app = typer.Typer(help="Play queue operations")
notify_app = typer.Typer(help="Notification streaming")
content_app = typer.Typer(help="Content profile operations")
setup_app = typer.Typer(help="Setup UI probes")

app.add_typer(device_app, name="device")
device_app.add_typer(device_line_in_app, name="line-in")
app.add_typer(zone_app, name="zone")
app.add_typer(transport_app, name="transport")
app.add_typer(volume_app, name="volume")
app.add_typer(queue_app, name="queue")
app.add_typer(notify_app, name="notify")
app.add_typer(content_app, name="content")
app.add_typer(setup_app, name="setup")

HostOption = Annotated[str, typer.Option("--host", help="Device hostname or IP address")]
TimeoutOption = Annotated[int, typer.Option("--timeout-ms", min=1)]
PrettyOption = Annotated[bool, typer.Option("--pretty", help="Pretty-print JSON output")]

_client_factory: Callable[..., Any] = create_beo_client


def set_client_factory(factory: Callable[..., Any]) -> None:
    global _client_factory
    _client_factory = factory


def _normalize_error(error: BaseException) -> dict[str, Any]:
    if isinstance(error, BeoError):
        return error.to_dict()
    return {"name": error.__class__.__name__, "message": str(error)}


def _write_json(value: Any, *, pretty: bool) -> None:
    if pretty:
        typer.echo(json.dumps(value, indent=2))
    else:
        typer.echo(json.dumps(value, separators=(",", ":")))


def _run(
    action: Callable[[], Coroutine[Any, Any, Any]], *, pretty: bool, stream: bool = False
) -> None:
    try:
        result = asyncio.run(action())
    except Exception as exc:
        typer.echo(json.dumps(_normalize_error(exc), separators=(",", ":")), err=True)
        raise typer.Exit(1) from exc
    if not stream:
        _write_json(result, pretty=pretty)


async def _with_client(
    host: str,
    control_port: int,
    setup_port: int,
    timeout_ms: int,
    action: Callable[[BeoClient], Awaitable[Any]],
) -> Any:
    client = _client_factory(
        host=host,
        control_port=control_port,
        setup_port=setup_port,
        timeout_ms=timeout_ms,
    )
    async with client:
        return await action(client)


def _source_metadata(sources: list[dict[str, Any]], source_id: str) -> dict[str, Any] | None:
    match = next((source for source in sources if source.get("id") == source_id), None)
    if match is None:
        return None
    product = match.get("product")
    return {
        "friendlyName": match.get("friendlyName"),
        "productJabberId": product.get("jid") if isinstance(product, dict) else None,
        "productFriendlyName": product.get("friendlyName") if isinstance(product, dict) else None,
    }


@app.command()
def services(
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _run(
        lambda: _with_client(host, control_port, setup_port, timeout_ms, lambda c: c.services()),
        pretty=pretty,
    )


@app.command()
def ping(
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _run(
        lambda: _with_client(host, control_port, setup_port, timeout_ms, lambda c: c.ping()),
        pretty=pretty,
    )


@device_app.command("info")
def device_info(
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _run(
        lambda: _with_client(
            host, control_port, setup_port, timeout_ms, lambda c: c.device.get_info()
        ),
        pretty=pretty,
    )


@device_line_in_app.command("show")
def device_line_in_show(
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _run(
        lambda: _with_client(
            host, control_port, setup_port, timeout_ms, lambda c: c.device.line_in.get()
        ),
        pretty=pretty,
    )


@device_line_in_app.command("set-sensitivity")
def device_line_in_set_sensitivity(
    value: Annotated[str, typer.Option("--value", help="Sensitivity: high, medium, or low")],
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _run(
        lambda: _with_client(
            host,
            control_port,
            setup_port,
            timeout_ms,
            lambda c: c.device.line_in.set_sensitivity(value),
        ),
        pretty=pretty,
    )


@zone_app.command("sources")
def zone_sources(
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _run(
        lambda: _with_client(
            host, control_port, setup_port, timeout_ms, lambda c: c.zone.get_sources()
        ),
        pretty=pretty,
    )


@zone_app.command("active-source")
def zone_active_source(
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _run(
        lambda: _with_client(
            host, control_port, setup_port, timeout_ms, lambda c: c.zone.get_active_sources()
        ),
        pretty=pretty,
    )


@zone_app.command("features")
def zone_features(
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _run(
        lambda: _with_client(
            host, control_port, setup_port, timeout_ms, lambda c: c.zone.get_features()
        ),
        pretty=pretty,
    )


@zone_app.command("set-source")
def zone_set_source(
    source_id: Annotated[str, typer.Option("--id", help="Source identifier")],
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    async def action(client: BeoClient) -> Any:
        sources = await client.zone.get_sources()
        return await client.zone.set_active_source(source_id, _source_metadata(sources, source_id))

    _run(lambda: _with_client(host, control_port, setup_port, timeout_ms, action), pretty=pretty)


def _transport_command(
    command_name: TransportCommand,
    host: str,
    control_port: int,
    setup_port: int,
    timeout_ms: int,
    pretty: bool,
) -> None:
    _run(
        lambda: _with_client(
            host,
            control_port,
            setup_port,
            timeout_ms,
            lambda c: c.zone.command(command_name),
        ),
        pretty=pretty,
    )


@transport_app.command()
def play(
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _transport_command("play", host, control_port, setup_port, timeout_ms, pretty)


@transport_app.command()
def pause(
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _transport_command("pause", host, control_port, setup_port, timeout_ms, pretty)


@transport_app.command()
def stop(
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _transport_command("stop", host, control_port, setup_port, timeout_ms, pretty)


@transport_app.command("toggle-power")
def toggle_power(
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _transport_command("toggle-power", host, control_port, setup_port, timeout_ms, pretty)


def _volume_action(
    method_name: str,
    host: str,
    control_port: int,
    setup_port: int,
    timeout_ms: int,
    pretty: bool,
    *args: Any,
) -> None:
    async def action(client: BeoClient) -> Any:
        method = getattr(client.volume, method_name)
        return await method(*args)

    _run(lambda: _with_client(host, control_port, setup_port, timeout_ms, action), pretty=pretty)


def _parse_bool_string(value: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise typer.BadParameter('Muted must be either "true" or "false".')


@volume_app.command("show")
def volume_show(
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _volume_action("get", host, control_port, setup_port, timeout_ms, pretty)


@volume_app.command("speaker")
def volume_speaker(
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _volume_action("get_speaker", host, control_port, setup_port, timeout_ms, pretty)


@volume_app.command("set-speaker")
def volume_set_speaker(
    level: Annotated[int, typer.Option("--level", min=0)],
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _volume_action("set_speaker_level", host, control_port, setup_port, timeout_ms, pretty, level)


@volume_app.command("mute-speaker")
def volume_mute_speaker(
    muted: Annotated[str, typer.Option("--muted")],
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _volume_action(
        "set_speaker_muted",
        host,
        control_port,
        setup_port,
        timeout_ms,
        pretty,
        _parse_bool_string(muted),
    )


@volume_app.command("headphone")
def volume_headphone(
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _volume_action("get_headphone", host, control_port, setup_port, timeout_ms, pretty)


@volume_app.command("set-headphone")
def volume_set_headphone(
    level: Annotated[int, typer.Option("--level", min=0)],
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _volume_action("set_headphone_level", host, control_port, setup_port, timeout_ms, pretty, level)


@volume_app.command("mute-headphone")
def volume_mute_headphone(
    muted: Annotated[str, typer.Option("--muted")],
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _volume_action(
        "set_headphone_muted",
        host,
        control_port,
        setup_port,
        timeout_ms,
        pretty,
        _parse_bool_string(muted),
    )


@queue_app.command("show")
def queue_show(
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _run(
        lambda: _with_client(host, control_port, setup_port, timeout_ms, lambda c: c.queue.get()),
        pretty=pretty,
    )


@queue_app.command("seek")
def queue_seek(
    item_id: Annotated[str, typer.Option("--item-id")],
    position: Annotated[int, typer.Option("--position", min=0)],
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _run(
        lambda: _with_client(
            host,
            control_port,
            setup_port,
            timeout_ms,
            lambda c: c.queue.seek({"playQueueItemId": item_id, "positionSeconds": position}),
        ),
        pretty=pretty,
    )


@notify_app.command("stream")
def notify_stream(
    host: HostOption,
    last_id: Annotated[str | None, typer.Option("--last-id")] = None,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    async def action() -> None:
        client = _client_factory(
            host=host, control_port=control_port, setup_port=setup_port, timeout_ms=timeout_ms
        )
        async with client:
            async for notification in client.notify.stream(last_id=last_id):
                _write_json(notification, pretty=pretty)

    _run(action, pretty=pretty, stream=True)


@content_app.command("netradio")
def content_netradio(
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _run(
        lambda: _with_client(
            host, control_port, setup_port, timeout_ms, lambda c: c.content.get_netradio_profile()
        ),
        pretty=pretty,
    )


@setup_app.command("version")
def setup_version(
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _run(
        lambda: _with_client(
            host, control_port, setup_port, timeout_ms, lambda c: c.setup.get_version()
        ),
        pretty=pretty,
    )


@setup_app.command("health")
def setup_health(
    host: HostOption,
    control_port: Annotated[int, typer.Option("--control-port", min=1)] = 8090,
    setup_port: Annotated[int, typer.Option("--setup-port", min=1)] = 80,
    timeout_ms: TimeoutOption = 10000,
    pretty: PrettyOption = False,
) -> None:
    _run(
        lambda: _with_client(
            host, control_port, setup_port, timeout_ms, lambda c: c.setup.get_index()
        ),
        pretty=pretty,
    )


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
