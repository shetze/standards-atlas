"""Domain contracts for deterministic taxonomy-aware semantic routing."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RoutingDisposition(StrEnum):
    """Execution disposition assigned to one semantic task."""

    SKIP = "skip"
    OPTIONAL = "optional"
    PREFERRED = "preferred"
    REQUIRED = "required"


class TaxonomyCategoryScope(StrEnum):
    """Namespace within a structural profile that owns a category signal."""

    DOCUMENT = "document"
    DOMAIN = "domain"


class TaxonomySignalField(StrEnum):
    """Scalar deterministic signals exposed to routing contracts."""

    CANONICAL_SECTION = "canonical_section"
    ANNEX_STATUS = "annex_status"
    NODE_KIND = "node_kind"
    CONTENT_PROFILE = "content_profile"


class TaxonomyCategorySignal(BaseModel):
    """One namespaced category emitted by a structural taxonomy."""

    model_config = ConfigDict(frozen=True)

    taxonomy: str = Field(min_length=1)
    category: str = Field(min_length=1)
    version: str | None = None


class TaxonomySignalProfile(BaseModel):
    """Normalized deterministic evidence available to routing matchers.

    This is intentionally an integration view rather than a taxonomy model. It
    carries only explicit structural signals and never assigns ontology values.
    """

    model_config = ConfigDict(frozen=True)

    canonical_section: str | None = None
    annex_status: str | None = None
    document_categories: tuple[TaxonomyCategorySignal, ...] = ()
    domain_categories: tuple[TaxonomyCategorySignal, ...] = ()
    node_kind: str | None = None
    content_profile: str | None = None
    heading: str = ""

    def scalar(self, field: TaxonomySignalField) -> str | None:
        """Return one scalar signal by its contract-facing field identifier."""

        return getattr(self, field.value)

    def categories(
        self,
        scope: TaxonomyCategoryScope,
    ) -> tuple[TaxonomyCategorySignal, ...]:
        """Return category signals from one explicit taxonomy namespace."""

        if scope is TaxonomyCategoryScope.DOCUMENT:
            return self.document_categories
        return self.domain_categories


class AlwaysMatcher(BaseModel):
    """Matcher that unconditionally selects a route."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["always"] = "always"


class SignalEqualsMatcher(BaseModel):
    """Match one scalar structural signal exactly."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["equals"] = "equals"
    field: TaxonomySignalField
    value: str = Field(min_length=1)


class TaxonomyCategoryMatcher(BaseModel):
    """Match a category owned by a concrete taxonomy namespace."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["category"] = "category"
    scope: TaxonomyCategoryScope
    taxonomy: str = Field(min_length=1)
    category: str = Field(min_length=1)
    version: str | None = None


class HeadingContainsMatcher(BaseModel):
    """Match explicit heading text without interpreting its semantics."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["heading_contains"] = "heading_contains"
    value: str = Field(min_length=1)
    case_sensitive: bool = False


class AllMatcher(BaseModel):
    """Require every nested matcher to match."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["all"] = "all"
    matchers: tuple[RoutingMatcher, ...] = Field(min_length=1)


class AnyMatcher(BaseModel):
    """Require at least one nested matcher to match."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["any"] = "any"
    matchers: tuple[RoutingMatcher, ...] = Field(min_length=1)


class NotMatcher(BaseModel):
    """Invert one nested matcher."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["not"] = "not"
    matcher: RoutingMatcher


RoutingMatcher = Annotated[
    AlwaysMatcher
    | SignalEqualsMatcher
    | TaxonomyCategoryMatcher
    | HeadingContainsMatcher
    | AllMatcher
    | AnyMatcher
    | NotMatcher,
    Field(discriminator="kind"),
]


class RoutingTaxonomyRequirement(BaseModel):
    """One taxonomy identity required by a persisted routing contract."""

    model_config = ConfigDict(frozen=True)

    scope: TaxonomyCategoryScope
    taxonomy: str = Field(min_length=1)
    version: str = Field(min_length=1)


class RoutingTaskReference(BaseModel):
    """One semantic task identity addressable by a routing contract."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    version: str = Field(min_length=1)


class RoutingRule(BaseModel):
    """One deterministic rule connecting taxonomy evidence to a semantic task."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    task: str = Field(min_length=1)
    effect: RoutingDisposition
    when: RoutingMatcher
    context_hints: dict[str, str] = Field(default_factory=dict)


class RoutingContract(BaseModel):
    """In-memory contract evaluated by the deterministic routing engine.

    Persistence, resource discovery, and manifest binding deliberately belong to
    a later slice. Keeping this model resource-agnostic preserves the boundary
    between taxonomy producers and ontology/task consumers.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    taxonomy_requirements: tuple[RoutingTaxonomyRequirement, ...] = ()
    tasks: tuple[RoutingTaskReference, ...] = ()
    rules: tuple[RoutingRule, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_contract(self) -> RoutingContract:
        rule_ids = [rule.id for rule in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("routing contract rule ids must be unique")

        task_ids = [task.id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("routing contract task ids must be unique")
        declared_tasks = set(task_ids)
        if declared_tasks:
            undeclared = sorted({rule.task for rule in self.rules} - declared_tasks)
            if undeclared:
                raise ValueError(
                    "routing contract rules reference undeclared tasks: " + ", ".join(undeclared)
                )

        taxonomy_keys = [(item.scope.value, item.taxonomy) for item in self.taxonomy_requirements]
        if len(taxonomy_keys) != len(set(taxonomy_keys)):
            raise ValueError("routing contract taxonomy requirements must be unique")
        return self


class RoutingDecision(BaseModel):
    """Deterministic decision for one semantic task."""

    model_config = ConfigDict(frozen=True)

    task: str = Field(min_length=1)
    disposition: RoutingDisposition
    reasons: tuple[str, ...] = ()
    matched_rules: tuple[str, ...] = ()
    context_hints: dict[str, str] = Field(default_factory=dict)


class SemanticRoutingPlan(BaseModel):
    """Complete routing result for one taxonomy signal profile."""

    model_config = ConfigDict(frozen=True)

    contract_id: str = Field(min_length=1)
    contract_version: str = Field(min_length=1)
    decisions: tuple[RoutingDecision, ...] = ()

    def decision_for(self, task: str) -> RoutingDecision | None:
        """Resolve one task decision without exposing engine internals."""

        return next((decision for decision in self.decisions if decision.task == task), None)
