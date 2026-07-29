# ADR 0052: Build Golden Corpus proposals from model consensus

## Status

Accepted

## Context

The existing semantic evaluation compared model proposals with a Golden Corpus that had itself been derived from one model proposal and then reviewed by a human. This creates an anchoring risk and makes the Golden Corpus unsuitable as the sole authority for selecting a model or prompt.

A separate semantic-evaluation workflow manifest was introduced temporarily. It duplicated the qualification-matrix manifest and split one evaluation lifecycle across two orchestration contracts.

The structural dimensions of a clause are now classified independently. The semantic evaluation considered here therefore targets statement functions derived from the clause text rather than document structure.

## Decision

The qualification-matrix manifest is the single orchestration contract for the multi-model evaluation stage. Corpus construction remains an explicit preceding command because its selection strategy and seed define the population being evaluated.

The matrix may import existing reviewed annotations before execution. These annotations remain useful as diagnostic evidence, but they do not determine the new Golden Corpus proposal.

After all configured models have been executed, consensus is calculated in two steps:

1. repeated runs are aggregated into one stable vote per model;
2. the model votes are compared for each clause.

This prevents repetitions, prompts, or retries from giving one model more weight than another. Consensus uses the configured text-focused prompt and only statement-function predictions. Structural classifications are excluded.

The result is divided into unanimous, strong-consensus, majority-consensus, disputed, and insufficient-evidence categories. Unanimous and strong-consensus cases form the high-confidence part of the proposal. The remaining cases are exported into a focused HITL review queue.

## Consequences

- `examples/evaluation/qualification-matrix.yaml` owns review import and consensus configuration.
- The separate `workflow evaluation` manifest and commands are removed.
- Qualification metrics against the existing corpus remain available as diagnostics.
- A failed qualification threshold does not prevent generation of the consensus proposal.
- Every model contributes at most one vote per clause after repetition aggregation.
- HITL review is concentrated on detected disagreement and uncertainty rather than all clauses.
