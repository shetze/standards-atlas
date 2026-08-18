# Tutorials

Tutorials provide complete learning paths through representative workflows. Replace example keys and paths with entries from your catalog.

## Available tutorials

### Process one standard family

```bash
uv run standards-atlas catalog validate manifests/standards.yaml
uv run standards-atlas workflow plan \\
  --manifests manifests/standards.yaml \\
  --family EN50716
uv run standards-atlas workflow run \\
  --manifests manifests/standards.yaml \\
  --family EN50716
```

Complete any reported review gate and continue with `--continue-after-review`. Export the result:

```bash
uv run standards-atlas document export markdown EN50716 \\
  --output local/markdown/EN50716 \\
  --replace
```

### Rebuild normalization without re-running Docling

```bash
uv run standards-atlas workflow run \\
  --manifests manifests/standards.yaml \\
  --family EN50716 \\
  --overwrite \\
  --keep docling
```

Use this after normalization, reference-resolution, or construction changes when extraction evidence remains valid.

### Run a small qualification probe

```bash
uv run standards-atlas llm preload-qualification-models \\
  --manifest manifests/multidimensional-semantic-qualification-v3-semantic-profile-v1.yaml

uv run standards-atlas evaluation qualification-matrix \\
  --manifest manifests/multidimensional-semantic-qualification-v3-semantic-profile-v1.yaml \\
  --output local/evaluation/qualification \\
  --limit 10 \\
  --overwrite
```

Inspect failures and metrics before starting the full matrix.

### Expose clauses through MCP

```bash
export STANDARDS_ATLAS_MCP_TOKEN='<token>'
uv run standards-atlas mcp start
uv run standards-atlas mcp status
uv run standards-atlas mcp probe \\
  --url http://127.0.0.1:8765/mcp/
```

Stop the managed server after use:

```bash
uv run standards-atlas mcp stop
```

## Planned tutorial backlog

The following tutorials are planned documentation work, not product roadmap commitments:

1. Develop a structural taxonomy for a new document class.
2. Build a reusable Knowledge Domain from a PDF source.
3. Discover and review relationships across Knowledge Domains.
4. Qualify an extraction and classification pipeline.

The first topic should cover representative-document analysis, initial taxonomy design, golden-corpus construction, multi-model evaluation, disagreement review, model evolution, and iteration until the taxonomy is stable enough for its intended use.
