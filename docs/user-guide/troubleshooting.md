# Troubleshooting

## Establish the failing stage

```bash
uv run standards-atlas catalog validate catalogs/standards.yaml
uv run standards-atlas workflow plan --catalog catalogs/standards.yaml --family FAMILY
uv run standards-atlas docling inspect DOCUMENT
uv run standards-atlas normalize inspect DOCUMENT
uv run standards-atlas references inspect DOCUMENT
uv run standards-atlas align inspect DOCUMENT --show-conflicts
```

## Persisted extraction is incomplete

Use `--overwrite` to regenerate derived artifacts. Preserve valid extraction with `--keep docling`; use `--force` only when Docling output must also be regenerated.

## Workflow pauses at a review gate

This is expected. Complete the indicated alignment or AtlasData review and rerun with `--continue-after-review`. The flag does not bypass missing review data.

## LLM stop says stopped, but status is running

Check whether a different RamaLama process owns the configured endpoint, whether runtime state refers to a container rather than the client process, and whether the configured stop timeout expired. Use the project workaround only as a diagnostic; then verify again with `llm status`.

## Model response ends with `finish_reason=length`

Increase the configured output budget where appropriate, simplify the prompt contract, and verify that reasoning text is not consuming the JSON response budget. Treat truncated JSON as a failed prediction, not a partial success.

## Qualification reliability validation fails

Success rates are fractions, not counts. A value such as `10.0` for ten successful predictions is invalid; the rate must be `1.0`, with `10` retained as a separate count.

## Doorstop export exits with code 2

Exit code `2` generally indicates CLI usage or parameter validation, while an expected domain failure should use the documented command failure code. Inspect the command arguments and the underlying error before changing tests.

## Missing Markdown links for clause references

The target clause must be present in the exported set and resolvable to a known Markdown path. External references and unavailable clauses remain plain references.
