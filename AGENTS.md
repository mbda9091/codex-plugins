# Codex Plugins development

- Use `uv run` and the Python version pinned in `.python-version`.
- This is a non-packaged application. Do not add wheel builds or console entry points.
- Implement runtime hooks and their tests in Python; runtime hooks use only the standard library.
- Plugin names must be explicitly chosen by the user, never inferred from hook names. Keep runtime hooks under `plugins/<plugin-name>/hooks/`; a plugin may contain multiple hooks.
- Keep development dependencies in the root dev group.
- Mirror plugin source directories under `tests/<plugin-name>/`; keep fixtures with their owning tests. Only repository-wide tooling and environment tests belong at the `tests/` top level.
- Hook stdout is a protocol channel. Put diagnostics on stderr and never execute commands from event payloads.
- Test rules and subprocess input/output before testing with a real Codex session.
- Run `make check` before handing off changes. Install and distribute plugins through the marketplace; do not add a separate ZIP build step.
- Do not install or enable this plugin, change user hook registration, or grant hook trust as part of tests.
- Keep credentials, session data, logs, virtual environments, and build outputs out of Git.
