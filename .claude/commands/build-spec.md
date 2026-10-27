---
description: Phase 5b – implement an approved spec task by task
---

Spec folder: $ARGUMENTS
If empty, use the most recent folder in docs/specs/.

Implement its tasks.md one task at a time:
1. Do the task.
2. Run the tests (and lint/type checks if configured). Fix failures before moving on.
3. Tick the task off in tasks.md.

If a task turns out wrong or unclear, stop and ask me with AskUserQuestion instead of improvising.

When all tasks are done:
- Verify every acceptance criterion in spec.md and report the result.
- Check the item off in docs/product/roadmap.md.
- Update docs/product/tech-stack.md if anything in the stack changed.
- Commit with a message referencing the spec folder.
