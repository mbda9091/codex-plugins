"""Archive runtime JSON and Python files only, without installing the plugin."""

import argparse
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]


def read_object(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return cast("dict[str, object]", value)


def build(output: Path, plugin_name: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", plugin_name):
        raise ValueError("Invalid plugin directory name")
    plugin = ROOT / "plugins" / plugin_name
    manifest = read_object(plugin / "plugin.json")
    read_object(plugin / "hooks" / "hooks.json")
    name, version = manifest.get("name"), manifest.get("version")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        raise ValueError("Invalid plugin name")
    if name != plugin_name:
        raise ValueError("Plugin name must match its directory name")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Expected a numeric major.minor.patch version")
    files = [
        plugin / "plugin.json",
        *sorted((plugin / "hooks").rglob("*.json")),
        *sorted((plugin / "hooks").rglob("*.py")),
    ]
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(plugin.resolve()):
            raise ValueError(f"Plugin sources must stay inside the plugin: {path}")
    output.mkdir(parents=True, exist_ok=True)
    destination = output / f"{name}-{version}.zip"
    with tempfile.NamedTemporaryFile(dir=output, suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                info = zipfile.ZipInfo(path.relative_to(plugin).as_posix())
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin", required=True, help="Explicit plugin name under plugins/")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    print(build(cast("Path", args.output), cast("str", args.plugin)))


if __name__ == "__main__":
    main()
