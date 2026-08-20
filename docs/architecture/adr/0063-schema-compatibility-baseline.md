# ADR 0063: Establish a clean schema compatibility baseline

- Status: Accepted
- Date: 2026-08-20

## Context

Standards Atlas persists and loads several JSON/YAML contracts. Historical fallback
logic had begun to accumulate without a common lifetime policy. The project is still
pre-1.0 and can make destructive changes before promising bounded compatibility.

## Decision

Establish one current schema baseline per persistent contract before introducing
multi-version reader support. During this cleanup phase readers accept only the
current baseline. In particular, Engineering Document schema 2 and unversioned
Engineering Documents are no longer accepted.

Schema versions describe serialization only. Domain/resource versions such as task,
taxonomy, prompt, corpus, and dataset versions remain independent.

`.atlas/cache` and `.atlas/work` formats receive no backward-compatibility guarantee.
Durable `.atlas/data`, versioned resources, manifests, and machine-consumed review
contracts are candidates for the future bounded reader policy.

No generic migration framework is introduced. Generated old artifacts can be
regenerated; future old-schema support will deserialize directly into the current
domain model.

## Consequences

The next schema-policy slice starts from explicit current baselines instead of
preserving accidental historical behavior. When bounded compatibility is enabled,
old readers can be added deliberately and removed after their support window without
requiring a migration chain.
