# Codex Hooks development

- Use `uv run` and the Python version pinned in `.python-version`.
- This is a non-packaged application. Do not add wheel builds or console entry points.
- Implement runtime hooks and their tests in Python; runtime hooks use only the standard library.
- Keep runtime hooks under `plugins/personal-hooks/hooks/`; development dependencies stay in the root dev group.
- Hook stdout is a protocol channel. Put diagnostics on stderr and never execute commands from event payloads.
- Test rules and subprocess input/output before testing with a real Codex session.
- Run `make check` and `make pack` before handing off changes.
- Do not install or enable this plugin, change user hook registration, or grant hook trust as part of tests.
- Keep credentials, session data, logs, virtual environments, and build outputs out of Git and archives.
