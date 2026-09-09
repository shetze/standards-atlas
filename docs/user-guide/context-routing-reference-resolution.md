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
2. Context enrichment supplies current resolved mentions to the provider. The default v3 prompt
   preserves literal citation text, assigns the semantic role and returns null target IDs/titles.
3. The deterministic resolver validates local references and explicit scope coordinates before
   canonical persistence, during generated-result reuse, and as an export safeguard. It never
   substitutes a prefix/ancestor for a more specific coordinate.

Explicit legacy prompt selections v1 and v2 remain available. The shipped context configuration
and default now use v3.
The resolver revision and complete prompt/schema inputs participate in the input fingerprint, so a
v1/v2 result is not mislabeled as a v3 generation. A normal enrichment workflow may run the new model
prompt; the explicit repair command below is entirely model-free.

## Resolution boundaries

Short references stay in the source standard, part and edition. Qualified coordinates must match
the specified namespace. Clause, table and figure prefixes are not interchangeable. `Figure 2` never resolves to
`Clause 2` or `Table 2`. Mixed lists carry forward the most recent explicit label:
`Figure 2, Table 1 and 3` denotes Figure 2, Table 1 and Table 3. A local citation must
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

## Scope extraction is not canonical ScopeReach serialization

The v2 contract asked the provider to populate all of `kind`, `document_key`, `part`, `clause_id`
and `reference`. Canonical document/part reaches prohibit clause references. Local validation
therefore detected contradictory answers but could not translate a meaningful citation into the
correct address; merely deleting the reference would lose information or widen the scope.

V3 uses a uniform extraction shape, independent of the canonical address constraints:

```json
{"reference": "IEC 61508-0:2005 4.5", "include_descendants": false}
```

The application resolves the coordinate to a clause reach (or a subtree when descendants are
explicitly included). The transport has no `kind`, `part`, `document_key` or `clause_id` fields
inside scope reaches, and requires no conditional null-field grammar. The reference-routing
contract and its semantic roles remain unchanged.

```json
{"reference": "Parts 1, 2, 3 and 4 of IEC 61508", "include_descendants": true}
```

This target expands atomically to four part reaches, each with its catalogued physical document
key and its own `part`. It does not become four local clauses, one source-document scope, or
merely the two endpoints. The source edition is not assumed to be the edition of all other parts.
Missing or ambiguous physical documents cause a diagnostic error; specify the cited edition and
make its structure available. Clause groups retain the established unresolved-whole-group behavior
when any member is unavailable. No synthetic target ID is fabricated.

An omitted `Parts` label (`1, 2, 3 and 4 of IEC 61508`) is accepted only when a verbatim,
source-verified evidence excerpt explicitly identifies that same list as parts. Otherwise it is
ambiguous and must not be guessed. Citations inside conditions are not substituted for an explicit
scope target. Whole-document targets use `this document` or an exact catalogued document reference;
unknown whole-document targets cannot fall back to the local document.

These examples describe representations, not a finding that those source clauses actually declare
such scopes. The provider still interprets whether the clause establishes a scope and whether it
includes descendants. Schema/coordinate validation does not prove semantic extraction accuracy.

The repository composition supplies the available physical-document catalogue. Catalogue identity
and target structure participate in input/cache fingerprints; unrelated generated attributes do
not. Canonical schema 9 and public companion schema 1.2 are unchanged. Nothing is deleted from
existing documents or companions and confirmed routing remains protected.

### Figure/table citations and unresolved identities

The extractor and address index both recognize labelled figures (including `Fig.`), tables,
complete mixed lists and bounded ranges. Prefix- and suffix-qualified scope citations are accepted,
for example `IEC 61508-2 Figure 2 and Table 1` and `Figure 2 and Table 1 of IEC 61508-2`.
They resolve against the cited physical document, not the source part or equal-numbered clauses.
Existing labelled figure entries can be addressed without introducing a new canonical clause type.

A meaningful citation is not invalid just because its objects have no standalone TOC entries.
This now follows the existing unresolved-clause policy: if every member resolves uniquely, expand
all members; otherwise retain the entire original group with `clause_id: null`. Never publish only
the resolvable subset, invent an ID, discard the figure/table labels, or widen to a whole document.
The reach retains the supplied descendant intent and the existing clause/subtree representation
for clause-like addressed items. No document/enrichment schema migration is needed.

For a single-item scope whose table/figure identities are unavailable, the canonical address is:

```yaml
kind: clause
document_key: IEC61508-2
clause_id: null
reference: IEC 61508-2 Figure 2 and Table 1
```

`clause_id: null` is not a verified link. It preserves a citation for later resolution/review.
The CLI separately reports `Scope targets unresolved` and `Reference targets unresolved`,
and writes complete retained target groups (including private evidence) to:

```text
.atlas/data/evaluation/context-routing/IEC61508-0-unresolved-targets.json
```

The count is of unresolved **reach records/groups**, not necessarily individual list members.
It includes reused/protected values, so reuse cannot hide missing identities. The report is cleared
when neither scope nor reference targets remain unresolved. It is private diagnostic output, not additional WIP data in companions.
`ok` means a valid routing extraction, not complete target resolution. `--fail-on-failure` still
blocks invalid schema/domain output; valid unresolved citations do not trigger a futile corrective
LLM request. Missing/ambiguous whole-document or part identities and malformed citations still fail.

A figure/table citation does **not** by itself establish scope. Informational mentions belong under
`reference_routings`; genuine declarations can govern figures/tables. The v3 prompt explains both
cases. There is no deterministic rule moving every object citation out of scopes or inventing a
role. The production log alone does not reveal the source evidence needed to judge that distinction.
An unresolved address and an incorrect semantic interpretation are separate questions.

The resolver revision and updated prompt invalidate stale generated-input fingerprints. The
standalone command below remains sufficient; there is no need to repeat Docling or normalization.

### Verify the context stage without repeating normalization

From the project root, after applying the patch including `cfg/context-enrichment.yaml`:

```bash
uv run standards-atlas document enrich-context IEC61508-0 \
  --workspace .atlas/data \
  --fresh \
  --fail-on-failure
```

The startup message must name `context-routing-enrichment/context-routing-v3`. This command needs
existing canonical content/taxonomy and the dedicated local context model. It does not rerun
Docling, normalization, qualification or publication. The normal `workflow run --task enrichments`
command also uses v3 through the shipped configuration. Repeating it with `--overwrite --fresh`
intentionally rebuilds derived steps and repeats generated context inference.

Schema and canonical validation remain strict. One corrective retry receives both the precise
error and the rejected JSON as diagnostic data (not as source evidence). After persistent failure,
`--fail-on-failure` still stops the standalone command after writing diagnostics. The end-to-end
workflow defaults to baseline collection and continues after recorded clause failures; use
`--fail-on-context-failure` to request the strict workflow policy. Technical failures remain fatal.
The CLI writes private diagnostics before returning:

```text
.atlas/data/evaluation/context-routing/IEC61508-0-failures.json
```

The report identifies each failed clause, generator, input fingerprint and both rejected answers
where available. It can contain licensed text, so it is never written to `data/enrichments`.
Successful retry removes the stale per-document failure report. No failed candidate is converted
into a fabricated successful empty routing value.

## Source-verified informational routing

Reference syntax is determined **after separating the standard designation from its coordinates**.
`Annex A of IEC 61508-5` is a single target; the hyphen in `61508-5` is not a range operator.
`Clauses 6 and 8` is a list with no range bounds. `Clauses 7.2 to 7.5` retains the true bounds.
`Clause 7 of IEC 61508-2 and IEC 61508-3 respectively` produces two mentions with the same complete
source span, one per named document. No synthetic quotation is substituted for the shared text.
The extractor provenance is `reference-mention-extractor/v3`; the mention schema remains 1.0.

A readable citation and valid target ID do not prove a scope relation. The
`source-grounded-information-v1` policy recognizes a bounded set of **English informational
navigation patterns** (reading recommendations, further-information and FAQ pointers). It verifies
all supporting quotations against the actual clause, allowing whitespace differences only. A
colon-introduced reading list belongs to that passage; the next prose paragraph does not.

A proven informational-only scope is replaced with reference edges extracted from that source
passage, including any omitted shared-coordinate target. Bare informational references use `other`
unless their evidence explicitly supports a more specific existing role. An unsupported
`provides_applicability` role on a FAQ pointer is therefore removed; genuine exception/procedure/
applicability descriptions retain their supported roles. Source content and original generated
provenance are preserved; before/after corrections are recorded separately, not silently discarded.

This policy is not a universal semantic classifier. It does not infer scope from `if`, the target
being normative, or a nearby interpretation paragraph. It never removes a scope merely because
its modifier arrays are empty or its target is a figure/table. Missing, unverified or unrecognized
evidence is not sufficient for automatic reclassification. Mixed informational/governing material
is retained for review by offline repair; during new inference it requires a corrected governing
quotation through the existing corrective retry and failure gate. Confirmed/protected routing and
protected baseline fields remain unchanged.

The check runs **before** the v3 transport is resolved into canonical scope addresses. Thus an
informational citation to a document absent from the catalogue remains an unresolved reference,
not a scope-resolution error. Exact physical-document targets are resolved from the catalogue;
no target ID, edition or parent scope is invented. Complete groups remain literal when any member
is unavailable. Reference addressing is separate from this limited semantic safeguard.

Standalone `document enrich-context` also refreshes unconfirmed baseline reference mentions and
structural reference edges. Prompt text, extractor revision and policy revision participate in
LLM-cache/reuse input identity, so old semantic output is not accepted as current solely because
the prompt is still named `context-routing-v3`.

### Repair an existing informational-scope error without inference

Preview (no changes to canonical files):

```bash
uv run standards-atlas document repair-context-routing IEC61508-0 \
  --workspace .atlas/data \
  --report local/evaluation/context-routing/IEC61508-0-repair.json
```

Add `--write` after inspecting the report. The command reads other physical documents from the
same workspace for exact cross-document targets. It never starts a model, reruns Docling, or
normalizes source content. It keeps an exact-byte backup before changing the canonical document.
The report includes `informational_scopes_reclassified`, `reference_roles_corrected`,
`unresolved_references_after`, `requires_review`, and complete before/after diagnostics. A second
identical repair is a no-op. Missing physical target documents leave literal unresolved references.

Then publish the corrected canonical state:

```bash
uv run standards-atlas atlasdata export-enrichments \
  --manifest manifests/standards.yaml \
  --workspace .atlas/data \
  --document IEC61508-0 \
  --dimension context_routing \
  --write
```

No deletion or schema migration is required. The public companion still contains no literal
source evidence or private repair diagnostics. Normal workflow context generation applies the
same safeguard; `--fresh` is not needed for the model-free repair above.

### Private semantic diagnostics

Context generation writes corrections and review details, when present, to:

```text
.atlas/data/evaluation/context-routing/<document-key>-routing-corrections.json
```

A no-change/reuse-only run keeps the previous correction audit. A later run with new corrections
replaces it with that run's details; it is a last-correction report, not an append-only history.
Offline repair retains its report plus the exact-byte canonical backup instead.

`<document-key>-unresolved-targets.json` now separates `unresolved_scope_targets` from
`unresolved_reference_targets`. Both include source evidence (and scope modifiers where relevant)
for private review. Their counts describe target records/groups, not individual objects. A known
information-list regression has zero scopes, eleven reference edges and three unresolved figure/
table groups with the matching catalogue. Those unresolved reference groups remain visible;
reclassifying them must not be reported as complete target resolution.

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
| `corrected` / `source_verified_information_not_scope` | Informational scope converted to source-backed references. |
| `corrected` / `source_verified_information_only` | Unsupported informational role or address corrected. |
| `requires_review` / `informational_evidence_in_mixed_or_unverified_context` | Offline repair preserved an uncertain scope instead of deleting it. |

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
