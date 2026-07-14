# ADR 0015: Use full-document Markdown for alignment review

## Status

Accepted

## Context

Automatic clause alignment is useful but not sufficiently reliable for creating canonical clause content without human review. The problem-oriented review document introduced in Slice 4.2 presents isolated missing or uncertain alignments. In practice, many missing alignments have no useful local context, and incorrectly detected alignments are difficult to remove or move.

Reviewers need to work in the natural order and full context of the standard. At the same time, Markdown must not become the canonical document representation and protected standard content must remain below `.atlas`.

## Decision

Standards Atlas exports the complete `NormalizedExtractedDocument` as an anchored Markdown review document.

Each normalized item is preceded by a stable HTML comment:

```markdown
<!-- atlas:item=normalized:#/texts/320 -->
```

An alignment point is represented by one Markdown hash and one terminating dash:

```markdown
# 1.1 - This document specifies ...
# 3.1.15 availability -
```

The hash marks the start of a clause. The dash separates the clause reference and optional observed heading from content. The canonical hierarchy remains defined by AtlasData, so reviewers normally use exactly one hash. Multiple hashes are interpreted only as an explicit manual heading-level decision.

Removing all leading hashes disables an automatically generated alignment marker. Adding a hash creates a manual alignment marker. The generated and edited reviews are stored separately:

```text
.atlas/alignments/<document>/review.generated.md
.atlas/alignments/<document>/review.edited.md
```

The generated file is reproducible. The editable file is never overwritten unless explicitly reset.

Both files are parsed using their stable item anchors. Structural differences are translated into the existing `overrides.yaml` format:

- added marker → `assign`
- removed marker → `ignore_candidate`
- changed observed heading → `set_observed_heading`
- changed hash count → `set_heading_level`

Changes to protected document content outside alignment markers are rejected.

## Consequences

Reviewers can correct missing, incorrect and misplaced alignments directly in complete document context without handling technical IDs manually.

Markdown remains a temporary review representation. The canonical inputs and outputs remain `NormalizedExtractedDocument`, `AlignmentOverrideDocument` and reviewed `AlignmentResult`.

The item-anchor comments are part of the machine-readable review contract and must not be removed or changed.

The reviewed Markdown can be regenerated after changes to normalization or automatic alignment, but existing edits require an explicit reset or manual reconciliation.
