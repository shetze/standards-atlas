# ADR 0056: Preserve cascade resolution provenance

## Status

Accepted

## Context

The semantic qualification cascade resolves statement function, knowledge kind,
applicability, and responsibility independently. Qualification result analysis exposed
three observability and consistency problems:

- a resolved `none` knowledge-kind decision was persisted with positive-label confidence
  instead of decision confidence;
- a statement-function majority could be frozen by the cascade even when the downstream
  review policy would deterministically reject the same confidence;
- structural-prior conflicts did not distinguish a conflict observed during escalation
  from one that remained unresolved in the final result.

The end-of-run artifacts also did not retain enough stage-level information to explain why
an individual clause entered or left a cascade stage without reconstructing execution from
model votes.

## Decision

1. Persist all resolved dimensions with their decision confidence. A unanimous negative
   (`none`) decision therefore has confidence `1.0`.
2. Keep the manifest's configured cascade policy unchanged, but derive an effective
   execution policy whose statement-function confidence floor is at least the review
   policy's majority auto-acceptance threshold.
3. Record structural applicability conflicts separately as `observed` and `unresolved`.
   Only unresolved conflicts force final HITL review; resolved conflicts remain audit
   evidence.
4. Persist `cascade-provenance.json` with stage entry and exit clause IDs and reasons,
   configured and effective policies, and per-dimension resolution counts before and after
   every stage.
5. Persist `qualification-analysis-metrics.json` with stable aggregate metrics for clause
   status, semantic dimensions, participation, review reasons, resolution sources,
   structural conflicts, and cascade stages.
6. At the end of a consensus-enabled qualification matrix, create a versioned analysis ZIP
   containing the manifest snapshot, qualification and consensus reports, HITL material,
   metrics, provenance, cascade JSON reports, and an archive manifest with SHA-256 hashes.

## Consequences

- Cascade finalization and automatic review acceptance no longer contradict one another at
  the confidence boundary.
- Qualification results can be analyzed without inferring stage behavior from final votes.
- Historical structural conflicts remain visible without generating stale HITL work.
- Analysis archives are self-describing and tied to the Standards Atlas and archive-schema
  versions.
- A fresh `--overwrite` run remains necessary when execution behavior itself has changed;
  provenance makes reused or unexpectedly escalated clauses visible rather than silently
  masking them.
