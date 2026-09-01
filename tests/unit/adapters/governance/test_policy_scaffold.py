from pathlib import Path

import yaml

from standards_atlas.adapters.governance import (
    GovernanceCandidateAnalyzer,
    GovernancePolicyScaffoldExporter,
)
from standards_atlas.application.model import PublicationDocument
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    GovernanceSelectionProfile,
    KnowledgeKind,
    NormativeStatus,
    ProcessFunction,
    SemanticClassification,
    StandardReference,
    StatementFunction,
)
from standards_atlas.domain.model.content import TextBlock


def _clause(
    clause_id: str,
    clause_ref: str,
    *,
    process: tuple[ProcessFunction, ...] = (),
    knowledge: tuple[KnowledgeKind, ...] = (),
) -> Clause:
    return Clause(
        id=ClauseId(value=clause_id),
        reference=StandardReference(standard="EN50716", year=2023, clause=clause_ref),
        clause_type=ClauseType.REQUIREMENT,
        content=(TextBlock(id=f"{clause_id}-text", text="The software shall be verified."),),
        normative_status=NormativeStatus.NORMATIVE,
        semantic_classification=SemanticClassification(
            statement_functions=(StatementFunction.REQUIREMENT,),
            process_functions=process,
            knowledge_kinds=knowledge,
        ),
    )


def _document(*clauses: Clause) -> PublicationDocument:
    return PublicationDocument(
        key=DocumentKey(value="EN50716"),
        title="EN 50716",
        year=2023,
        clauses=clauses,
    )


def _profile(*, request_knowledge: bool = False) -> GovernanceSelectionProfile:
    selection = {"process-functions": ["activity"]}
    if request_knowledge:
        selection["knowledge-kinds"] = ["evidence"]
    return GovernanceSelectionProfile.model_validate(
        {
            "id": "rail-onboard-sil2",
            "version": "1.0.0",
            "description": "Rail onboard SIL 2 policy",
            "context": {
                "domain": "railway",
                "system-types": ["onboard-software", "linux"],
                "lifecycle-phases": ["software-development"],
                "integrity-levels": ["SIL-2"],
                "roles": ["verifier"],
                "attributes": {"automation-level": "GoA4"},
            },
            "standards": {"include": ["EN50716"]},
            "selection": selection,
        }
    )


def test_policy_scaffold_imports_catalogs_and_selected_guidance(tmp_path: Path) -> None:
    document = _document(_clause("c1", "5.1", process=(ProcessFunction.ACTIVITY,)))
    profile = _profile()
    analysis = GovernanceCandidateAnalyzer().analyze(profile, (document,))

    policy_path, manifest_path = GovernancePolicyScaffoldExporter().export(
        profile,
        analysis,
        (document,),
        tmp_path / "policy.yaml",
        responsible=("Rail Safety Engineering",),
        accountable=("Project Safety Manager",),
    )

    payload = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    assert payload["metadata"]["type"] == "Policy"
    assert payload["metadata"]["gemara-version"] == "1.1.0"
    assert payload["metadata"]["draft"] is True
    assert payload["contacts"]["responsible"][0]["name"] == "Rail Safety Engineering"
    assert payload["scope"]["in"]["technologies"] == ["onboard-software", "linux"]
    assert "domain:railway" in payload["scope"]["in"]["groups"]
    assert payload["imports"]["catalogs"][0]["reference-id"] == "en50716-controls"
    assert payload["imports"]["guidance"][0]["reference-id"] == "en50716"
    assert payload["adherence"] == {}
    assert manifest_path.exists()


def test_policy_scaffold_rejects_undetermined_by_default(tmp_path: Path) -> None:
    document = _document(_clause("c1", "5.1", process=(ProcessFunction.ACTIVITY,)))
    profile = _profile(request_knowledge=True)
    analysis = GovernanceCandidateAnalyzer().analyze(profile, (document,))

    try:
        GovernancePolicyScaffoldExporter().export(
            profile,
            analysis,
            (document,),
            tmp_path / "policy.yaml",
            responsible=("Rail Safety Engineering",),
            accountable=("Project Safety Manager",),
        )
    except ValueError as exc:
        assert "undetermined controls" in str(exc)
    else:
        raise AssertionError("expected undetermined candidates to block policy scaffold")


def test_withheld_undetermined_are_excluded_and_documented(tmp_path: Path) -> None:
    import json

    document = _document(_clause("c1", "5.1", process=(ProcessFunction.ACTIVITY,)))
    profile = _profile(request_knowledge=True)
    analysis = GovernanceCandidateAnalyzer().analyze(profile, (document,))

    policy_path, manifest_path = GovernancePolicyScaffoldExporter().export(
        profile,
        analysis,
        (document,),
        tmp_path / "policy.yaml",
        responsible=("Rail Safety Engineering",),
        accountable=("Project Safety Manager",),
        withhold_undetermined=True,
    )

    payload = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    excluded = payload["imports"]["catalogs"][0]["exclusions"]
    assert analysis.candidates[0].control_id in excluded
    assert analysis.candidates[0].control_id in manifest["withheld-controls"]
    assert manifest["withheld-reasons"][analysis.candidates[0].control_id]


def test_policy_scaffold_is_deterministic(tmp_path: Path) -> None:
    document = _document(_clause("c1", "5.1", process=(ProcessFunction.ACTIVITY,)))
    profile = _profile()
    analysis = GovernanceCandidateAnalyzer().analyze(profile, (document,))
    exporter = GovernancePolicyScaffoldExporter()

    first, _ = exporter.export(
        profile,
        analysis,
        (document,),
        tmp_path / "first.yaml",
        responsible=("Rail Safety Engineering",),
        accountable=("Project Safety Manager",),
    )
    second, _ = exporter.export(
        profile,
        analysis,
        (document,),
        tmp_path / "second.yaml",
        responsible=("Rail Safety Engineering",),
        accountable=("Project Safety Manager",),
    )

    assert first.read_bytes() == second.read_bytes()
