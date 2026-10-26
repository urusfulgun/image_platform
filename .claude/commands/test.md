---
description: Run tests for one service, or every service with a tests/ folder
argument-hint: "[service] [pytest args]  e.g. bff-token-handler -k logout"
allowed-tools: Bash(uv run:*), Bash(uv sync:*), Bash(bun run test:*), Bash(ls:*)
---
Run the test suite. Arguments: `$ARGUMENTS`

1. **Pick the target(s).** The first argument names a directory under `services/`.
   - No argument: run every Python service that has a `tests/` folder (`ls -d services/*/tests`), one after another.
   - `frontend`: run `bun run test --watch=false` from `services/frontend`.
   - Anything else that isn't a directory under `services/`: list the valid service names and stop.
2. **Run pytest** for each Python target from inside its directory, passing the remaining arguments through:
   `cd services/<service> && uv run --extra dev pytest <remaining args>`
   If the run fails because of an import or missing-package error, run `uv sync --extra dev` once and retry.
3. **Report back.**
   - When everything passes: one line per service with its pass count.
   - When something fails: show each failing test as `path/to/test_file.py:line`, with the assertion or exception in one or two lines and your best guess at the cause from reading the code under test.
   - Don't change any code unless I ask.
