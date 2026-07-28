# ADR 0040: Expose evaluation services through an MCP adapter

## Status

Accepted

## Context

Standards Atlas needs programmatic access to persisted engineering clauses for local semantic
evaluation, interactive engineering assistants, and future relationship-discovery workflows.

The same clause-access behavior must be reusable by command-line workflows, benchmark runners,
tests, and remote clients. Coupling that behavior directly to MCP would make the application core
dependent on a transport protocol and would make future adapters difficult to add.

The server must also remain read-only. An external model or agent must not be able to mutate the
canonical `EngineeringDocument` repository through the evaluation interface.

## Decision

Standards Atlas exposes clause access through generic application services and treats MCP as an
inbound adapter.

The application layer defines a transport-independent `ClauseProvider` port together with stable
descriptors, filters, search operations, and deterministic sampling strategies. The filesystem
adapter implements that port against persisted `EngineeringDocument` objects.

The MCP adapter translates protocol operations into calls to those application services. It exposes
read-only tools and resources for:

- enumerating available standards;
- retrieving a clause by stable identifier;
- listing and filtering clauses;
- searching clause text;
- reproducibly sampling clauses; and
- reading the document catalog as an MCP resource.

The adapter does not contain semantic evaluation logic and does not expose repository mutation.

## Consequences

### Positive

- Evaluation behavior can be reused without MCP.
- MCP remains replaceable as an inbound adapter.
- The domain model and application services do not depend on the MCP SDK.
- Read-only behavior is explicit and testable.
- Future REST, Python, batch, or agent adapters can reuse the same application port.

### Negative

- Descriptor models duplicate a deliberately small subset of domain data.
- Changes to the public clause-access contract require compatibility consideration.
- Adapter tests are required in addition to application-service tests.

## Alternatives considered

### Implement clause access directly in MCP tools

Rejected because protocol handlers would own application behavior and become difficult to reuse or
test independently.

### Expose the repository directly

Rejected because persistence details would leak across the architecture boundary and mutation would
be difficult to constrain safely.

### Implement a REST API first

Rejected because MCP is the immediate integration target for model-assisted engineering workflows.
The generic application port nevertheless keeps a future REST adapter possible.
