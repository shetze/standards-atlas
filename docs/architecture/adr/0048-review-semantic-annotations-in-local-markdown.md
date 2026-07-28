# ADR 0048: Review semantic annotations in local Markdown

## Status

Accepted

## Context

Baseline proposal runs preserve provider requests, responses, and content-safe annotation candidates.
The candidates still require human review before they can become qualification evidence. Reviewers
need the local clause context, while published corpus data must not contain licensed standard text.
The workflow must also detect stale reviews, accidental edits to accepted proposals, duplicate
reviews, and conflicts with already imported annotations.

## Decision

Standards Atlas exports each proposal candidate as a Markdown review document below a caller-selected
local directory. The document contains local prompt and clause context, a readable proposal summary,
and one machine-readable YAML block marked with
`standards-atlas-semantic-review:v1`.

The reviewer edits only that YAML block and records a decision, reviewed semantic roles, reviewer,
optional timestamp, confidence, and comment. Import validates the embedded clause key and content
hash against the original proposal run. It then creates a canonical `reviewed` annotation below
`local/evaluation/corpora` while preserving the generated proposal and its provenance.

Decision rules are explicit:

- `accepted` must preserve the generated role selection;
- `corrected` must change the generated role selection;
- `rejected` must contain no selected roles;
- `ambiguous` may retain or change roles but remains explicitly marked.

Existing differing reviewed annotations are not overwritten unless requested explicitly. Publication
copies all reviewed annotations and the corpus manifest to `data/evaluation/corpora`, changing only
the lifecycle status to `published`. Markdown review files and licensed context remain local.

## Consequences

The review surface is readable and can be handled with ordinary text tooling. The canonical YAML
annotations remain content-safe, reproducible, and suitable for Git. Proposal quality can later be
measured because import never replaces proposal evidence with the reviewed result. Review documents
are deliberately coupled to one proposal run and become stale when clause content hashes change.
