"""Private last-attempt ledger; retained values are never counted as fresh successes."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from standards_atlas import __version__
from standards_atlas.application.services.context_enrichment_service import ContextEnrichmentResult


def write_context_run_report(
    result: ContextEnrichmentResult,
    *,
    workspace: Path,
    config_path: Path,
    prompt: str,
    model: str,
    fresh: bool,
) -> Path:
    """Record all clause dispositions after canonical persistence and diagnostics.

    The ledger describes this document invocation, not a semantic approval. It is
    always written, including a valid empty result. Baseline archives freeze it
    before subsequent retries replace the file.
    """
    key = result.document.key.value
    outcomes = list(getattr(result, "routing_outcomes", ()))
    counts = Counter(item["status"] for item in outcomes)
    summary = {
        name: counts[name]
        for name in (
            "succeeded",
            "reused",
            "protected",
            "failed",
            "not_candidate",
        )
    }
    # Also allow service doubles/legacy callers without per-clause diagnostics.
    # A missing ledger must never erase a reported failure.
    summary["failed"] = result.context_enrichment_failures
    summary["candidates"] = result.candidates
    summary["failed_with_retained_value"] = sum(
        item["status"] == "failed" and item.get("retained_previous_value", False)
        for item in outcomes
    )
    summary["unresolved_scope_targets"] = len(getattr(result, "unresolved_scope_targets", ()))
    summary["unresolved_reference_targets"] = len(
        getattr(result, "unresolved_reference_targets", ())
    )
    summary["routing_corrections"] = len(getattr(result, "routing_corrections", ()))
    canonical = workspace / "documents" / f"{key}.json"
    payload = {
        "schema_version": 1,
        "document_key": key,
        "completed_at": datetime.now(UTC).isoformat(),
        "standards_atlas_version": __version__,
        "status": "partial" if summary["failed"] else "completed",
        "semantically_verified": False,
        "prompt": prompt,
        "model": model,
        "fresh": fresh,
        "config": str(config_path),
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "canonical_sha256": (
            hashlib.sha256(canonical.read_bytes()).hexdigest() if canonical.is_file() else None
        ),
        "outcomes_complete": len(outcomes) == result.subject_clauses,
        "summary": summary,
        "clauses": outcomes,
    }
    target = workspace / "evaluation/context-routing" / f"{key}-run.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def failed_context_clause_ids(workspace: Path, document_key: str) -> tuple[str, ...]:
    """Do not mistake an older retained value for success of a failed new attempt."""
    path = workspace / "evaluation/context-routing" / f"{document_key}-run.json"
    if not path.exists():
        # Bootstrap from diagnostics written before last-attempt ledgers existed.
        # The absence of the new report is not evidence that old failures succeeded.
        legacy = path.with_name(f"{document_key}-failures.json")
        if not legacy.exists():
            return ()
        previous = json.loads(legacy.read_text(encoding="utf-8"))
        if previous.get("document_key") != document_key:
            raise ValueError(f"invalid context failure report: {legacy}")
        return tuple(item["clause_id"] for item in previous.get("failures", ()))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("document_key") != document_key or payload.get("schema_version") != 1:
        raise ValueError(f"invalid context run report: {path}")
    return tuple(item["clause_id"] for item in payload["clauses"] if item["status"] == "failed")
