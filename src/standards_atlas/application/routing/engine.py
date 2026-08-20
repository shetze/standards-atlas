"""Deterministic routing engine binding taxonomy evidence to semantic tasks."""

from __future__ import annotations

from collections import defaultdict

from standards_atlas.application.routing.matcher import matches
from standards_atlas.application.routing.model import (
    RoutingContract,
    RoutingDecision,
    RoutingDisposition,
    RoutingRule,
    SemanticRoutingPlan,
    TaxonomySignalProfile,
)

_DISPOSITION_PRECEDENCE = {
    RoutingDisposition.SKIP: 0,
    RoutingDisposition.OPTIONAL: 1,
    RoutingDisposition.PREFERRED: 2,
    RoutingDisposition.REQUIRED: 3,
}


class DeterministicRoutingEngine:
    """Evaluate a versioned in-memory routing contract without semantic inference."""

    def route(
        self,
        profile: TaxonomySignalProfile,
        contract: RoutingContract,
    ) -> SemanticRoutingPlan:
        """Return stable task decisions for all rules matching the signal profile."""

        by_task: dict[str, list[RoutingRule]] = defaultdict(list)
        for rule in contract.rules:
            if matches(rule.when, profile):
                by_task[rule.task].append(rule)

        decisions = tuple(
            self._decision(task, tuple(rules)) for task, rules in sorted(by_task.items())
        )
        return SemanticRoutingPlan(
            contract_id=contract.id,
            contract_version=contract.version,
            decisions=decisions,
        )

    def _decision(
        self,
        task: str,
        rules: tuple[RoutingRule, ...],
    ) -> RoutingDecision:
        winning_disposition = max(
            (rule.effect for rule in rules),
            key=_DISPOSITION_PRECEDENCE.__getitem__,
        )
        matched_rules = tuple(sorted(rule.id for rule in rules))
        winning_rules = tuple(
            sorted(
                (rule for rule in rules if rule.effect is winning_disposition),
                key=lambda rule: rule.id,
            )
        )
        hints: dict[str, str] = {}
        for rule in winning_rules:
            for key, value in sorted(rule.context_hints.items()):
                hints.setdefault(key, value)
        return RoutingDecision(
            task=task,
            disposition=winning_disposition,
            reasons=tuple(f"contract_rule:{rule.id}" for rule in winning_rules),
            matched_rules=matched_rules,
            context_hints=hints,
        )
