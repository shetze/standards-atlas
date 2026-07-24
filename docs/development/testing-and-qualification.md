# Testing and qualification

The test strategy combines fast unit tests with contract, integration, and golden-corpus regression checks.

Unit tests cover parsers, value objects, normalization rules, workflow planning, lifecycle transitions, composition, and export mapping. Integration tests exercise filesystem repositories and adapter boundaries. Golden corpus tests detect regressions in difficult pages, heading structures, lists, tables, captions, annexes, and multi-part documents.

Before committing:

```bash
uv run ruff check .
uv run pytest
```

A transformation change should include fixtures that demonstrate both the intended correction and preservation of unrelated source evidence. Never update golden outputs solely to make a test pass; inspect the semantic diff and document intentional contract changes.
