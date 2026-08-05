"""Central eligibility policy for semantic qualification tasks."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.semantic_qualification.clause_access import (
    ClauseContentProfile,
    ClauseDescriptor,
)


class SemanticTaskEligibility(BaseModel):
    """Structured decision describing whether an item belongs to a task."""

    model_config = ConfigDict(frozen=True)

    eligible: bool
    item_kind: str = "clause"
    content_profile: ClauseContentProfile = ClauseContentProfile.TEXT_DOMINANT
    reason: str | None = None
    alternative_task: str | None = None


class SemanticTaskEligibilityPolicy:
    """Apply task metadata consistently at every semantic-evaluation entry point."""

    def __init__(
        self,
        *,
        supported_item_kinds: tuple[str, ...] = ("clause",),
        excluded_content_profiles: tuple[ClauseContentProfile, ...] = (),
        alternative_tasks: dict[str, str] | None = None,
    ) -> None:
        self._supported_item_kinds = supported_item_kinds
        self._excluded_content_profiles = excluded_content_profiles
        self._alternative_tasks = dict(alternative_tasks or {})

    def evaluate_clause(self, clause: ClauseDescriptor) -> SemanticTaskEligibility:
        return self.evaluate(
            item_kind="clause",
            content_profile=clause.content_profile,
        )

    def evaluate(
        self,
        *,
        item_kind: str,
        content_profile: ClauseContentProfile,
    ) -> SemanticTaskEligibility:
        if item_kind not in self._supported_item_kinds:
            return SemanticTaskEligibility(
                eligible=False,
                item_kind=item_kind,
                content_profile=content_profile,
                reason="unsupported_item_kind",
                alternative_task=self._alternative_tasks.get("unsupported_item_kind"),
            )
        if content_profile in self._excluded_content_profiles:
            reason = content_profile.value
            return SemanticTaskEligibility(
                eligible=False,
                item_kind=item_kind,
                content_profile=content_profile,
                reason=reason,
                alternative_task=self._alternative_tasks.get(reason),
            )
        return SemanticTaskEligibility(
            eligible=True,
            item_kind=item_kind,
            content_profile=content_profile,
        )

    @classmethod
    def from_task(cls, task: object) -> SemanticTaskEligibilityPolicy:
        return cls(
            supported_item_kinds=tuple(getattr(task, "supported_item_kinds", ("clause",))),
            excluded_content_profiles=tuple(
                ClauseContentProfile(value)
                for value in getattr(task, "excluded_content_profiles", ())
            ),
            alternative_tasks=dict(getattr(task, "alternative_tasks", {})),
        )


def eligibility_from_input(
    policy: SemanticTaskEligibilityPolicy,
    item_input: dict[str, object],
) -> SemanticTaskEligibility:
    """Evaluate a persisted dataset item, including corpora created before the policy."""
    context = item_input.get("context")
    context_payload = context if isinstance(context, dict) else {}
    profile_value = context_payload.get("content_profile", ClauseContentProfile.TEXT_DOMINANT.value)
    try:
        profile = ClauseContentProfile(str(profile_value))
    except ValueError:
        profile = ClauseContentProfile.TEXT_DOMINANT
    return policy.evaluate(item_kind="clause", content_profile=profile)
