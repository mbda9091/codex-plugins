"""Approve literal output redirects into temporary directories without running them."""

import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

MAX_INPUT_BYTES = 65_536
MAX_COMMAND_LENGTH = 16_384
MAX_POLICY_OUTPUT_BYTES = 256 * 1024
SHELL_WRAPPERS = {
    "exec",
    "eval",
    "env",
    "command",
    "builtin",
    "source",
    "time",
    "nice",
    "nohup",
    "sudo",
    "sh",
    "bash",
    "zsh",
    "fish",
    ".",
    ":",
}


@dataclass(frozen=True)
class Redirect:
    argv: list[str]
    targets: list[str]


def read_word(command: str, index: int) -> tuple[str, int]:
    value = ""
    seen = False
    while index < len(command) and command[index] not in " \t>":
        quote = command[index]
        if quote in "\"'":
            end = command.find(quote, index + 1)
            if end < 0:
                raise ValueError("Unterminated quote")
            part = command[index + 1 : end]
            if re.fullmatch(r"[a-zA-Z0-9_./:=,+@% \-]*", part) is None:
                raise ValueError("Unsupported quoted syntax")
            value += part
            index = end + 1
        else:
            if re.fullmatch(r"[a-zA-Z0-9_./:=,+@%\-]", quote) is None:
                raise ValueError("Unsupported shell syntax")
            value += quote
            index += 1
        seen = True
    if not seen:
        raise ValueError("Missing word")
    return value, index


def parse_redirect(command: object) -> Redirect | None:
    """Accept a small literal grammar; never evaluate shell syntax."""
    if (
        not isinstance(command, str)
        or len(command) > MAX_COMMAND_LENGTH
        or any(character in command for character in "\r\n\0")
    ):
        return None
    argv: list[str] = []
    targets: list[str] = []
    index = 0
    redirected = stdout = False
    try:
        while index < len(command):
            while index < len(command) and command[index] in " \t":
                index += 1
            if index == len(command):
                break
            if command.startswith("2>&1", index):
                if not stdout or (index + 4 < len(command) and command[index + 4] not in " \t"):
                    return None
                index += 4
                redirected = True
                continue
            rest = command[index:]
            if re.match(r"[0-9]+>", rest) and not re.match(r"[12]>", rest):
                return None
            redirect = re.match(r"(1|2)?(>>?)", rest)
            if redirect:
                if not argv:
                    return None
                redirected = True
                index += redirect.end()
                while index < len(command) and command[index] in " \t":
                    index += 1
                target, index = read_word(command, index)
                targets.append(target)
                if redirect.group(1) != "2":
                    stdout = True
            else:
                if redirected:
                    return None
                word, index = read_word(command, index)
                argv.append(word)
    except ValueError:
        return None
    if not argv or not argv[0] or not targets or "=" in argv[0]:
        return None
    if argv[0].split("/")[-1] in SHELL_WRAPPERS:
        return None
    return Redirect(argv, targets)


def temporary_target(target: str) -> bool:
    if not os.path.isabs(target) or any(part in {"..", "."} for part in target.split("/")):
        return False
    prefix = next(
        (root for root in ("/tmp", "/private/tmp") if target.startswith(root + "/")), None
    )
    if prefix is None or target.endswith("/"):
        return False
    try:
        root = Path(prefix).resolve(strict=True)
        path = Path(target)
        parent = path.parent.resolve(strict=True)
        if not parent.is_relative_to(root) or not parent.is_dir():
            return False
        try:
            resolved = path.resolve(strict=True)
        except FileNotFoundError:
            # A new file is eligible; a dangling final symlink is not.
            try:
                path.lstat()
            except FileNotFoundError:
                return True
            return False
        return resolved.is_relative_to(root) and stat.S_ISREG(resolved.stat().st_mode)
    except OSError, ValueError, RuntimeError:
        return False


def rules_in(directory: Path) -> list[Path]:
    try:
        return sorted(path for path in directory.iterdir() if path.name.endswith(".rules"))
    except FileNotFoundError:
        return []


def policy_allows(
    argv: list[str], command: str, cwd: str, *, codex_home: Path | None = None, codex: str = "codex"
) -> bool:
    """Only explicit forbidden rules veto the temporary-directory whitelist."""
    home = codex_home or Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    files = rules_in(home / "rules") + rules_in(Path("/etc/codex/rules"))
    directory = Path(os.path.abspath(cwd))
    for ancestor in (directory, *directory.parents):
        files.extend(rules_in(ancestor / ".codex" / "rules"))
    files = list(dict.fromkeys(files))
    if not files:
        return True
    flags = [argument for path in files for argument in ("--rules", str(path))]

    def forbidden(arguments: list[str]) -> bool:
        # argv and command are data for execpolicy, never a command to execute.
        result = subprocess.run(
            [codex, "execpolicy", "check", *flags, "--", *arguments],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=1.5,
            check=True,
        )
        if len(result.stdout) > MAX_POLICY_OUTPUT_BYTES:
            raise ValueError("Policy output is too large")
        decision: object = json.loads(result.stdout)
        if not isinstance(decision, dict):
            raise ValueError("Expected a policy decision object")
        return cast("dict[str, object]", decision).get("decision") == "forbidden"

    if forbidden(argv):
        return False
    for shell in ("sh", "bash", "zsh", "/bin/sh", "/bin/bash", "/bin/zsh"):
        for flag in ("-c", "-lc"):
            if forbidden([shell, flag, command]):
                return False
    return True


def decide(
    event: object, allows: Callable[[list[str], str, str], bool] = policy_allows
) -> dict[str, object]:
    try:
        if not isinstance(event, dict):
            return {}
        payload = cast("dict[str, object]", event)
        if (
            payload.get("hook_event_name") != "PermissionRequest"
            or payload.get("tool_name") != "Bash"
        ):
            return {}
        cwd = payload.get("cwd")
        if not isinstance(cwd, str) or not os.path.isabs(cwd):
            return {}
        mode = payload.get("permission_mode")
        if mode and mode not in ("default", "acceptEdits"):
            return {}
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return {}
        command = cast("dict[str, object]", tool_input).get("command")
        parsed = parse_redirect(command)
        if parsed is None or not isinstance(command, str):
            return {}
        if not all(temporary_target(target) for target in parsed.targets):
            return {}
        if not allows(parsed.argv, command, cwd):
            return {}
        return {
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "allow"},
            }
        }
    except Exception:
        # Failure leaves the normal Codex approval flow in control.
        return {}


def main() -> int:
    response: dict[str, object] = {}
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) <= MAX_INPUT_BYTES:
            event: object = json.loads(raw.decode("utf-8"))
            response = decide(event)
    except ValueError, OSError, RecursionError:
        pass
    print(json.dumps(response))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
