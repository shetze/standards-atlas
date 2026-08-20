import pytest

from standards_atlas.application.routing import (
    AlwaysMatcher,
    DeterministicRoutingEngine,
    RoutingContract,
    RoutingDisposition,
    RoutingRule,
    RoutingTaskReference,
    SignalEqualsMatcher,
    TaxonomySignalField,
    TaxonomySignalProfile,
)


def _rule(
    rule_id: str,
    task: str,
    effect: RoutingDisposition,
    *,
    context_hints: dict[str, str] | None = None,
) -> RoutingRule:
    return RoutingRule(
        id=rule_id,
        task=task,
        effect=effect,
        when=AlwaysMatcher(),
        context_hints=context_hints or {},
    )


def test_engine_returns_only_tasks_with_matching_rules() -> None:
    contract = RoutingContract(
        id="test-contract",
        version="1.0.0",
        rules=(
            _rule("core", "statement-function-classification", RoutingDisposition.REQUIRED),
            RoutingRule(
                id="scope",
                task="applicability-extraction",
                effect=RoutingDisposition.PREFERRED,
                when=SignalEqualsMatcher(
                    field=TaxonomySignalField.CANONICAL_SECTION,
                    value="scope",
                ),
            ),
        ),
    )

    plan = DeterministicRoutingEngine().route(
        TaxonomySignalProfile(canonical_section="body"),
        contract,
    )

    assert tuple(decision.task for decision in plan.decisions) == (
        "statement-function-classification",
    )
    assert plan.decision_for("applicability-extraction") is None


def test_required_overrides_preferred_optional_and_skip() -> None:
    contract = RoutingContract(
        id="test-contract",
        version="1.0.0",
        rules=(
            _rule("skip", "role-relation-extraction", RoutingDisposition.SKIP),
            _rule("optional", "role-relation-extraction", RoutingDisposition.OPTIONAL),
            _rule("preferred", "role-relation-extraction", RoutingDisposition.PREFERRED),
            _rule("required", "role-relation-extraction", RoutingDisposition.REQUIRED),
        ),
    )

    decision = (
        DeterministicRoutingEngine()
        .route(
            TaxonomySignalProfile(),
            contract,
        )
        .decision_for("role-relation-extraction")
    )

    assert decision is not None
    assert decision.disposition is RoutingDisposition.REQUIRED
    assert decision.reasons == ("contract_rule:required",)
    assert decision.matched_rules == ("optional", "preferred", "required", "skip")


def test_rule_order_does_not_change_routing_plan() -> None:
    rules = (
        _rule("b", "knowledge-kind-classification", RoutingDisposition.PREFERRED),
        _rule("a", "knowledge-kind-classification", RoutingDisposition.PREFERRED),
        _rule("c", "statement-function-classification", RoutingDisposition.REQUIRED),
    )
    engine = DeterministicRoutingEngine()
    profile = TaxonomySignalProfile()

    first = engine.route(
        profile,
        RoutingContract(id="contract", version="1", rules=rules),
    )
    second = engine.route(
        profile,
        RoutingContract(id="contract", version="1", rules=tuple(reversed(rules))),
    )

    assert first == second


def test_context_hints_come_only_from_winning_rules_and_are_deterministic() -> None:
    contract = RoutingContract(
        id="contract",
        version="1",
        rules=(
            _rule(
                "z-preferred",
                "role-relation-extraction",
                RoutingDisposition.PREFERRED,
                context_hints={"heading": "verification", "source": "z"},
            ),
            _rule(
                "a-preferred",
                "role-relation-extraction",
                RoutingDisposition.PREFERRED,
                context_hints={"source": "a", "phase": "verification"},
            ),
            _rule(
                "optional",
                "role-relation-extraction",
                RoutingDisposition.OPTIONAL,
                context_hints={"ignored": "true"},
            ),
        ),
    )

    decision = (
        DeterministicRoutingEngine()
        .route(
            TaxonomySignalProfile(),
            contract,
        )
        .decision_for("role-relation-extraction")
    )

    assert decision is not None
    assert decision.context_hints == {
        "heading": "verification",
        "phase": "verification",
        "source": "a",
    }
    assert decision.reasons == (
        "contract_rule:a-preferred",
        "contract_rule:z-preferred",
    )


def test_contract_rejects_duplicate_rule_ids() -> None:
    with pytest.raises(ValueError, match="rule ids must be unique"):
        RoutingContract(
            id="contract",
            version="1",
            rules=(
                _rule("duplicate", "task-a", RoutingDisposition.REQUIRED),
                _rule("duplicate", "task-b", RoutingDisposition.REQUIRED),
            ),
        )


def test_contract_rejects_rules_for_undeclared_tasks() -> None:
    with pytest.raises(ValueError, match="undeclared tasks: task-b"):
        RoutingContract(
            id="contract",
            version="1",
            tasks=(RoutingTaskReference(id="task-a", version="1"),),
            rules=(_rule("rule", "task-b", RoutingDisposition.REQUIRED),),
        )
