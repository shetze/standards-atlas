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
