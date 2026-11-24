import json
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins/personal-hooks/hooks/session_start.py"


def run_hook(script: Path, payload: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(script)],
        input=payload,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )


def test_session_start_protocol_from_another_directory(tmp_path: Path) -> None:
    payload = (ROOT / "fixtures/session-start.json").read_text(encoding="utf-8")
    result = run_hook(SCRIPT, payload, tmp_path)
    assert result.returncode == 0
    assert result.stderr == ""
    response = cast("dict[str, dict[str, str]]", json.loads(result.stdout))
    assert response["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert response["hookSpecificOutput"]["additionalContext"]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("payload", ["{invalid", "[]", "null"])
def test_invalid_payload_has_no_protocol_output(tmp_path: Path, payload: str) -> None:
    result = run_hook(SCRIPT, payload, tmp_path)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr


def test_unrelated_event_is_ignored(tmp_path: Path) -> None:
    result = run_hook(SCRIPT, json.dumps({"hook_event_name": "Stop"}), tmp_path)
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""
