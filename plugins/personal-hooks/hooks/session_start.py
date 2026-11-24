"""Minimal SessionStart example; no file writes or external actions."""

import json
import sys
from typing import cast


def main() -> int:
    try:
        value: object = json.load(sys.stdin)
    except ValueError, OSError:
        print("Expected a JSON event on stdin.", file=sys.stderr)
        return 1
    if not isinstance(value, dict):
        print("Expected a JSON object.", file=sys.stderr)
        return 1
    event = cast("dict[str, object]", value)
    if event.get("hook_event_name") != "SessionStart":
        return 0
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "The personal-hooks development example is available.",
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
