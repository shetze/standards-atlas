# Architecture-guided AI development

## Scope

This methodology describes how Standards Atlas is developed. It does not define the runtime architecture of the product itself.

## Core principle

Architecture and explicit domain contracts guide implementation. AI accelerates analysis and construction, but does not replace engineering authority or evidence-based acceptance.

## Human responsibilities

Human maintainers retain responsibility for:

- product vision and priorities;
- architecture and domain semantics;
- acceptance criteria and risk decisions;
- review of generated code, tests, and documentation;
- promotion of experimental results into maintained product behavior.

## AI responsibilities

AI may support:

- architecture and implementation proposals;
- code and documentation reviews;
- vertical-slice implementation;
- refactoring and migration work;
- test design and failure analysis;
- documentation and diagram maintenance.

AI output remains a proposal until it has passed the same review and verification expected of human-authored changes.

## Engineering principles

- Architecture before implementation.
- ADRs for durable decisions.
- Small vertical slices instead of disconnected layer work.
- Continuous refactoring toward explicit boundaries.
- Documentation and tests evolve with behavior.
- Context is curated rather than accumulated without structure.
- Human-in-the-loop review is retained where evidence or semantics are uncertain.

## Working sequence

The repository-level sequence is defined in the [development workflow](../development/development-workflow.md). Methodology documents explain why those steps matter; they do not duplicate command-level contribution instructions.
