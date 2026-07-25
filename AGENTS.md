# Agent instructions

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before you make a change. That file gives the
development, verification, Git, and release instructions.

## Simplified Technical English

ASD-STE100 Simplified Technical English, Issue 9, is necessary for all documentation
and docstrings.

Use these requirements:

- Use approved dictionary words only with their approved meaning and part of speech.
- Use American English spelling.
- Use short, clear sentences.
- Use a maximum of 20 words in each procedural sentence.
- Use a maximum of 25 words in each descriptive sentence.
- Use the active voice. You can use the passive voice only when the agent is unknown.
- Do not use a semicolon.
- Do not omit words or use contractions.
- Use one term for one concept.
- Use vertical lists for complex information.
- Review each change manually against the Issue 9 dictionary.
- Run `make docs-check` and `make docs-build` after a documentation change.

Approved project terminology includes nouns and verbs from these subject fields:

- Python and software engineering
- Database systems and data formats
- Finance, accounting, and market research
- Statistics, mathematics, and data science
- Persistra identifiers and public API terms

Keep code, commands, identifiers, paths, URLs, formulas, and quoted output unchanged.
These items are literal technical content. Generated signatures and type annotations
are also literal technical content.

## Repository rules

- **Read `CONTRIBUTING.md` first.** Make sure that each change passes the full gate.
- **Do not add AI attribution.** Do not add attribution to commits, pull requests,
  code comments, or documentation.
- **Interview before nontrivial work.** Ask about scope, API shape, edge cases, and
  tests. Confirm the approach before you write code.
- **Humans control releases.** Do not push, tag, publish, or change a version without a
  direct user instruction.

[ste]: https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf
