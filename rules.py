"""Declarative policy engine.

Rules live in a YAML file (see policy.yaml) and are evaluated top to bottom;
the first rule whose conditions all match decides the outcome. If nothing
matches, the policy's default outcome applies. The matching rule id and its
reason are stored on the request so every decision can be explained later.
"""

import enum
import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_POLICY_PATH = Path(__file__).with_name("policy.yaml")


class Outcome(str, enum.Enum):
    AUTO_APPROVE = "auto_approve"
    AUTO_REJECT = "auto_reject"
    REQUIRE_MANAGER = "require_manager"


class Conditions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_types: list[str] | None = None
    min_cost: float | None = Field(None, description="inclusive: cost >= min_cost")
    max_cost: float | None = Field(None, description="exclusive: cost < max_cost")
    min_justification_length: int | None = None
    max_justification_length: int | None = Field(None, description="inclusive")

    def matches(self, request: "RuleInput") -> bool:
        if self.resource_types is not None and request.resource_type not in self.resource_types:
            return False
        if self.min_cost is not None and request.estimated_cost < self.min_cost:
            return False
        if self.max_cost is not None and request.estimated_cost >= self.max_cost:
            return False
        length = len(request.justification.strip())
        if self.min_justification_length is not None and length < self.min_justification_length:
            return False
        if self.max_justification_length is not None and length > self.max_justification_length:
            return False
        return True


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    when: Conditions = Field(default_factory=Conditions)
    outcome: Outcome


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    default_outcome: Outcome = Outcome.REQUIRE_MANAGER
    rules: list[Rule]

    @model_validator(mode="after")
    def _unique_ids(self):
        ids = [r.id for r in self.rules]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate rule ids: {sorted(dupes)}")
        return self


class RuleInput(BaseModel):
    resource_type: str
    justification: str
    estimated_cost: float


class Decision(BaseModel):
    outcome: Outcome
    rule_id: str
    reason: str


def load_policy(path: str | Path | None = None) -> Policy:
    path = Path(path or os.getenv("POLICY_PATH") or DEFAULT_POLICY_PATH)
    with open(path, encoding="utf-8") as f:
        return Policy.model_validate(yaml.safe_load(f))


def evaluate(policy: Policy, request: RuleInput) -> Decision:
    for rule in policy.rules:
        if rule.when.matches(request):
            return Decision(outcome=rule.outcome, rule_id=rule.id, reason=rule.description)
    return Decision(
        outcome=policy.default_outcome,
        rule_id="default",
        reason="no policy rule matched; falling back to default outcome",
    )
