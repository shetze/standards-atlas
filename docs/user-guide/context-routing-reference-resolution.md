# Canonical context-routing reference resolution

## Responsibilities and failure mechanism

`ReferenceTarget.clause_id` is an address, not a model confidence signal. Existence of an ID in the
TOC does not establish that it is the target named in a source citation. The earlier routing prompt
permitted model-supplied IDs and the source extractor omitted many annex/bare-number/list mentions.
Consequently a provider could reuse a source/ancestor ID even while quoting a different target.
An ID-authoritative display normalizer then concealed the contradiction by overwriting the text.
Checking only the subsequently canonicalized text cannot recover that original citation.

The corrected flow separates source evidence, document coordinates and semantic routing roles:

1. Content enrichment preserves syntactic mentions and offsets. Taxonomy refreshes the generated
   reference baseline from available source text using the same deterministic coordinate index.
2. Context enrichment supplies current resolved mentions to the provider. The default v2 prompt
   preserves literal citation text, assigns the semantic role and returns null target IDs/titles.
3. The deterministic resolver validates local references and explicit scope coordinates before
   canonical persistence, during generated-result reuse, and as an export safeguard. It never
   substitutes a prefix/ancestor for a more specific coordinate.

Legacy prompt v1 remains readable, but the shipped context configuration and default now use v2.
The resolver revision and complete prompt/schema inputs participate in the input fingerprint, so a
v1 result is not mislabeled as a v2 generation. A normal enrichment workflow may run the new model
prompt; the explicit repair command below is entirely model-free.

## Resolution boundaries

Short references stay in the source standard, part and edition. Qualified coordinates must match
the specified namespace. Clause and table prefixes are not interchangeable. A local citation must
resolve uniquely; a supplied ID does not disambiguate duplicate coordinates.

`7.2.2.1 to 7.2.2.9` expands to nine individually addressed reference edges when all nine sibling
coordinates exist uniquely. `Annexes A and B` expands to two edges. Expansion preserves the role
and original evidence on each edge. Ranges are bounded to 201 same-level numeric coordinates;
missing or ambiguous members retain the whole group as unresolved rather than publishing only
endpoints. Other range syntax remains unresolved, not guessed.

Explicit scope coordinates obey the same exact-address rule. Deterministic `structural_context.scopes`
can establish the target IDs when a provider repeated the wrong display label. Without that proof,
a provider ID alone cannot override a contradictory explicit coordinate. References inside scope
conditions, exclusions or qualifications are not automatically the governed region.

Already canonicalized bad targets can be recovered from routing evidence only when the evidence
is a verbatim substring of the clause's source text after whitespace normalization. A single
unambiguous citation/group can correct the target; a target already supported by one of several
mentions is retained. Multiple unrelated candidates without a supported target require review.
Unverified conflicting evidence never supplies a replacement citation or verified local ID. The
resolver does not infer a target from `role`, target title, hash or source ID.

Explicitly external targets are preserved for cross-document resolution; this local repair is not
an audit of their IDs. Source-free public projection data cannot supply missing private evidence.
The resolver intentionally leaves semantic role classification unchanged.

## Repair existing canonical documents

Inspect first:

```bash
uv run standards-atlas document repair-context-routing IEC61508-3 \
  --workspace .atlas/data \
  --report local/evaluation/context-routing/IEC61508-3-repair.json
```

Persist the same deterministic repair after inspecting diagnostics:

```bash
uv run standards-atlas document repair-context-routing IEC61508-3 \
  --workspace .atlas/data \
  --report local/evaluation/context-routing/IEC61508-3-repair.json \
  --write
```

The command loads and updates `.atlas/data/documents/IEC61508-3.json`, not only a companion. It
refreshes generated reference mentions/structural reference edges from available content, retains
subject/semantic enrichments and original routing generation provenance, and skips protected
routing. The separate report records the deterministic resolver and before/after object hashes.

Writing saves the exact original file bytes as
`IEC61508-3.json.before-routing-repair-<digest-prefix>.bak`. Backups are outside the repository's
`*.json` inventory and are never overwritten with different content. A repeated repair makes no
further document change and creates no additional backup. The report must be outside the canonical
documents directory. Missing documents are errors; the command never starts an inference server.

Review the report's `requires_review`, `protected_clauses` and
`routing_clauses_without_source_text` counts, as well as individual `diagnostics`:

| Status/reason | Interpretation |
| --- | --- |
| `resolved` / `exact_document_coordinates` | Exact citation resolved uniquely, including complete groups. |
| `resolved` / `recovered_from_verbatim_source_evidence` | A damaged target was recovered from preserved, source-verified evidence. |
| `resolved` / `deterministic_scope_edge` | A structural scope edge supplied the target behind a stale label. |
| `partially_resolved`, `unresolved`, `ambiguous` | No complete unique group or an unresolved evidence conflict; no guessed local ID. |
| `unverified` | Conflicting evidence could not be grounded in source content; target ID removed, text retained. |
| `protected` | Reviewed/unattributed protected routing was not rewritten. |

No schema migration is needed: canonical schema 9, companion schema 1.2 and evidence schema 1.0
remain unchanged. Re-export generated routing after canonical repair:

```bash
uv run standards-atlas atlasdata export-enrichments \
  --manifest manifests/standards.yaml \
  --workspace .atlas/data \
  --document IEC61508-3 \
  --dimension context_routing \
  --write
```

Unselected dimensions are preserved. Neither existing canonical documents nor private evidence
should be deleted. If both literal citation and usable evidence/source are lost, review or restore
source-backed routing instead of treating the incorrect canonical self-link as proof.
