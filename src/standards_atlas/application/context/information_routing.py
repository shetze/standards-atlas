"""Source-grounded safeguard against turning reading advice into scope edges.

This is deliberately a bounded policy, not a general semantic classifier. Only
explicit informational passages, verified against the source and free of a
possible governing instruction, can justify automatic reclassification. Mixed,
unverified and unrecognized evidence is never a reason to delete a scope.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from standards_atlas.application.references.catalog import ReferenceDocumentCatalog
from standards_atlas.application.references.extractor import extract_reference_mentions
from standards_atlas.application.references.resolution import reference_key
from standards_atlas.domain.model import (
    ContextRouting,
    EngineeringDocument,
    ReferenceRole,
    ReferenceRouting,
    ReferenceTarget,
)

INFORMATION_ROUTING_POLICY = "source-grounded-information-v1"
_INFORMATION = re.compile(
    r"\b(?:for\s+(?:further|more|additional|background)\s+(?:information|details)|"
    r"further\s+information|frequently\s+asked\s+questions|recommended\s+reading|"
    r"(?:may|might|will)\s+find\s+it\s+(?:helpful|useful)\s+to\s+(?:read|consult)|"
    r"(?:read|consult)\s+(?:the\s+)?following\s+(?:sections?|clauses?|documents?)\s+"
    r"(?:first|for\s+(?:information|background)))\b",
    re.I,
)
# Conservative veto: these words may express a genuine governing relation.
# Descriptions such as 'contains requirements' alone do not express one.
_GOVERNING = re.compile(
    r"\b(?:shall|must|applies|apply|applicable\s+(?:to|when|if)|governs?|covers?|excludes?|"
    r"except|unless|limited\s+to|only\s+for|"
    r"provided\s+that|only\s+(?:if|when)|subject\s+to|for\s+the\s+purposes\s+of)\b",
    re.I,
)
_ROLE_CUES = {
    ReferenceRole.DEFINES: r"\bdefin(?:e[sd]?|ition[s]?)\b",
    ReferenceRole.CONSTRAINS: r"\b(?:constrain\w*|restrict\w*|limit\w*)\b",
    ReferenceRole.REQUIRES: r"\b(?:shall|must|required\s+by)\b",
    ReferenceRole.PROVIDES_PROCEDURE: r"\b(?:procedure[s]?|method[s]?|steps?)\b",
    ReferenceRole.PROVIDES_EXCEPTION: r"\b(?:exception[s]?|exemption[s]?)\b",
    ReferenceRole.PROVIDES_APPLICABILITY: r"\bapplicab\w*\b",
    ReferenceRole.PROVIDES_EVIDENCE: r"\b(?:evidence|proof|test\s+results?)\b",
    ReferenceRole.REFINES: r"\brefin\w*\b",
    ReferenceRole.DEPENDS_ON: r"\b(?:depend\w*|prerequisite[s]?)\b",
}


def _text_key(text: str) -> str:
    return " ".join(text.split())  # No case folding or paraphrase acceptance.


@dataclass(frozen=True)
class _Passage:
    text: str

    def contains(self, quote: str) -> bool:
        return bool(quote.strip()) and _text_key(quote) in _text_key(self.text)


def _information_passages(text: str) -> tuple[_Passage, ...]:
    """Attach a colon-introduced reading list, but never the next prose paragraph."""
    paragraphs = re.split(r"\n\s*\n", text)
    passages = []
    for position, paragraph in enumerate(paragraphs):
        if not _INFORMATION.search(paragraph):
            continue
        passage = paragraph
        if paragraph.rstrip().endswith(":") and re.search(r"\bfollowing\b", paragraph, re.I):
            for following in paragraphs[position + 1 :]:
                if not re.match(r"\s*(?:[-*•]|\d+[.)])\s+", following):
                    break
                passage += "\n\n" + following
        if not _GOVERNING.search(passage):
            passages.append(_Passage(passage))
    return tuple(passages)


def _target_key(target: ReferenceTarget) -> tuple[str | None, str]:
    return target.document_key, target.clause_id or reference_key(target.reference)


class InformationRoutingPolicy:
    """Reclassify only proven navigation; record the full before/after privately."""

    def __init__(
        self, document: EngineeringDocument, documents: Iterable[EngineeringDocument] = ()
    ) -> None:
        self.document = document
        self.catalog = ReferenceDocumentCatalog(document, documents)
        self.clauses = {clause.id.value: clause for clause in document.clauses}
        self.passages: dict[str, tuple[_Passage, ...]] = {}

    def _passages(self, source: str, evidence: tuple[str, ...]) -> tuple[_Passage, ...]:
        clause = self.clauses.get(source)
        if clause is None or clause.provenance.protection("enrichments.context_routing"):
            return ()
        if source not in self.passages:
            self.passages[source] = _information_passages(clause.plain_text)
        selected = []
        for quote in evidence:
            match = next((p for p in self.passages[source] if p.contains(quote)), None)
            if match is None:
                return ()  # One unverified/mixed quote prevents automatic removal.
            if match not in selected:
                selected.append(match)
        return tuple(selected)

    def _references(self, source: str, passages: tuple[_Passage, ...]) -> list[ReferenceRouting]:
        references = []
        for passage in passages:
            for mention in extract_reference_mentions(passage.text):
                text = mention.reference
                if not text:
                    continue  # Unaddressed contextual hints are not explicit citations.
                for target in self.catalog.targets(text, source):
                    references.append(
                        ReferenceRouting(
                            source_clause_id=source,
                            target=target,
                            role=ReferenceRole.OTHER,
                            evidence=(passage.text,),
                        )
                    )
        return references

    def normalize(
        self, routing: ContextRouting, *, diagnostics: list[dict] | None = None
    ) -> ContextRouting:
        references = []
        changed = False
        for position, edge in enumerate(routing.references):
            passages = self._passages(edge.source_clause_id, edge.evidence)
            if passages:
                informational = self._references(edge.source_clause_id, passages)
                # Verify the addressed citation too; a quotation about A cannot
                # justify a change to B. Explicitly named roles remain untouched.
                targets = self.catalog.targets(edge.target.reference, edge.source_clause_id)
                addresses = {_target_key(item.target) for item in informational}
                supported = targets and all(_target_key(t) in addresses for t in targets)
                cue = _ROLE_CUES.get(edge.role)
                role_evidence = " ".join(edge.evidence)
                if supported and (cue is None or not re.search(cue, role_evidence, re.I)):
                    normalized = tuple(
                        edge.model_copy(update={"role": ReferenceRole.OTHER, "target": target})
                        for target in targets
                    )
                    if normalized != (edge,):
                        changed = True
                        if diagnostics is not None:
                            diagnostics.append(
                                {
                                    "kind": (
                                        "reference_role"
                                        if edge.role != ReferenceRole.OTHER
                                        else "informational_reference_address"
                                    ),
                                    "status": "corrected",
                                    "source_clause_id": edge.source_clause_id,
                                    "index": position,
                                    "reason": "source_verified_information_only",
                                    "before": edge.model_dump(mode="json"),
                                    "after": [item.model_dump(mode="json") for item in normalized],
                                }
                            )
                    references.extend(normalized)
                    continue
            references.append(edge)

        scopes = []
        for position, scope in enumerate(routing.scopes):
            passages = self._passages(scope.source_clause_id, scope.evidence)
            if not passages:
                scopes.append(scope)
                known = self.passages.get(scope.source_clause_id, ())
                # An overbroad quotation (e.g. the whole clause) must not bypass
                # the safeguard by also including an unrelated prose paragraph.
                # Unverified reading advice is not grounds for deletion either.
                questionable = known and (
                    not scope.evidence
                    or any(
                        (_INFORMATION.search(quote) and not _GOVERNING.search(quote))
                        or any(_text_key(p.text) in _text_key(quote) for p in known)
                        for quote in scope.evidence
                    )
                )
                if questionable and diagnostics is not None:
                    diagnostics.append(
                        {
                            "kind": "scope_semantics",
                            "status": "requires_review",
                            "source_clause_id": scope.source_clause_id,
                            "index": position,
                            "reason": "informational_source_requires_direct_scope_evidence",
                            "before": scope.model_dump(mode="json"),
                        }
                    )
                continue
            # Never stitch an informational list to a governing statement from
            # another paragraph. Such a mixed candidate needs human/model review.
            modifiers = (*scope.conditions, *scope.exclusions, *scope.qualifications)
            source = self.clauses[scope.source_clause_id]
            if _GOVERNING.search(source.plain_text) or any(
                not value.strip()
                or _text_key(value) not in _text_key(source.plain_text)
                or _GOVERNING.search(value)
                for value in modifiers
            ):
                scopes.append(scope)
                if diagnostics is not None:
                    diagnostics.append(
                        {
                            "kind": "scope_semantics",
                            "status": "requires_review",
                            "source_clause_id": scope.source_clause_id,
                            "index": position,
                            "reason": "informational_evidence_in_mixed_or_unverified_context",
                            "before": scope.model_dump(mode="json"),
                        }
                    )
                continue
            converted = self._references(scope.source_clause_id, passages)
            if not converted:
                scopes.append(scope)  # No loss of unrecognized or implicit addresses.
                continue
            changed = True
            references.extend(converted)
            if diagnostics is not None:
                diagnostics.append(
                    {
                        "kind": "scope_semantics",
                        "status": "corrected",
                        "source_clause_id": scope.source_clause_id,
                        "index": position,
                        "reason": "source_verified_information_not_scope",
                        "before": scope.model_dump(mode="json"),
                        "after": [edge.model_dump(mode="json") for edge in converted],
                    }
                )

        if not changed:
            return routing

        # Preserve independently supported roles and combine duplicate evidence
        # only for identical source/target/role edges. Source order stays stable.
        merged: dict[tuple, ReferenceRouting] = {}
        for edge in references:
            key = edge.source_clause_id, _target_key(edge.target), edge.role
            previous = merged.get(key)
            merged[key] = (
                previous.model_copy(
                    update={"evidence": tuple(dict.fromkeys((*previous.evidence, *edge.evidence)))}
                )
                if previous
                else edge
            )
        return routing.model_copy(
            update={"scopes": tuple(scopes), "references": tuple(merged.values())}
        )
