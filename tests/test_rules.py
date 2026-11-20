import pytest
from pydantic import ValidationError

from rules import DEFAULT_POLICY_PATH, Outcome, Policy, RuleInput, evaluate, load_policy

POLICY = load_policy(DEFAULT_POLICY_PATH)


def decide(resource_type="laptop", justification="needed for daily work", cost=10.0):
    return evaluate(POLICY, RuleInput(resource_type=resource_type,
                                      justification=justification, estimated_cost=cost))


@pytest.mark.parametrize("cost,justification,rule,outcome", [
    (49.99, "needed for daily work", "low-cost", Outcome.AUTO_APPROVE),
    (50.0, "needed for daily work", "default", Outcome.REQUIRE_MANAGER),   # max_cost is exclusive
    (10.0, "short", "insufficient-justification", Outcome.REQUIRE_MANAGER),
    (10.0, "   padded   ", "insufficient-justification", Outcome.REQUIRE_MANAGER),  # stripped
    (5000.0, "needed for daily work", "budget-cap", Outcome.AUTO_REJECT),   # min_cost inclusive
    (4999.99, "needed for daily work", "default", Outcome.REQUIRE_MANAGER),
])
def test_cost_and_justification_boundaries(cost, justification, rule, outcome):
    d = decide(cost=cost, justification=justification)
    assert (d.rule_id, d.outcome) == (rule, outcome)


def test_privileged_access_overrides_low_cost():
    d = decide(resource_type="prod-access", cost=0)
    assert (d.rule_id, d.outcome) == ("privileged-access", Outcome.REQUIRE_MANAGER)


def test_resource_specific_rule():
    assert decide(resource_type="software-license", cost=150).rule_id == "standard-software"
    assert decide(resource_type="software-license", cost=200).rule_id == "default"


def test_budget_cap_beats_everything():
    assert decide(resource_type="prod-access", justification="x", cost=9999).rule_id == "budget-cap"


def test_policy_rejects_duplicate_ids():
    rule = {"id": "a", "description": "d", "outcome": "auto_approve"}
    with pytest.raises(ValidationError, match="duplicate rule ids"):
        Policy.model_validate({"version": 1, "rules": [rule, rule]})


def test_policy_rejects_unknown_condition():
    with pytest.raises(ValidationError):
        Policy.model_validate({"version": 1, "rules": [
            {"id": "a", "description": "d", "when": {"max_price": 5}, "outcome": "auto_approve"}]})
