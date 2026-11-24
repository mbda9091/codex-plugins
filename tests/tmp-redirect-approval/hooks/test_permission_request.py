import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import permission_request as hook
import pytest

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "plugins/tmp-redirect-approval/hooks/permission_request.py"
)
ALLOW = {
    "hookSpecificOutput": {
        "hookEventName": "PermissionRequest",
        "decision": {"behavior": "allow"},
    }
}


@pytest.fixture
def directory() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="codex-redirect-test-", dir="/tmp") as value:
        yield Path(value)


def event(command: str, cwd: Path) -> dict[str, object]:
    return {
        "hook_event_name": "PermissionRequest",
        "tool_name": "Bash",
        "cwd": str(cwd),
        "permission_mode": "default",
        "tool_input": {"command": command},
    }


@pytest.mark.parametrize(
    ("command", "argv", "targets"),
    [
        (
            "./preview.sh --force > /tmp/preview.log 2>&1",
            ["./preview.sh", "--force"],
            ["/tmp/preview.log"],
        ),
        (
            './preview.sh --force 1>>"/tmp/preview log.txt" 2>/tmp/errors',
            ["./preview.sh", "--force"],
            ["/tmp/preview log.txt", "/tmp/errors"],
        ),
        ('echo "a b" 2 > /tmp/out', ["echo", "a b", "2"], ["/tmp/out"]),
        ("echo 'literal' >/tmp/out", ["echo", "literal"], ["/tmp/out"]),
    ],
)
def test_literal_redirects_preserve_argv(command: str, argv: list[str], targets: list[str]) -> None:
    assert hook.parse_redirect(command) == hook.Redirect(argv, targets)


@pytest.mark.parametrize(
    "command",
    [
        "./preview.sh --force",
        "echo hi > /tmp/out; rm -rf x",
        "echo hi > /tmp/out && other",
        "echo hi > /tmp/out | cat",
        "echo $(touch /tmp/oops) > /tmp/out",
        "echo `id` > /tmp/out",
        "echo $HOME > /tmp/out",
        "FOO=bar echo hi > /tmp/out",
        "echo * > /tmp/out",
        "echo hi < /tmp/in > /tmp/out",
        "echo hi > /tmp/out\nother",
        "echo hi > /tmp/out &",
        "echo hi > /tmp/out later",
        "echo hi 2>&1",
        "echo hi 2>&1 > /tmp/out",
        "echo hi > /tmp/out 2>&1oops",
        "echo hi > /tmp/out 2>&9",
        "echo hi &> /tmp/out",
        "echo hi >| /tmp/out",
        "echo hi 3>/tmp/out",
        "echo hi 12>/tmp/out",
        "echo hi 0>/tmp/out",
        "echo hi > /tmp/out # comment",
        "echo hi > /tmp/$(id)",
        'echo "unterminated > /tmp/out',
        'bash -c "echo hi" > /tmp/out',
        '/bin/zsh -lc "echo hi" > /tmp/out',
        "env echo hi > /tmp/out",
        "> /tmp/out",
        "echo hi >",
        "echo hi > /tmp/out\0",
        "echo ~ > /tmp/out",
        "x" * (hook.MAX_COMMAND_LENGTH + 1),
        None,
        [],
        {"command": "echo hi > /tmp/out"},
    ],
)
def test_shell_expansions_and_unsupported_syntax_fall_back(command: object) -> None:
    assert hook.parse_redirect(command) is None


def test_temporary_target_resolves_links_without_writing(directory: Path, tmp_path: Path) -> None:
    file = directory / "log"
    file.write_text("original")
    assert hook.temporary_target(str(file))
    assert hook.temporary_target(str(directory / "new"))
    assert not hook.temporary_target(str(directory))
    assert not hook.temporary_target(str(directory / "missing" / "new"))
    for value in ("/tmp-elsewhere/log", "/tmp/../outside", "/tmp/./log", "tmp/log"):
        assert not hook.temporary_target(value)
    (directory / "escape").symlink_to("/etc", target_is_directory=True)
    assert not hook.temporary_target(str(directory / "escape" / "hosts"))
    (directory / "link").symlink_to(file)
    assert hook.temporary_target(str(directory / "link"))
    (directory / "dangling").symlink_to(directory / "absent")
    assert not hook.temporary_target(str(directory / "dangling"))
    (directory / "loop").symlink_to(directory / "loop")
    assert not hook.temporary_target(str(directory / "loop"))
    (directory / "hardlink").hardlink_to(file)
    assert hook.temporary_target(str(directory / "hardlink"))
    (directory / "outside").symlink_to(tmp_path, target_is_directory=True)
    if not tmp_path.resolve().is_relative_to(Path("/tmp").resolve()):
        assert not hook.temporary_target(str(directory / "outside" / "new"))
    if Path("/private/tmp").exists():
        assert hook.temporary_target("/private" + str(file))
    assert file.read_text() == "original"
    assert not (directory / "new").exists()


def test_eligible_request_passes_literal_data_to_policy(directory: Path) -> None:
    command = f'./preview.sh --force > "{directory}/output" 2>&1'
    checks: list[tuple[list[str], str, str]] = []

    def allows(argv: list[str], original: str, cwd: str) -> bool:
        checks.append((argv, original, cwd))
        return True

    assert hook.decide(event(command, directory), allows) == ALLOW
    assert checks == [(["./preview.sh", "--force"], command, str(directory))]
    assert hook.decide(event(command, directory), lambda _argv, _command, _cwd: False) == {}
    assert list(directory.iterdir()) == []


@pytest.mark.parametrize(
    "replacement",
    [
        {"hook_event_name": "PreToolUse"},
        {"tool_name": "tools.exec_command"},
        {"permission_mode": "plan"},
        {"permission_mode": "dontAsk"},
        {"cwd": "relative"},
        {"cwd": None},
        {"tool_input": None},
        {"tool_input": {"command": []}},
        {"tool_input": {"command": "rm -rf anything"}},
        {"tool_input": {"command": "echo hi >/Users/someone/log"}},
        {"tool_input": {"command": "echo hi >/tmp/good 2>/etc/bad"}},
    ],
)
def test_ineligible_requests_never_reach_policy(
    directory: Path, replacement: dict[str, object]
) -> None:
    def unexpected(*_args: object) -> bool:
        pytest.fail("Ineligible requests must not reach policy")

    payload = {**event(f"echo hi > {directory}/output", directory), **replacement}
    assert hook.decide(payload, unexpected) == {}


def test_real_execpolicy_respects_forbidden_rules_and_original_shell(
    directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = directory / "user"
    cwd = directory / "project"
    user = home / "rules" / "default.rules"
    project = cwd / ".codex" / "rules" / "project.rules"
    user.parent.mkdir(parents=True)
    project.parent.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(home))
    command = f"./preview.sh --force > {directory}/output 2>&1"

    def allows(argv: list[str], original: str, working_directory: str) -> bool:
        return hook.policy_allows(argv, original, working_directory, codex_home=home)

    user.write_text('prefix_rule(pattern=["./preview.sh"], decision="allow")\n')
    assert allows(["./preview.sh", "--force"], command, str(cwd))
    assert allows(["unapproved"], command, str(cwd))
    project.write_text('prefix_rule(pattern=["./preview.sh", "--force"], decision="prompt")\n')
    assert allows(["./preview.sh", "--force"], command, str(cwd))
    project.write_text('prefix_rule(pattern=["unapproved"], decision="forbidden")\n')
    assert not allows(["unapproved"], command, str(cwd))
    user.write_text(
        'prefix_rule(pattern=["./preview.sh"], decision="allow")\n'
        'prefix_rule(pattern=["/bin/zsh", "-lc"], decision="forbidden")\n'
    )
    assert not allows(["./preview.sh", "--force"], command, str(cwd))
    user.write_text("invalid policy!!!")
    assert hook.decide(event(command, cwd), allows) == {}
    user.write_text('prefix_rule(pattern=["./preview.sh"], decision="allow")\n')
    assert (
        hook.decide(
            event(command, cwd),
            lambda argv, original, wd: hook.policy_allows(
                argv, original, wd, codex_home=home, codex=str(directory / "missing-codex")
            ),
        )
        == {}
    )


def test_policy_failure_falls_back(directory: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = directory / "home"
    (home / "rules").mkdir(parents=True)
    (home / "rules" / "default.rules").write_text("")
    command = f"echo hi > {directory}/output"

    def unavailable(_args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired("codex", 1.5)

    monkeypatch.setattr(hook.subprocess, "run", unavailable)
    assert (
        hook.decide(
            event(command, directory),
            lambda argv, original, cwd: hook.policy_allows(argv, original, cwd, codex_home=home),
        )
        == {}
    )


def run_hook(payload: bytes, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT)],
        input=payload,
        cwd=cwd,
        env={**os.environ, "CODEX_HOME": str(cwd / "isolated-home")},
        capture_output=True,
        check=False,
        timeout=10,
    )


def test_protocol_returns_decision_without_executing_command(directory: Path) -> None:
    marker, target = directory / "executed", directory / "output"
    result = run_hook(
        json.dumps(event(f'touch "{marker}" > "{target}"', directory)).encode(), directory
    )
    assert result.returncode == 0
    assert result.stderr == b""
    assert json.loads(result.stdout) == ALLOW
    assert list(directory.iterdir()) == []


@pytest.mark.parametrize(
    "payload",
    [
        b"{",
        b"[]",
        b"null",
        b"\xff",
        b"x" * (hook.MAX_INPUT_BYTES + 1),
        b"[" * 2000 + b"]" * 2000,
    ],
)
def test_invalid_protocol_input_returns_empty_decision(directory: Path, payload: bytes) -> None:
    result = run_hook(payload, directory)
    assert result.returncode == 0
    assert result.stderr == b""
    assert json.loads(result.stdout) == {}
