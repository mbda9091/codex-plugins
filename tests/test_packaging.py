import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import TypedDict, cast

ROOT = Path(__file__).resolve().parents[1]


class CommandHandler(TypedDict):
    command: str


class MatcherGroup(TypedDict):
    hooks: list[CommandHandler]


class HookDocument(TypedDict):
    hooks: dict[str, list[MatcherGroup]]


def test_packaged_hook_runs_from_path_with_spaces(tmp_path: Path) -> None:
    output = tmp_path / "release output"
    built = subprocess.run(
        [sys.executable, "-B", str(ROOT / "scripts/build_plugin.py"), "--output", str(output)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    artifact = Path(built.stdout.strip())
    with zipfile.ZipFile(artifact) as archive:
        assert set(archive.namelist()) == {
            "plugin.json",
            "hooks/hooks.json",
            "hooks/session_start.py",
        }
        manifest = cast("dict[str, object]", json.loads(archive.read("plugin.json")))
        assert manifest["name"] == "personal-hooks"
        cached = tmp_path / "plugin cache with spaces"
        archive.extractall(cached)
    hooks = cast(
        "HookDocument",
        json.loads((cached / "hooks/hooks.json").read_text(encoding="utf-8")),
    )
    command = hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    environment = {**os.environ, "PLUGIN_ROOT": str(cached)}
    result = subprocess.run(
        command,
        input=json.dumps({"hook_event_name": "SessionStart"}),
        cwd=tmp_path,
        env=environment,
        shell=True,
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    )
    response = cast("dict[str, dict[str, str]]", json.loads(result.stdout))
    assert response["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert result.stderr == ""


def test_marketplace_points_to_a_complete_plugin() -> None:
    marketplace = cast(
        "dict[str, list[dict[str, dict[str, str]]]]",
        json.loads((ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8")),
    )
    relative = marketplace["plugins"][0]["source"]["path"]
    plugin = (ROOT / relative).resolve()
    assert plugin.is_relative_to(ROOT)
    assert (plugin / "plugin.json").is_file()
    assert (plugin / "hooks/hooks.json").is_file()
