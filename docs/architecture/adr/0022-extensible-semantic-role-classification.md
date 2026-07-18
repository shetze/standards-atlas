# ADR 0022: Extensible semantic-role classification

## Status

Accepted

## Context

Standards Atlas needs reproducible semantic-role classification for clause headings across standards from different domains. Most explicit roles can be identified from headings and hierarchy without probabilistic inference. Some future cases may require content-sensitive or LLM-assisted classification.

## Decision

Introduce `SemanticRoleClassifier` as an application service. Its default implementation is deterministic and returns roles together with confidence and evidence.

The service accepts an optional `SemanticRoleClassifierExtension` port. An adapter, including a future LLM-backed adapter, may implement this port. The extension is invoked only when the deterministic result is below a configurable confidence threshold and can replace it only with a higher-confidence result.

The deterministic classifier:

- uses exact heading rules before token-based rules;
- supports multiple roles for composed headings;
- gives inherited terminology context precedence over local keywords;
- recognizes annexes from their reference or heading;
- leaves unsupported headings unclassified instead of guessing;
- exposes traceable evidence for every classification.

AtlasData onboarding uses this service and maps only roles supported by legacy AtlasData markers (`s`, `t`, `o`, `r`). The domain roles remain canonical.

## Consequences

Classification remains deterministic, testable, offline-capable, and explainable by default. LLM support can be added as an adapter without changing the domain model, onboarding service, or deterministic rules. The extension contract prevents silent replacement of high-confidence deterministic results.
