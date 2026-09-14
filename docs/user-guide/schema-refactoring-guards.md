# Global schema guards (refactoring R4)

R4 completes the technical schema refactoring after R1–R3. It adds enforcement, not
another format migration. All 57 registered schema families retain the versions and
single-version reader windows present in the R3 snapshot. The project remains in
`CompatibilityPhase.REFACTORING`.

## One current contract per family

Every concrete `SchemaPolicy` must declare `readable == (current,)`. Registration checks
run on import and again when a family is used. A policy cannot widen an active reader
window by opting into the future Stable rules. Unknown families, mismatched registry keys,
duplicate or malformed version windows, and incorrect phase values fail explicitly.

Version markers are type-exact: an integer schema `1` does not accept `True`, `1.0`, or
`"1"`. String markers are not parsed, coerced, or replaced by the registry's current value.
An envelope writer must supply its actual `schema_version`; the guard does not insert one.

The generic Stable policy is retained only for an explicit future phase transition.
Synthetic tests construct `SchemaPolicy(..., phase=CompatibilityPhase.STABLE)` and check
the bounded reader window and expected warnings. They do not register old production
formats or relax the current project's registry.

The removed `SCHEMA_BASELINES` and `SchemaBaseline` aliases have no replacement compatibility
shim. Use `SCHEMA_POLICIES` and `SchemaPolicy` in application code and tests.

## Guard the actual output

Application and adapter contracts may opt into `SchemaBoundModel` with an explicit,
non-serialized `SCHEMA_FAMILY` class variable. The shared validator checks supplied markers
before field coercion. JSON reads, including nested registered models, require an explicit
marker before constructor defaults can fill one in. The shared serializer checks the actual
instance marker, including
instances created by unchecked `model_copy` or `model_construct`. Excluding the marker from
a view does not bypass this check. Existing defaults for constructing new current objects
are retained; this is not permission to supply an unversioned persisted envelope.

Dictionary writers use `require_current_payload(family, payload)` before publication. The
payload is not rewritten, rehashed under a new marker, or recursively assumed to be safe.
Known independently versioned nested envelopes require their own explicit checks. The
EngineeringDocument, formal projection and extraction repositories guard their concrete
output; projection and extraction reads also check both raw markers before model coercion.

The current marker must remain a literal/default in the concrete implementation, not a
value looked up from the registry to label unchanged data. When the registry changes but
a writer does not, the writer must fail rather than advertise a new contract it has not
implemented. Early preflight checks additionally prevent a request ledger from invoking a
model under an incompatible contract. Review-state serialization is completed before a new
history entry can be written.

These checks do not make all filesystem operations globally transactional. Existing atomic
review publication, Handoff and repository boundaries remain responsible for their own
consistency. They also do not replace source hashes, context/rule binding, semantic validation,
or qualification and release gates.

## Executable coverage

`application.schema.inventory` describes lifecycle-crossing interfaces.
`application.schema.bindings` links all registered families to concrete boundaries:

| Binding | Checked by architecture tests |
| --- | --- |
| 35 model bindings | Registry family, current field type/default or Literal, inherited serialization guard |
| 21 dictionary-writer bindings | Explicit validation of the actual envelope in the named function |
| 12 resource bindings | Every matching shipped variant uses its family's exact current schema marker |

The counts overlap by family. Together they cover all 57 families; they are not 68 independent
formats. References are strings for testing/documentation, not runtime plugin dispatch or
application imports of adapter classes. The tests also check family uniqueness, missing
bindings, unknown literal guard families, and declared model bindings outside the inventory.

Packaged resource identity remains independent of serialization age. A profile/resource
version such as `1.0.0` is not its `schema_version`. No prompt, task, rule, model, resource,
AtlasData text grammar or archive-layout version is changed by R4.

When adding a schema family, add its central policy, lifecycle inventory entry and concrete
model/writer/resource binding together. Test both a current round trip and rejection of
obsolete/wrongly typed markers before publication. Preserve explicit negative values and
unobserved states in semantic tests. Keep deliberately invalid fixtures in rejection tests,
not in ordinary workflow examples.

## Tests and warning policy

Unexpected `SchemaDeprecationWarning` is an error in the project pytest configuration.
Only explicit synthetic Stable tests consume an expected warning. There is no blanket
ignore for Atlas schemas or warnings from optional third-party libraries.

```bash
uv run pytest
uv run ruff check .
```

Focused R4 checks:

```bash
uv run pytest \
  tests/architecture/test_schema_contracts.py \
  tests/unit/application/schema/test_refactoring_guards.py \
  tests/unit/application/schema/test_repository_guards.py \
  tests/unit/application/semantic_qualification/test_schema_refactoring_r4.py
```

The end-to-end regression uses registered typed MCP functions, the real Web ASGI routes and
synthetic human decisions. It follows selection, unchanged Holdout membership, evidence
proposals, blind Holdout review/reveal, confirmed values, Handoff, model-free campaign planning
and the final archive's nested review ZIP. It does not claim a live Codex session, browser
engine run, authenticated human identity or a successful production qualification.

## Existing data

No new schema versions are introduced and no productive artifacts are edited. Valid current
artifacts remain subject to the same source/configuration/hash checks as before. There is no
R4 requirement to regenerate them solely because the global guards were added.

Obsolete artifacts already rejected by R1–R3 remain rejected. Preserve historical evidence
unchanged and regenerate obsolete derived artifacts from reviewed sources when needed. Do
not edit version markers, manually repair hashes, delete human decisions or carry an old
execution identity into a new artifact. Unknown attachments and local implementation markers
are not silently promoted to centrally verified schemas.

See [schema contracts](../reference/schema-contracts.md),
[ADR 0014](../architecture/adr/0014-schema-and-artifact-versioning-policy.md),
[review Handoff](partial-review-handoff.md), and the
[R4 validation report](../development/schema-refactoring-r4-validation.md).
