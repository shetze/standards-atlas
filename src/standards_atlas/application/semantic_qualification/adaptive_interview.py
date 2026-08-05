"""Adaptive, normalization-aware semantic qualification interviews."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InterviewDimension(StrEnum):
    STATEMENT_FUNCTION = "statement_function"
    KNOWLEDGE_KIND = "knowledge_kind"
    PROCESS_FUNCTION = "process_function"
    APPLICABILITY = "applicability"
    RESPONSIBILITY = "responsibility"
    REFERENCE_SEMANTICS = "reference_semantics"


class InterviewQuestion(BaseModel):
    """One focused question selected from normalized clause evidence."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    dimension: InterviewDimension
    question: str = Field(min_length=1)
    allowed_labels: tuple[str, ...] = ()
    reason: str = Field(min_length=1)


class AdaptiveInterviewPlan(BaseModel):
    """Deterministic set of focused questions for one clause."""

    model_config = ConfigDict(frozen=True)

    questions: tuple[InterviewQuestion, ...]
    skipped_dimensions: tuple[InterviewDimension, ...] = ()


_REFERENCE_MARKERS = (
    "internal_reference",
    "external_reference",
    "references",
    "reference_candidates",
    "relations",
)


class AdaptiveInterviewPlanner:
    """Select focused questions from structural and normalization context."""

    def plan(self, item_input: Any) -> AdaptiveInterviewPlan:
        context = dict(item_input.get("context", {}))
        content = str(dict(item_input.get("content", {})).get("text", ""))
        roles = {str(value) for value in context.get("structural_roles", ())}
        clause_type = str(context.get("clause_type", ""))
        canonical_section = str(context.get("canonical_section", ""))
        categories = {
            *(str(value) for value in context.get("document_categories", ())),
            *(str(value) for value in context.get("domain_categories", ())),
        }
        structural = roles | categories | {clause_type, canonical_section}

        questions: list[InterviewQuestion] = []
        skipped: list[InterviewDimension] = []

        deterministic = structural & {
            "toc",
            "front_matter",
            "bibliography",
            "references",
            "term",
            "terminology",
            "example",
            "note",
        }
        if deterministic:
            skipped.append(InterviewDimension.STATEMENT_FUNCTION)
        else:
            questions.append(
                InterviewQuestion(
                    id="statement-function",
                    dimension=InterviewDimension.STATEMENT_FUNCTION,
                    question=(
                        "What single primary statement function is directly expressed "
                        "by this clause?"
                    ),
                    allowed_labels=(
                        "requirement",
                        "recommendation",
                        "condemnation",
                        "permission",
                        "prohibition",
                        "definition",
                        "description",
                        "explanation",
                        "rationale",
                        "example",
                        "note",
                        "guideline",
                        "conformance_statement",
                        "objective",
                        "prerequisite",
                        "assumption",
                        "none",
                    ),
                    reason="The normalized structure does not determine the statement function.",
                )
            )

        knowledge_markers = (
            "technique",
            "method_or_measure",
            "procedure",
            "process",
            "artifact",
            "record",
            "evidence",
            "role",
            "concept",
        )
        if any(marker in content.lower() for marker in knowledge_markers) or bool(
            structural
            & {"technique", "method_or_measure", "measure", "method", "techniques_and_measures"}
        ):
            questions.append(
                InterviewQuestion(
                    id="knowledge-kind",
                    dimension=InterviewDimension.KNOWLEDGE_KIND,
                    question="What engineering knowledge kind is represented by this clause?",
                    allowed_labels=(
                        "technique",
                        "method_or_measure",
                        "process",
                        "artifact",
                        "role",
                        "evidence",
                        "concept",
                        "none",
                    ),
                    reason="Clause wording or structure indicates an engineering knowledge kind.",
                )
            )
        else:
            skipped.append(InterviewDimension.KNOWLEDGE_KIND)

        process_markers = (
            "objective",
            "purpose",
            "aim",
            "before",
            "after",
            "following",
            "input",
            "output",
            "if",
            "when",
            "unless",
            "otherwise",
            "option",
            "alternative",
            "assume",
            "assumption",
            "completion",
        )
        if any(marker in content.lower() for marker in process_markers):
            questions.append(
                InterviewQuestion(
                    id="process-function",
                    dimension=InterviewDimension.PROCESS_FUNCTION,
                    question=(
                        "What single process-model role is directly expressed by this clause?"
                    ),
                    allowed_labels=(
                        "objective",
                        "prerequisite",
                        "input",
                        "activity",
                        "decision",
                        "branch",
                        "sequence",
                        "output",
                        "completion_criterion",
                        "option",
                        "assumption",
                        "none",
                    ),
                    reason=(
                        "Clause wording contains process, lifecycle, decision, or sequencing "
                        "signals."
                    ),
                )
            )
        else:
            skipped.append(InterviewDimension.PROCESS_FUNCTION)

        structural_scope = (
            canonical_section == "scope" or clause_type == "scope" or bool(structural & {"scope"})
        )
        applicability_signal = bool(structural & {"applicability"}) or any(
            marker in content.lower()
            for marker in ("applicable", "applies to", "only if", "unless", "out of scope")
        )
        if applicability_signal:
            questions.append(
                InterviewQuestion(
                    id="applicability-presence",
                    dimension=InterviewDimension.APPLICABILITY,
                    question=(
                        "Does this clause explicitly govern whether a document, section, "
                        "requirement, method, role, or situation applies?"
                    ),
                    allowed_labels=("present", "none"),
                    reason=(
                        "Clause wording indicates semantic applicability beyond structural "
                        "section placement."
                        if structural_scope
                        else (
                            "Normalization or clause wording indicates an applicability hypothesis."
                        )
                    ),
                )
            )
        else:
            skipped.append(InterviewDimension.APPLICABILITY)

        responsibility_signal = any(
            marker in content.lower()
            for marker in (
                "responsible",
                "responsibility",
                "shall ensure",
                "shall be performed by",
                "is assigned to",
            )
        )
        if responsibility_signal:
            questions.append(
                InterviewQuestion(
                    id="responsibility-presence",
                    dimension=InterviewDimension.RESPONSIBILITY,
                    question=(
                        "Does this clause explicitly connect an identifiable actor or role "
                        "to a duty, exclusion, or responsibility condition?"
                    ),
                    allowed_labels=("present", "none"),
                    reason=("Clause wording indicates a responsibility allocation hypothesis."),
                )
            )
        else:
            skipped.append(InterviewDimension.RESPONSIBILITY)

        if self._has_reference_evidence(context):
            questions.append(
                InterviewQuestion(
                    id="reference-semantics",
                    dimension=InterviewDimension.REFERENCE_SEMANTICS,
                    question=(
                        "What is the semantic purpose of the detected reference in this clause?"
                    ),
                    allowed_labels=(
                        "extends_requirement",
                        "example",
                        "supporting_guidance",
                        "verification_method",
                        "validation_method",
                        "technique_or_method",
                        "dependency",
                        "generic_reference",
                        "unclear",
                    ),
                    reason="Normalization detected one or more clause references.",
                )
            )
        else:
            skipped.append(InterviewDimension.REFERENCE_SEMANTICS)

        return AdaptiveInterviewPlan(questions=tuple(questions), skipped_dimensions=tuple(skipped))

    @staticmethod
    def _has_reference_evidence(context: dict[str, Any]) -> bool:
        for key in _REFERENCE_MARKERS:
            value = context.get(key)
            if value:
                return True
        return bool(
            context.get("has_internal_references") or context.get("has_external_references")
        )


def focused_response_schema(labels: tuple[str, ...]) -> dict[str, Any]:
    """Return the small schema shared by all interview questions."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["label", "confidence", "evidence"],
        "properties": {
            "label": {"type": "string", "enum": list(labels)},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "evidence": {"type": "string"},
        },
    }


def follow_up_question(question: InterviewQuestion) -> InterviewQuestion | None:
    """Return the subtype question for a positive hierarchical presence decision."""
    if question.id == "applicability-presence":
        return InterviewQuestion(
            id="applicability-subtype",
            dimension=InterviewDimension.APPLICABILITY,
            question=(
                "Which single applicability subtype is explicitly expressed? Treat a local "
                "logical condition as none unless it governs application of normative content."
            ),
            allowed_labels=(
                "applicability_condition",
                "inclusion",
                "exclusion",
                "exception",
                "none",
            ),
            reason="A positive applicability-presence decision requires one subtype.",
        )
    if question.id == "responsibility-presence":
        return InterviewQuestion(
            id="responsibility-subtype",
            dimension=InterviewDimension.RESPONSIBILITY,
            question=(
                "Which single responsibility subtype is explicitly expressed? Select none "
                "unless the evidence names both an actor or role and its duty or exclusion."
            ),
            allowed_labels=(
                "responsibility_assignment",
                "responsibility_exclusion",
                "role_condition",
                "none",
            ),
            reason="A positive responsibility-presence decision requires one subtype.",
        )
    return None
