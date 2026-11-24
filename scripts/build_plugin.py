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
PLUGIN = ROOT / "plugins" / "personal-hooks"


def read_object(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return cast("dict[str, object]", value)


def build(output: Path) -> Path:
    manifest = read_object(PLUGIN / "plugin.json")
    read_object(PLUGIN / "hooks" / "hooks.json")
    name, version = manifest.get("name"), manifest.get("version")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        raise ValueError("Invalid plugin name")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Expected a numeric major.minor.patch version")
    files = [
        PLUGIN / "plugin.json",
        *sorted((PLUGIN / "hooks").rglob("*.json")),
        *sorted((PLUGIN / "hooks").rglob("*.py")),
    ]
    for path in files:
        if path.is_symlink() or not path.resolve().is_relative_to(PLUGIN.resolve()):
            raise ValueError(f"Plugin sources must stay inside the plugin: {path}")
    output.mkdir(parents=True, exist_ok=True)
    destination = output / f"{name}-{version}.zip"
    with tempfile.NamedTemporaryFile(dir=output, suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                info = zipfile.ZipInfo(path.relative_to(PLUGIN).as_posix())
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    print(build(cast("Path", args.output)))


if __name__ == "__main__":
    main()
