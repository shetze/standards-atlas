"""Render, parse and compare full-document Markdown alignment reviews."""

from __future__ import annotations

import re
from collections.abc import Iterable

from standards_atlas.application.model.alignment import AlignmentResult, AlignmentStatus
from standards_atlas.application.model.markdown_review import (
    MarkdownReviewBlock,
    MarkdownReviewChange,
    MarkdownReviewChangeKind,
    MarkdownReviewDiff,
    MarkdownReviewDocument,
    MarkdownReviewHeading,
)
from standards_atlas.application.model.normalized_document import (
    NormalizedCode,
    NormalizedExtractedDocument,
    NormalizedFormula,
    NormalizedHeading,
    NormalizedList,
    NormalizedPicture,
    NormalizedTable,
    NormalizedText,
    NormalizedUnknown,
)

_ANCHOR = re.compile(r"^<!-- atlas:item=(?P<item_id>.+?) -->$")
_ACTIVE_HEADING_WITH_DASH = re.compile(r"^(?P<hashes>#+)\s+(?P<label>.+?)\s+-\s*(?P<trailing>.*)$")
_ACTIVE_HEADING = re.compile(r"^(?P<hashes>#+)\s+(?P<label>.+?)\s*$")
_INACTIVE_MARKER = re.compile(r"^(?P<label>.+?)\s+-\s*(?P<trailing>.*)$")
_REFERENCE = re.compile(
    r"^(?P<reference>(?:\d+(?:\.\d+)*|[A-Z]+(?:\.\d+)*))"
    r"(?:\s+(?P<heading>.*))?$"
)


class FullDocumentReviewRenderer:
    """Render every normalized item with stable, unobtrusive anchors."""

    def render(
        self,
        normalized: NormalizedExtractedDocument,
        alignment: AlignmentResult,
    ) -> str:
        alignment_by_sequence = {
            clause.start_sequence_number: clause
            for clause in alignment.clauses
            if clause.start_sequence_number is not None
            and clause.status is not AlignmentStatus.MISSING
        }
        lines = [
            f"<!-- atlas:review-document={normalized.source_id} -->",
            "<!-- Edit alignment markers only. Use: # <reference> <heading> - <content> -->",
            "",
        ]
        skipped_items: set[str] = set()
        for item in normalized.items:
            if item.id in skipped_items:
                continue
            clause = alignment_by_sequence.get(item.sequence_number)
            if clause is not None and clause.status is AlignmentStatus.LOW_CONFIDENCE:
                confidence = "unknown" if clause.confidence is None else f"{clause.confidence:.2f}"
                lines.append(
                    "<!-- atlas:alignment-confidence=low "
                    f"reference={clause.expected_reference} confidence={confidence} -->"
                )
            lines.append(f"<!-- atlas:item={item.id} -->")
            if clause is None:
                lines.extend(self._render_item(item))
            else:
                heading = clause.observed_title or ""
                marker = f"# {clause.expected_reference}"
                if heading:
                    marker += f" {heading}"
                if clause.status in {
                    AlignmentStatus.LOW_CONFIDENCE,
                    AlignmentStatus.SEQUENCE_INFERRED,
                }:
                    marker += " -"
                lines.append(marker)
                trailing = self._trailing_content(item, clause)
                if trailing:
                    lines.extend(("", trailing))
                if clause.following_label_item_id:
                    skipped_items.add(clause.following_label_item_id)
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _trailing_content(item, clause) -> str | None:
        if clause.remainder_kind is not None and clause.remainder_kind.value == "content":
            return clause.observed_remainder
        if isinstance(item, NormalizedText) and clause.observed_remainder is None:
            text = item.text.strip()
            prefix = clause.expected_reference
            if text == prefix:
                return None
            if text.startswith(prefix + " "):
                remainder = text[len(prefix) :].strip()
                if clause.observed_title and remainder.startswith(clause.observed_title):
                    remainder = remainder[len(clause.observed_title) :].strip()
                return remainder or None
        return None

    @staticmethod
    def _render_item(item) -> list[str]:
        if isinstance(item, (NormalizedText, NormalizedHeading)):
            return [item.text]
        if isinstance(item, NormalizedCode):
            fence = f"```{item.language or ''}".rstrip()
            return [fence, item.code, "```"]
        if isinstance(item, NormalizedList):
            result: list[str] = []
            for index, entry in enumerate(item.items, start=1):
                marker = f"{index}." if item.ordered else "-"
                result.append(f"{marker} {entry.text}")
            return result
        if isinstance(item, NormalizedTable):
            if not item.rows:
                return ["[empty table]"]
            rows = [[cell.text for cell in row.cells] for row in item.rows]
            width = max(len(row) for row in rows)
            rows = [row + [""] * (width - len(row)) for row in rows]
            header = rows[0]
            result = ["| " + " | ".join(header) + " |"]
            result.append("| " + " | ".join("---" for _ in header) + " |")
            result.extend("| " + " | ".join(row) + " |" for row in rows[1:])
            return result
        if isinstance(item, NormalizedFormula):
            return [f"$${item.expression}$$"]
        if isinstance(item, NormalizedPicture):
            label = item.caption or item.description or item.image_reference or "picture"
            return [f"![{label}]({item.image_reference or ''})"]
        if isinstance(item, NormalizedUnknown):
            return [item.text or f"[{item.type}]"]
        return [f"[{item.type}]"]


class FullDocumentReviewParser:
    """Parse anchored review Markdown without treating Markdown as canonical data."""

    def parse(self, markdown: str) -> MarkdownReviewDocument:
        lines = markdown.splitlines()
        blocks: list[MarkdownReviewBlock] = []
        current_id: str | None = None
        current_lines: list[str] = []
        for line in lines:
            anchor = _ANCHOR.match(line.strip())
            if anchor:
                if current_id is not None:
                    blocks.append(self._parse_block(current_id, current_lines))
                current_id = anchor.group("item_id")
                current_lines = []
                continue
            if current_id is not None:
                current_lines.append(line)
        if current_id is not None:
            blocks.append(self._parse_block(current_id, current_lines))
        return MarkdownReviewDocument(blocks=tuple(blocks))

    def _parse_block(self, item_id: str, lines: list[str]) -> MarkdownReviewBlock:
        content = self._trim_blank_edges(lines)
        if not content:
            return MarkdownReviewBlock(item_id=item_id)
        first = content[0]
        active_with_dash = _ACTIVE_HEADING_WITH_DASH.match(first)
        active = active_with_dash or _ACTIVE_HEADING.match(first)
        if active:
            label = active.group("label").strip()
            parsed = _REFERENCE.match(label)
            if parsed is None:
                return MarkdownReviewBlock(item_id=item_id, body="\n".join(content))
            trailing = (
                active_with_dash.group("trailing").strip() or None
                if active_with_dash is not None
                else None
            )
            body_lines = ([trailing] if trailing else []) + content[1:]
            return MarkdownReviewBlock(
                item_id=item_id,
                heading=MarkdownReviewHeading(
                    level=len(active.group("hashes")),
                    reference=parsed.group("reference"),
                    heading=(parsed.group("heading") or "").strip() or None,
                    trailing_content=trailing,
                ),
                body="\n".join(self._trim_blank_edges(body_lines)),
            )
        inactive = _INACTIVE_MARKER.match(first)
        if inactive and _REFERENCE.match(inactive.group("label").strip()):
            trailing = inactive.group("trailing").strip() or None
            body_lines = ([trailing] if trailing else []) + content[1:]
            return MarkdownReviewBlock(
                item_id=item_id,
                disabled_heading_text=inactive.group("label").strip(),
                body="\n".join(self._trim_blank_edges(body_lines)),
            )
        return MarkdownReviewBlock(item_id=item_id, body="\n".join(content))

    @staticmethod
    def _trim_blank_edges(lines: Iterable[str]) -> list[str]:
        result = list(lines)
        while result and not result[0].strip():
            result.pop(0)
        while result and not result[-1].strip():
            result.pop()
        return result


class FullDocumentReviewDiffer:
    """Compare generated and edited reviews using item anchors, not line positions."""

    def diff(
        self,
        generated: MarkdownReviewDocument,
        edited: MarkdownReviewDocument,
    ) -> MarkdownReviewDiff:
        generated_by_id = {block.item_id: block for block in generated.blocks}
        edited_by_id = {block.item_id: block for block in edited.blocks}
        changes: list[MarkdownReviewChange] = []
        for item_id, original in generated_by_id.items():
            current = edited_by_id.get(item_id)
            if current is None:
                changes.append(
                    MarkdownReviewChange(
                        kind=MarkdownReviewChangeKind.CONTENT_MODIFIED,
                        item_id=item_id,
                        message="Anchored item was removed from the edited review.",
                    )
                )
                continue
            changes.extend(self._heading_changes(item_id, original, current))
            if self._semantic_body(original) != self._semantic_body(current):
                changes.append(
                    MarkdownReviewChange(
                        kind=MarkdownReviewChangeKind.CONTENT_MODIFIED,
                        item_id=item_id,
                        message="Document content changed outside the alignment marker.",
                    )
                )
        for item_id in edited_by_id.keys() - generated_by_id.keys():
            changes.append(
                MarkdownReviewChange(
                    kind=MarkdownReviewChangeKind.CONTENT_MODIFIED,
                    item_id=item_id,
                    message="Unknown item anchor was added to the edited review.",
                )
            )
        return MarkdownReviewDiff(changes=tuple(changes))

    @staticmethod
    def _heading_changes(item_id, original, current):
        before = original.heading
        after = current.heading
        if before is None and after is not None:
            return [
                MarkdownReviewChange(
                    kind=MarkdownReviewChangeKind.ADD_ALIGNMENT,
                    item_id=item_id,
                    reference=after.reference,
                    heading=after.heading,
                    level=after.level,
                )
            ]
        if before is not None and after is None:
            return [
                MarkdownReviewChange(
                    kind=MarkdownReviewChangeKind.REMOVE_ALIGNMENT,
                    item_id=item_id,
                    previous_reference=before.reference,
                    previous_heading=before.heading,
                    previous_level=before.level,
                )
            ]
        if before is None or after is None:
            return []
        result = []
        if before.reference != after.reference:
            result.append(
                MarkdownReviewChange(
                    kind=MarkdownReviewChangeKind.CHANGE_REFERENCE,
                    item_id=item_id,
                    reference=after.reference,
                    previous_reference=before.reference,
                )
            )
        if before.heading != after.heading:
            result.append(
                MarkdownReviewChange(
                    kind=MarkdownReviewChangeKind.CHANGE_HEADING,
                    item_id=item_id,
                    reference=after.reference,
                    heading=after.heading,
                    previous_heading=before.heading,
                )
            )
        if before.level != after.level:
            result.append(
                MarkdownReviewChange(
                    kind=MarkdownReviewChangeKind.CHANGE_LEVEL,
                    item_id=item_id,
                    reference=after.reference,
                    level=after.level,
                    previous_level=before.level,
                )
            )
        return result

    @staticmethod
    def _semantic_body(block: MarkdownReviewBlock) -> str:
        body = " ".join(block.body.split())
        if block.heading is None:
            if block.disabled_heading_text:
                return " ".join(part for part in (block.disabled_heading_text, body) if part)
            return body
        parts = [block.heading.reference]
        if block.heading.heading:
            parts.append(block.heading.heading)
        if body:
            parts.append(body)
        return " ".join(parts)


class MarkdownReviewOverrideBuilder:
    """Translate reviewed Markdown changes into existing override actions."""

    def build(self, diff, engineering, automatic):
        from standards_atlas.application.model.alignment_review import (
            AlignmentOverrideDocument,
            AssignOverride,
            IgnoreCandidateOverride,
            SetHeadingLevelOverride,
            SetObservedHeadingOverride,
        )

        clause_by_reference: dict[str, list] = {}
        for clause in engineering.clauses:
            clause_by_reference.setdefault(clause.reference.clause, []).append(clause)
        automatic_by_item = {
            clause.candidate_item_id: clause
            for clause in automatic.clauses
            if clause.candidate_item_id is not None
        }
        overrides = []
        assigned: set[tuple[str, str]] = set()
        for change in diff.changes:
            if change.kind is MarkdownReviewChangeKind.CONTENT_MODIFIED:
                continue
            if change.kind is MarkdownReviewChangeKind.REMOVE_ALIGNMENT:
                overrides.append(
                    IgnoreCandidateOverride(
                        candidate_item_id=change.item_id,
                        comment="Removed as alignment marker in reviewed Markdown.",
                    )
                )
                continue
            if change.kind in {
                MarkdownReviewChangeKind.ADD_ALIGNMENT,
                MarkdownReviewChangeKind.CHANGE_REFERENCE,
            }:
                reference = change.reference
                matches = clause_by_reference.get(reference or "", [])
                if len(matches) != 1:
                    raise ValueError(
                        f"Reference {reference!r} does not resolve to exactly one clause."
                    )
                clause_id = matches[0].id.value
                key = (clause_id, change.item_id)
                if key not in assigned:
                    overrides.append(
                        AssignOverride(
                            clause_id=clause_id,
                            candidate_item_id=change.item_id,
                            comment="Added or moved in reviewed Markdown.",
                        )
                    )
                    assigned.add(key)
                previous = automatic_by_item.get(change.item_id)
                if previous is not None and previous.clause_id != clause_id:
                    overrides.append(
                        IgnoreCandidateOverride(
                            candidate_item_id=change.item_id,
                            comment="Automatic clause assignment replaced in reviewed Markdown.",
                        )
                    )
            if change.kind is MarkdownReviewChangeKind.CHANGE_HEADING:
                reference = change.reference
                matches = clause_by_reference.get(reference or "", [])
                if len(matches) == 1:
                    overrides.append(
                        SetObservedHeadingOverride(
                            clause_id=matches[0].id.value,
                            heading=change.heading,
                            comment="Observed heading changed in reviewed Markdown.",
                        )
                    )
            if change.kind is MarkdownReviewChangeKind.CHANGE_LEVEL:
                reference = change.reference
                matches = clause_by_reference.get(reference or "", [])
                if len(matches) == 1 and change.level is not None:
                    overrides.append(
                        SetHeadingLevelOverride(
                            clause_id=matches[0].id.value,
                            level=change.level,
                            comment="Heading level explicitly changed in reviewed Markdown.",
                        )
                    )
        return AlignmentOverrideDocument(
            document_key=engineering.key.value,
            overrides=tuple(overrides),
        )
