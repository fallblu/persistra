# Agent instructions

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before you make a change. That file gives the
development, verification, Git, and release instructions.

## Project design

- Do not preserve backward compatibility. Remove obsolete paths instead.
- Choose the simplest implementation that meets the current requirements.
- Build each capability on a working product.
- Keep concerns separate and components modular.
- Prefer established libraries when they reduce complexity or improve reliability.
- Check current dependency documentation and types before adding code.
- Make long-term architectural decisions. Do not add temporary replacements.
- Use short, active sentences and plain American English in documentation and docstrings.
- Run `make docs-check` and `make docs-build` after a documentation change.

## Repository rules

- **Read `CONTRIBUTING.md` first.** Make sure that each change passes the full gate.
- **Do not add AI attribution.** Do not add attribution to commits, pull requests,
  code comments, or documentation.
- **Interview before nontrivial work.** Ask about scope, API shape, edge cases, and
  tests. Confirm the approach before you write code.
- **Humans control releases.** Do not push, tag, publish, or change a version without a
  direct user instruction.
