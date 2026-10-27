---
description: Phase 2 – write docs/product/tech-stack.md (current vs target)
---

Create or update docs/product/tech-stack.md with two sections:

- **Current**: what the project actually uses, verified from package/lock files and config, with versions. No guesses: if something can't be verified, mark it "unverified".
- **Target**: where the stack should go.

For every meaningful gap (outdated framework, deprecated library, missing tooling such as tests, linting, CI or type checking), use the AskUserQuestion tool to let me choose keep / upgrade / replace. Put your recommended option first, labelled "(Recommended)", with a one-line reason. Group related decisions into rounds of up to 4 questions.

Write the Target section only from my answers.
