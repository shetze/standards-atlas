# ADR 0050: Qualify model/prompt combinations as a versioned matrix

## Status

Accepted

## Context

Semantic-role quality depends on both the model and the prompt. A single run is not sufficient because local inference can vary and because quality alone does not capture latency or resource demand. Qualification must also be reproducible and usable as a CI regression gate.

## Decision

Standards Atlas stores a versioned qualification-matrix manifest containing:

- a model shortlist with provider and declared resource profile;
- exactly four versioned prompt candidates;
- at least two repetitions per model/prompt combination;
- references to Slice 5.4.5 qualification reports;
- measured duration and peak-memory observations;
- absolute and baseline-relative regression thresholds.

Qualification aggregates Gold, Silver and Structure Agreement across repetitions, reports mean and minimum quality, stability, coverage, duration and memory, and identifies the Pareto front. Missing repetitions are qualification failures rather than silently reduced samples. The CLI exits with status 1 when any candidate violates the matrix contract or thresholds.

## Consequences

Model selection becomes an auditable engineering decision rather than an informal benchmark. Reports can be regenerated without access to protected clause text because they consume qualification summaries. Runtime and memory must be measured by the execution workflow and recorded with each observation.
