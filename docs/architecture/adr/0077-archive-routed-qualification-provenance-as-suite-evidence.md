# ADR 0077: Archive routed qualification provenance as suite evidence

## Status

Accepted.

## Context

ADR 0076 introduced `routed-qualification` as an orchestration layer across five independently
qualified semantic tasks. The existing immutable `qualification-run-NNN.zip` archive remained
focused on one matrix run. That was sufficient for model/task analysis, but not for evaluating
the deterministic router itself because the archive did not contain the exact routing contract,
routing manifest, or per-document `routing.json` artifacts used to admit or skip clauses.

A routed suite also produced five independent qualification archives without a durable common
run identity. Later analysis therefore could not prove that five task runs belonged to the same
workflow invocation or reconstruct routing reduction and disposition counts from the immutable
evidence alone.

## Decision

Every routing-enabled qualification run archives the routing manifest, the exact versioned
routing-contract resource, and every persisted `routing.json` artifact referenced by documents
in its corpus. These members participate in the normal `archive-manifest.json` SHA-256 manifest.
`qualification-run-metadata.json` records routing contract identity/version, the task admission
threshold, routing aggregates, and an optional `suite_run_id`.

`routed-qualification` allocates one sequential `qualification-suite-run-NNN` identifier before
executing its five matrices and passes that identifier to every task run. The suite manifest is
embedded in every correlated qualification archive.

After all five matrices complete, the workflow writes `qualification-suite-run-NNN.zip`. The
suite archive contains immutable snapshots of the suite manifest and routing manifest plus a
suite metadata document. That metadata references all five `qualification-run-NNN.zip` files by
archive ID and SHA-256 and records task-level routing aggregates, including admitted/skipped
counts and the distribution of required/preferred/optional/skip/unrouted decisions.

The suite archive references rather than duplicates the complete task archives. The task archives
remain independently useful for model qualification, while the suite archive establishes their
common provenance and router-level analysis context.

## Consequences

A routed qualification result can be analyzed without access to the original `.atlas` workspace.
Analysts can distinguish router behavior from LLM task quality, reproduce exactly which clauses
were admitted, and verify that routing evidence has not changed after the run.

The archive schema for individual qualification runs advances to 1.3. Existing archives remain
historical immutable evidence and do not require migration.
