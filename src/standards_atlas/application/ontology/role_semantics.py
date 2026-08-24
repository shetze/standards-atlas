"""Dedicated role-semantics presence detection and relation extraction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from standards_atlas.application.ontology.engine import OntologyContext
from standards_atlas.application.ports.llm_gateway import LlmGateway, StructuredGenerationRequest
from standards_atlas.domain.model import RoleRelation, RoleRelationClassCore


@dataclass(frozen=True)
class RoleSemanticsResult:
    """Role semantics detected in one clause and any grounded relations extracted from it."""

    present: bool
    relations: tuple[RoleRelation, ...] = ()


class RoleSemanticsClassifier(Protocol):
    """Classify role semantics using a presence-first, extraction-second composition."""

    def classify(self, context: OntologyContext) -> RoleSemanticsResult: ...


class LlmRoleSemanticsClassifier:
    """Use two focused structured-generation tasks for role semantics.

    Relation extraction is local task composition: it is invoked only after the
    presence task reports role semantics. No routing artifact or routing contract is
    persisted.
    """

    def __init__(self, gateway: LlmGateway, *, model: str | None = None) -> None:
        self._gateway = gateway
        self._model = model

    def classify(self, context: OntologyContext) -> RoleSemanticsResult:
        payload = _context_payload(context)
        presence = self._gateway.generate_structured(
            StructuredGenerationRequest(
                task="role-semantics-presence",
                system_prompt=(
                    "Decide whether the clause contains explicit role, actor, "
                    "resposibility, accountability, participation, assignment, verification, "
                    "validation, approval, or organizational-independence semantics. A complete "
                    "actor-relation-target tuple is NOT required. Passive wording such as 'shall "
                    "be verified' is positive  role semantics even when the actor is not stated. "
                    "Do not infer missing actors."
                ),
                user_prompt=json.dumps(payload, ensure_ascii=False, sort_keys=True),
                output_schema=_presence_schema(),
                prompt_version="1.0.0",
                model=self._model,
                temperature=0.0,
                seed=0,
                max_tokens=256,
                reasoning_enabled=False,
            )
        )
        present = bool(presence.value.get("role_semantics_present", False))
        if not present:
            return RoleSemanticsResult(present=False)

        extraction = self._gateway.generate_structured(
            StructuredGenerationRequest(
                task="role-relation-extraction",
                system_prompt=(
                    "Extract only explicit role relations as actor, relation_class, and target. "
                    "An actor must be an explicitly identified human or organizational role, "
                    "group, organization, authority, committee, supplier, duty holder, or "
                    "stakeholder. Technical objects are not actors merely because they are "
                    "grammatical subjects. Prefer the documented core relation classes when "
                    "they fit, but do not force a relation into the core vocabulary. Do not "
                    "invent an actor from passive wording. Return an empty relations list when "
                    "no complete actor-class-target relation is explicit."
                ),
                user_prompt=json.dumps(payload, ensure_ascii=False, sort_keys=True),
                output_schema=_extraction_schema(),
                prompt_version="1.0.0",
                model=self._model,
                temperature=0.0,
                seed=0,
                max_tokens=768,
                reasoning_enabled=False,
            )
        )
        relations = tuple(
            RoleRelation.model_validate(item) for item in extraction.value.get("role_relations", ())
        )
        return RoleSemanticsResult(present=True, relations=relations)


def _context_payload(context: OntologyContext) -> dict[str, object]:
    return {
        "content": context.content,
        "structural_context": context.structural_context,
        "metadata": context.metadata,
    }


def _presence_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["role_semantics_present", "confidence", "rationale"],
        "properties": {
            "role_semantics_present": {"type": "boolean"},
            "confidence": {"type": ["number", "null"], "minimum": 0.0, "maximum": 1.0},
            "rationale": {"type": ["string", "null"]},
        },
    }


def _extraction_schema() -> dict[str, object]:
    core_classes = [item.value for item in RoleRelationClassCore]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["role_relations"],
        "properties": {
            "role_relations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["actor", "relation_class", "target"],
                    "properties": {
                        "actor": {"type": "string", "minLength": 1},
                        "relation_class": {
                            "type": "string",
                            "minLength": 1,
                            "description": (
                                "Open semantic relation class. Recommended core values: "
                                + ", ".join(core_classes)
                            ),
                        },
                        "target": {"type": "string", "minLength": 1},
                    },
                },
            }
        },
    }
