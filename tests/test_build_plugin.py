import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("frontend", ["cli", "make"])
def test_pack_requires_explicit_plugin(frontend: str, tmp_path: Path) -> None:
    command = (
        [sys.executable, "-B", str(ROOT / "scripts/build_plugin.py"), "--output", str(tmp_path)]
        if frontend == "cli"
        else ["make", "-C", str(ROOT), "pack"]
    )
    environment = dict(os.environ)
    environment.pop("PLUGIN", None)
    result = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode != 0
    assert ("--plugin" if frontend == "cli" else "PLUGIN") in result.stderr
    assert list(tmp_path.iterdir()) == []
