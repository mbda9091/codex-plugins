import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import TypedDict, cast

ROOT = Path(__file__).resolve().parents[2]


class CommandHandler(TypedDict):
    command: str


class MatcherGroup(TypedDict):
    hooks: list[CommandHandler]


class HookDocument(TypedDict):
    hooks: dict[str, list[MatcherGroup]]


def test_packaged_hook_runs_from_path_with_spaces(tmp_path: Path) -> None:
    output = tmp_path / "release output"
    built = subprocess.run(
        [
            sys.executable,
            "-B",
            str(ROOT / "scripts/build_plugin.py"),
            "--plugin",
            "tmp-redirect-approval",
            "--output",
            str(output),
        ],
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
            "hooks/permission_request.py",
        }
        manifest = cast("dict[str, object]", json.loads(archive.read("plugin.json")))
        assert manifest["name"] == "tmp-redirect-approval"
        assert artifact.name == "tmp-redirect-approval-0.1.0.zip"
        cached = tmp_path / "plugin cache with spaces"
        archive.extractall(cached)
    hooks = cast(
        "HookDocument",
        json.loads((cached / "hooks/hooks.json").read_text(encoding="utf-8")),
    )
    assert set(hooks["hooks"]) == {"PermissionRequest"}
    environment = {**os.environ, "PLUGIN_ROOT": str(cached)}

    command = hooks["hooks"]["PermissionRequest"][0]["hooks"][0]["command"]
    with tempfile.TemporaryDirectory(prefix="codex-packaged-redirect-", dir="/tmp") as directory:
        target = Path(directory) / "candidate output.log"
        marker = Path(directory) / "candidate executed"
        result = subprocess.run(
            command,
            input=json.dumps(
                {
                    "hook_event_name": "PermissionRequest",
                    "tool_name": "Bash",
                    "cwd": str(tmp_path),
                    "permission_mode": "default",
                    "tool_input": {"command": f'touch "{marker}" > "{target}"'},
                }
            ),
            cwd=tmp_path,
            env={**environment, "CODEX_HOME": str(tmp_path / "isolated codex home")},
            shell=True,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        assert json.loads(result.stdout) == {
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "allow"},
            }
        }
        assert result.stderr == ""
        assert not marker.exists()
        assert not target.exists()


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
    manifest = cast("dict[str, object]", json.loads((plugin / "plugin.json").read_text()))
    assert plugin.name == manifest["name"] == "tmp-redirect-approval"
