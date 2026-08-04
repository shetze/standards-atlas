# Knowledge Domains

## Historical context

The first implemented use case focused on Functional Safety standards and used
Doorstop as the first publication adapter. This historical origin explains many
implementation decisions but does not constrain the long-term architecture.

## Current state

Knowledge Domains are the canonical organisation of extracted engineering
knowledge. They are intentionally independent from publication technologies.

A Knowledge Domain may contain:

- clause identities
- structural profiles
- references
- relationship information
- travelogues
- provenance
- review metadata

## Adapters

Publication and integration adapters project a Knowledge Domain into specific
ecosystems.

Initially implemented:

- Doorstop

Planned:

- BASIL
- Markdown
- Graph-oriented tooling (e.g. Tulip)

Adapters must not define the canonical information model.

## Travelogues

Travelogues are first-class artefacts of a Knowledge Domain and should be
published together with generated adapter artefacts where supported.
