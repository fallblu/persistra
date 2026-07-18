# Build research datasets

Research datasets are immutable tables at exact `(decision_at, instrument_id)` grain.
Each build binds a snapshot, dual cutoffs (public availability and project knowledge),
missing-input policies, and eligibility/input audits, and is addressed by content
identity so an exact retry reuses the existing build.

## Define and build

Inside a `RESEARCH_WRITE` lifecycle, define the dataset through
`project.services.research` with the universe, calendar, snapshot binding, and joined
canonical inputs, then build it. The result is a bounded handle — public queries are
row-limited and raise rather than truncate.

Temporal safety is structural:

- research decisions consume only facts whose persisted availability is at or before
  the decision cutoff;
- complete daily/bar facts become observable at their interval end;
- label and retrospective ancestry is structurally ineligible for portfolio or
  simulator decisions;
- opaque inputs require a content-addressed override and remain visibly tainted in
  downstream results, exports, and reports.

## Features and labels

Register executable features and labels through
`project.services.research.features`; managed operators without execution kernels are
rejected at registration. Materializations record exact identity (definition, inputs,
snapshot, configuration) and persist decision-input manifests for downstream safety
validation.

## Bounded SQL workspaces

`project.services.research` also provides parsed, read-only SQL over research data
using SQLGlot with static lineage and safety analysis. Label, retrospective, or opaque
ancestry cannot be laundered through SQL or workspaces: derived columns inherit the
strictest ancestry classification of their inputs. Workspace materializations are
immutable and versioned with resource limits and cancellation.
