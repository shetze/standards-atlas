# Methods and Techniques Index

Standards Atlas treats named methods and techniques as reusable knowledge objects rather
than statement functions. During normalization it creates a conservative, provenance-
preserving candidate index from explicitly signalled lists and tables, especially annexes
headed with terms such as “methods” or “techniques”.

Each normalized document contains `method_technique_candidates`. The normalization
repository also writes a separate deterministic artifact:

```text
.atlas/data/normalized/<document-key>/methods-and-techniques.json
```

A candidate records its display name, normalized name, category (`method`, `technique`, or
`method_or_technique`), source item IDs, extraction context, rule, and confidence. This is a
candidate list, not yet a canonical ontology: synonym resolution and cross-standard
consolidation are deliberately deferred.

The separate artifact is intended as the future input for MCP tools such as `list_methods`,
`find_method`, and for later assessment of whether a method can be implemented as an agent
skill.
