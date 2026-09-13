# Review package Slice 1 — validation

Date: 2026-09-13

Base snapshot: `standards-atlas-current-202609131826.zip`.

## Delivered scope

Versioned source-bound review package, review profile and append-only proposal/decision
state; local human CLI; deterministic Development/Holdout construction; validated,
atomic pair publication in the existing semantic-reference suite format; preserved
review evidence in qualification campaign artifacts. No Web or MCP endpoint and no
intelligent Codex selection are introduced by this slice. No production annotation,
qualification outcome or release approval is fabricated by the tests.

## Executed checks

Environment: Python 3.13.5, pytest 9.0.2, Pydantic 2.13.4.

| Check | Result |
| --- | --- |
| `python -m pytest -q tests/architecture tests/unit --disable-warnings` | 2,503 passed; 3 skipped; 133 warnings |
| `python -m pytest -q tests/integration tests/contract tests/property --disable-warnings -ra` | 172 passed; 4 skipped |
| Final targeted rerun: review-package tests, unit schema tests and architecture tests | 100 passed; 52 warnings |
| Fresh original snapshot + changes ZIP: review-package test module | 66 passed; 52 warnings |
| Python bytecode compilation of new application package and CLI module | Passed |
| `git diff --check` | Passed |
| ZIP member inventory, CRC and byte-for-byte comparison with changed files | Passed |

The targeted and fresh-snapshot runs overlap with the broad suite; these numbers must
not be summed as distinct tests. The final targeted and fresh-snapshot runs include
the directory-fsync durability refinement made after the broad run started.

Integration skips are for the unavailable optional Docling and Hypothesis dependencies
and two tests requiring the private qualification-run-074 archive. Schema deprecation
warnings include legacy 1.0 campaign/manifest reads after adding artifact 1.1 support;
both legacy and bound-campaign paths remain covered.

Ruff was not installed in this execution environment and could not be installed due
to network restrictions. No successful Ruff run is claimed. Syntax, changed-Python
line lengths, import usage and whitespace were checked separately. No production LLM
run was executed, and the private production run/Golden inputs were not present in
the supplied snapshot.

## Regression coverage

The 66 new test cases cover full source text and source-only structure; stable identities;
Development preservation; seeded Holdout exclusions including Unicode/whitespace-equivalent
text; insufficient populations; explicit false/null/empty predicates; typed schema validation;
revision-bound confirmations; manual corrections, deferral and rejection; retained history;
new proposals not altering accepted human decisions; coverage and cross-attribute conflicts;
source, context and rule drift; evidence quotes and Unicode positions; stale writers and
symlinks; immutable/idempotent publication; simulated atomic-write failure; verified suite
pairs; frozen campaign evidence, missing bindings and artifact versions; and local CLI use.

## Assurance boundaries

Hashes establish reproducible binding, not authenticated reviewer identity or protection
against an actor able to rewrite all local files. Holdout selection is independent of
candidate outputs in this slice, but unrecorded prior development exposure, paraphrases
and translations require human assessment. The publication declaration records that
assessment; it cannot mathematically prove independence. Explicitly truncated source
inputs are rejected, but silent omissions by an upstream extractor remain outside this
check. The default coverage profile is a technical completeness floor, not evidence of
statistical sufficiency.
