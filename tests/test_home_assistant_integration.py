from __future__ import annotations

import importlib
import json
from pathlib import Path

COMPONENT = "custom_components.bang_olufsen_legacy"


def test_home_assistant_metadata_is_self_contained() -> None:
    root = Path(__file__).parents[1]
    manifest = json.loads(
        (root / "custom_components/bang_olufsen_legacy/manifest.json").read_text()
    )
    hacs = json.loads((root / "hacs.json").read_text())

    assert manifest["domain"] == "bang_olufsen_legacy"
    assert manifest["name"] == "Bang & Olufsen Legacy"
    assert manifest["integration_type"] == "device"
    assert manifest["iot_class"] == "local_push"
    assert manifest["requirements"] == []
    assert hacs["render_readme"] is True


def test_home_assistant_platform_modules_import() -> None:
    for module_name in (
        "__init__",
        "config_flow",
        "coordinator",
        "entity",
        "media_player",
        "select",
        "sensor",
    ):
        importlib.import_module(f"{COMPONENT}.{module_name}")
