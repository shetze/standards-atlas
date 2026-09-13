# ADR 0015: MCP Evaluation Boundary

## Status
Accepted

## Goal alignment
MCP is an **interface to Standards Atlas capabilities**, not the purpose of the system and not an alternate knowledge model. Evaluation access is one bounded use case. As knowledge-serving capabilities mature, MCP may also expose controlled retrieval and query services over the Engineering Knowledge Base through application-layer contracts while preserving provenance and authorization boundaries.

## Context
External agents and tools need controlled access to evaluation and review capabilities without bypassing application boundaries or exposing unrestricted project state.

## Decision
Evaluation capabilities may be exposed through a restricted MCP adapter.

- MCP is an adapter over application services, not a domain dependency.
- Deployments use streamable HTTP with authentication, request/result limits, audit logging, and explicit tool registration.
- Read-only/evaluation operations are the default; mutation/review actions require explicit narrow contracts.
- External clients such as Codex operate with restricted MCP capabilities rather than direct repository/application internals.
- Content-safety and source-disclosure rules apply to MCP responses just as to local reports.

## Consequences
Automation clients can participate in evaluation workflows while preserving application boundaries, auditability, and deployment controls.

## Source-bound human review preparation

The optional review adapter reads a trusted local package registry and accepts closed,
source-bound model selection/recommendation contracts. Review data and logic live in the
application layer shared by CLI, MCP and the planned Web workbench. MCP cannot manufacture
human decisions, materialize new membership, publish reference suites or activate policies.
Local selection materialization creates a new package while preserving all known Development,
fixed Holdout membership and existing human decisions; its queue and provenance are hash-bound.

Historical results inform Development selection but never select a favorable Holdout or become
new confirmations. Holdout assistance is separately opt-in with historical answers withheld.
A review-only client allowlist avoids generic reader bypasses; this boundary does not apply
to unrestricted filesystem/shell access. Declared model identities and HTTP request logging do
not establish authenticated reviewer identity or a complete historical source-exposure ledger.
