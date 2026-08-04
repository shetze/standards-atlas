# Developing a Structural Taxonomy for a New Document Class

*An engineering tutorial based on the Functional Safety Knowledge Domain*

## Goal

This tutorial describes the engineering process used to develop a robust
taxonomy for a new document class. It focuses on the reasoning behind the
process rather than individual commands.

The Functional Safety Knowledge Domain serves as the running example.

## 1. Study representative standards

Before writing code, study representative standards from the target document
class.

Questions to answer include:

- Which structures appear consistently?
- Which concepts are domain-specific?
- Which concepts are shared across standards?
- Which information must survive the normalization process?

The objective is to understand the document class before defining categories.

## 2. Derive an initial taxonomy

Create a first taxonomy from observations.

Treat this taxonomy as a hypothesis rather than a final solution.

Document assumptions explicitly.

## 3. Build a representative Golden Corpus

Construct a representative corpus covering different document types,
structural patterns and uncommon situations.

Avoid relying on random sampling alone.

## 4. Evaluate multiple LLMs

Run several models using the same taxonomy.

The goal is not only to compare models but also to identify ambiguous
classification rules.

## 5. Analyse disagreements

Disagreements provide valuable information.

Investigate whether differences originate from:

- ambiguous taxonomy definitions
- insufficient evidence
- inconsistent document structures
- genuine model limitations

## 6. Refine the taxonomy

Update the taxonomy based on the analysis.

For the Functional Safety Knowledge Domain this iterative work ultimately led
to the introduction of the StructuralProfile concept.

## 7. Evolve the domain model

Only after the taxonomy stabilises should the canonical domain model evolve.

Capture architectural consequences using ADRs and incremental refactorings.

## 8. Repeat until convergence

Repeat evaluation, review and refinement until additional iterations provide
only marginal improvements.

A practical lesson from the Functional Safety work is:

> A taxonomy is not designed once. It converges through repeated engineering
> cycles.

## Lessons learned

- Human review improves quality but does not automatically establish truth.
- Consensus between models is evidence worth investigating, not proof.
- Taxonomy weaknesses often become visible before model weaknesses.
- Architecture, evaluation and documentation evolve together.
- Small, reviewable iterations produce more robust results than large redesigns.

## Next steps

Future tutorials will build on this process to describe:

- building complete Knowledge Domains
- relationship mapping across domains
- qualification of extraction pipelines
- publication through different adapters
