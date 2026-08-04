# Development workflow

Standards Atlas is evolved through small, reviewable vertical slices. Each slice should leave architecture, implementation, tests, and documentation consistent.

## Workflow

1. Clarify the engineering goal and affected user workflow.
2. Review the relevant architecture documents and accepted ADRs.
3. Record a new ADR when the change introduces a durable architectural decision.
4. Implement one coherent vertical slice through domain, application, adapters, and CLI as required.
5. Add or update unit, integration, architecture, regression, and qualification tests.
6. Run the relevant quality checks.
7. Review dependency direction, persistence compatibility, lineage, and operational failure handling.
8. Update user, architecture, reference, and roadmap documentation where the observable contract changed.
9. Commit the slice as an independently understandable change.

## Required checks

Use the narrowest applicable checks while developing and the complete project checks before merging:

```bash
uv run ruff check .
uv run pytest
```

Additional qualification or integration commands belong to the affected subsystem and are documented in [Testing and qualification](testing-and-qualification.md).

## Architectural guardrails

- Domain objects do not depend on adapters or CLI concerns.
- Application services depend on ports, not concrete filesystem or runtime implementations.
- Persisted artifacts retain provenance and explicit version information.
- LLM output is treated as a proposal or derived artifact unless a documented workflow promotes it.
- Compatibility behavior must be explicit and covered by tests; it must not emerge accidentally from permissive parsing.

## AI-assisted work

AI may propose implementations, tests, reviews, refactorings, and documentation. Human maintainers remain responsible for architecture, domain semantics, acceptance, and release decisions. The broader method is described in [Architecture-guided AI development](../methodology/architecture-guided-ai-development.md).
