# ADR 0015: MCP Evaluation Boundary

## Status
Accepted

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
