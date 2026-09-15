# AtlasData enrichments

AtlasData companions publish accepted, text-safe enrichment state separately from source baselines. The current clean-break schema version is `1`.

## Current enrichment dimensions

A clause may publish these independent dimensions:

- `enrichments.applicability`: explicit applicability presence and optional `included` / `excluded` polarity;
- `enrichments.context_routing`: accepted routing context used to frame interpretation;
- `enrichments.subject_context`: accepted subject framing for the clause.

Clause-level statement, knowledge, process and role classifications are not part of the current companion schema. Engineering-domain meaning is represented by evidence-backed `DocumentKnowledge` entities and `NormativeAssertion` records in the canonical EngineeringDocument.

## Authority and partial publication

Each selected dimension is published independently. A partial export may update one dimension without inventing values for the others. Accepted applicability remains visible to downstream consumers but is excluded from applicability-qualification inputs and source-only fingerprints so it cannot trigger its own reclassification.

Old `AF-*` tags and legacy semantic applicability fields are not read or written. Existing generated companions from the former schema must be deleted and rebuilt.
