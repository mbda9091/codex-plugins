import json
import os
import queue
import shlex
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import TypedDict, cast

ROOT = Path(__file__).resolve().parents[2]


class CommandHandler(TypedDict):
    command: str


class MatcherGroup(TypedDict):
    hooks: list[CommandHandler]


class HookDocument(TypedDict):
    hooks: dict[str, list[MatcherGroup]]


def test_registered_hook_runs_from_path_with_spaces(tmp_path: Path) -> None:
    cached = tmp_path / "plugin copy with spaces"
    shutil.copytree(
        ROOT / "plugins/tmp-redirect-approval",
        cached,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    hooks = cast(
        "HookDocument",
        json.loads((cached / "hooks/hooks.json").read_text(encoding="utf-8")),
    )
    assert set(hooks["hooks"]) == {"PermissionRequest"}
    environment = {**os.environ, "PLUGIN_ROOT": str(cached)}

    command = hooks["hooks"]["PermissionRequest"][0]["hooks"][0]["command"]
    arguments = [part.replace("${PLUGIN_ROOT}", str(cached)) for part in shlex.split(command)]
    with tempfile.TemporaryDirectory(prefix="codex-registered-redirect-", dir="/tmp") as directory:
        target = Path(directory) / "candidate output.log"
        marker = Path(directory) / "candidate executed"
        result = subprocess.run(
            arguments,
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
    assert (plugin / ".codex-plugin/plugin.json").is_file()
    assert (plugin / "hooks/hooks.json").is_file()
    manifest = cast(
        "dict[str, object]", json.loads((plugin / ".codex-plugin/plugin.json").read_text())
    )
    assert plugin.name == manifest["name"] == "tmp-redirect-approval"


def test_codex_discovers_permission_request_without_installing(tmp_path: Path) -> None:
    codex_home = tmp_path / "isolated-codex-home"
    codex_home.mkdir()
    replies: queue.Queue[dict[str, object]] = queue.Queue()
    with subprocess.Popen(
        ["codex", "app-server", "--stdio"],
        cwd=tmp_path,
        env={**os.environ, "CODEX_HOME": str(codex_home)},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    ) as process:
        stdin, stdout = process.stdin, process.stdout
        assert stdin is not None and stdout is not None

        def read_replies() -> None:
            for line in stdout:
                value: object = json.loads(line)
                if isinstance(value, dict):
                    replies.put(cast("dict[str, object]", value))

        reader = threading.Thread(target=read_replies, daemon=True)
        reader.start()

        def request(identifier: int, method: str, params: dict[str, object]) -> dict[str, object]:
            stdin.write(json.dumps({"id": identifier, "method": method, "params": params}) + "\n")
            stdin.flush()
            while True:
                reply = replies.get(timeout=20)
                if reply.get("id") == identifier:
                    assert "error" not in reply, reply
                    return cast("dict[str, object]", reply["result"])

        try:
            request(
                1,
                "initialize",
                {
                    "clientInfo": {"name": "plugin_discovery_test", "title": None, "version": "1"},
                    "capabilities": {"experimentalApi": True, "requestAttestation": False},
                },
            )
            stdin.write(json.dumps({"method": "initialized"}) + "\n")
            stdin.flush()
            result = request(
                2,
                "plugin/read",
                {
                    "marketplacePath": str(ROOT / ".agents/plugins/marketplace.json"),
                    "pluginName": "tmp-redirect-approval",
                },
            )
            plugin = cast("dict[str, object]", result["plugin"])
            summary = cast("dict[str, object]", plugin["summary"])
            discovered = cast("list[dict[str, object]]", plugin["hooks"])
            assert summary["installed"] is False
            assert [(hook["eventName"], hook["key"]) for hook in discovered] == [
                (
                    "permissionRequest",
                    "tmp-redirect-approval@mbda9091-codex-plugins:"
                    "hooks/hooks.json:permission_request:0:0",
                )
            ]
        finally:
            process.terminate()
            process.wait(timeout=5)
            reader.join(timeout=5)
