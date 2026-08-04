# Tutorials

Tutorials provide complete paths through common tasks. Replace example keys and paths with entries from your catalog.

## 1. Process one standard family

```bash
uv run standards-atlas catalog validate catalogs/standards.yaml
uv run standards-atlas workflow plan --catalog catalogs/standards.yaml --family EN50716
uv run standards-atlas workflow run --catalog catalogs/standards.yaml --family EN50716
```

Complete any reported review gate and continue with `--continue-after-review`. Export the result:

```bash
uv run standards-atlas document export markdown EN50716   --output local/markdown/EN50716 --replace
```

## 2. Rebuild normalization without re-running Docling

```bash
uv run standards-atlas workflow run   --catalog catalogs/standards.yaml   --family EN50716   --overwrite   --keep docling
```

Use this after normalization, reference-resolution or construction changes when extraction evidence remains valid.

## 3. Run a small qualification probe

```bash
uv run standards-atlas llm preload-qualification-models   --manifest local/evaluation/qualification/semantic-role-v1.yaml

uv run standards-atlas evaluation qualification-matrix   --manifest local/evaluation/qualification/semantic-role-v1.yaml   --output local/evaluation/qualification   --limit 10   --overwrite
```

Inspect failures and metrics before starting the full matrix.

## 4. Expose clauses through MCP

```bash
export STANDARDS_ATLAS_MCP_TOKEN='<token>'
uv run standards-atlas mcp start
uv run standards-atlas mcp status
uv run standards-atlas mcp probe   --url http://127.0.0.1:8765/mcp/
```

Stop the managed server after use:

```bash
uv run standards-atlas mcp stop
```
