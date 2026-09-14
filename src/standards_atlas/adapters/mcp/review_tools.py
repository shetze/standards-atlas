"""Optional FastMCP registration; only typed reads and model-only preparation writes."""

from __future__ import annotations

from typing import Any

from standards_atlas.adapters.mcp.review import McpReviewService
from standards_atlas.application.semantic_qualification.review_package.preparation_model import (
    AnnotationBatch,
    SelectionRequest,
)


def register_review_tools(mcp: Any, config: Any, tool_call: Any) -> None:
    service = McpReviewService(config)
    read = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
    write = {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }

    @mcp.tool(annotations=read)
    def list_review_packages(limit: int = 20, offset: int = 0) -> dict[str, Any]:
        """List locally registered review package handles, not arbitrary filesystem paths."""
        return tool_call(service.list_packages, limit=limit, offset=offset)

    @mcp.tool(annotations=read)
    def get_review_package(handle: str) -> dict[str, Any]:
        """Read frozen annotation rules, permitted capabilities and candidate index identities."""
        return tool_call(service.get_package, handle)

    @mcp.tool(annotations=read)
    def list_review_candidates(
        handle: str,
        index_sha256: str,
        limit: int = 20,
        offset: int = 0,
        membership: str | None = None,
        document_key: str | None = None,
        clause_type: str | None = None,
        reason: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Rank Development candidates with bound history; never expose Holdout results."""
        return tool_call(
            service.list_candidates,
            handle,
            index_sha256,
            limit=limit,
            offset=offset,
            membership=membership,
            document_key=document_key,
            clause_type=clause_type,
            reason=reason,
            query=query,
        )

    @mcp.tool(annotations=read)
    def get_review_case(handle: str, example_id: str) -> dict[str, Any]:
        """Read complete source/context and separate proposals/reviews, without truncation.

        Development may include producer_kind=engineering proposals: these are current
        normalized enrichments to challenge critically, not gold labels. Holdout keeps such
        prior candidates withheld so the model recommendation remains independent.
        """
        return tool_call(service.get_case, handle, example_id)

    @mcp.tool(annotations=read)
    def list_review_cases(
        handle: str, split: str = "development", limit: int = 20, offset: int = 0
    ) -> dict[str, Any]:
        """Page materialized review cases in their frozen review order; Holdout is opt-in."""
        return tool_call(service.list_cases, handle, split=split, limit=limit, offset=offset)

    if not config.capabilities.review_preparation:
        return

    @mcp.tool(annotations=write)
    def submit_review_selection(
        handle: str, index_sha256: str, expected_state_sha256: str, request: SelectionRequest
    ) -> dict[str, Any]:
        """Propose bounded Development additions/priorities, without approvals or moving Holdout.

        Each added source needs a source_sha256-bound priority and rationale. Actor/model are
        declared provenance. Materialize this selection with the separate local CLI operation.
        """
        return tool_call(
            service.submit_selection,
            handle,
            index_sha256=index_sha256,
            expected_state_sha256=expected_state_sha256,
            request=request,
        )

    @mcp.tool(annotations=write)
    def submit_review_annotations(
        handle: str, package_sha256: str, expected_revision: int, batch: AnnotationBatch
    ) -> dict[str, Any]:
        """Submit model-only recommendations atomically, never human confirmations.

        Send exact quote/prefix/suffix evidence with purpose support/counterevidence/context;
        target is text or fact:<index>. Atlas resolves character offsets. No HTML or manual hashes.
        Repeat the same request_id and payload for safe retry; reread revision for a new batch.
        """
        return tool_call(
            service.submit_annotations,
            handle,
            package_sha256=package_sha256,
            expected_revision=expected_revision,
            batch=batch,
        )
