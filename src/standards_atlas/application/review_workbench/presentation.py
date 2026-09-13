"""Source-preserving evidence segmentation: no HTML, Markdown execution or JS offsets."""

from collections import defaultdict

from standards_atlas.application.semantic_qualification.review_package.sources import evidence_text


def evidence_segments(text: str, spans: list[dict]) -> list[dict]:
    """Split at every boundary, retaining all overlapping labels and exact Unicode text."""
    boundaries = {0, len(text)}
    for span in spans:
        start, end = span["start"], span["end"]
        if not 0 <= start < end <= len(text) or text[start:end] != span["quote"]:
            raise ValueError("evidence span does not match the displayed frozen source")
        boundaries.update((start, end))
    positions = sorted(boundaries)
    result = []
    for start, end in zip(positions, positions[1:], strict=False):
        marks = [
            {k: s[k] for k in ("attribute", "purpose", "proposal_sha256")}
            for s in spans
            if s["start"] < end and s["end"] > start
        ]
        result.append({"text": text[start:end], "marks": marks})
    return result


def source_presentation(source, proposals) -> dict:
    by_target = defaultdict(list)
    for proposal in proposals:
        for span in proposal.evidence:
            by_target[span.target].append(
                {
                    **span.model_dump(mode="json"),
                    "attribute": proposal.attribute,
                    "proposal_sha256": proposal.proposal_sha256,
                }
            )
    return {
        "text": evidence_segments(source.text, by_target["text"]),
        "facts": {
            target: evidence_segments(evidence_text(source, target), spans)
            for target, spans in by_target.items()
            if target != "text"
        },
    }
