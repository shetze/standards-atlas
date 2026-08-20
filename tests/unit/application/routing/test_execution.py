from standards_atlas.application.routing import (
    RoutingDecision,
    RoutingDisposition,
    RoutingExecutionPolicy,
)


def test_execution_policy_respects_disposition_threshold() -> None:
    policy = RoutingExecutionPolicy(minimum_disposition=RoutingDisposition.PREFERRED)

    assert policy.allows(RoutingDecision(task="x", disposition=RoutingDisposition.REQUIRED))
    assert policy.allows(RoutingDecision(task="x", disposition=RoutingDisposition.PREFERRED))
    assert not policy.allows(RoutingDecision(task="x", disposition=RoutingDisposition.OPTIONAL))
    assert not policy.allows(RoutingDecision(task="x", disposition=RoutingDisposition.SKIP))


def test_execution_policy_does_not_execute_unrouted_tasks_by_default() -> None:
    assert not RoutingExecutionPolicy().allows(None)
    assert RoutingExecutionPolicy(include_unrouted=True).allows(None)
