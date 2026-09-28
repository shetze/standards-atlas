from __future__ import annotations

from pathlib import Path

from standards_atlas.application.assertion_qualification import (
    AssertionAutoAdoptionReport,
    AssertionQualificationCascadeReport,
    AssertionQualificationReport,
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src/standards_atlas/application/assertion_qualification"


def test_assertion_qualification_is_proposal_only_and_has_no_adoption_boundary() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in PACKAGE.glob("*.py"))
    assert "DocumentKnowledge(" not in source
    assert "KnowledgeAdoption" not in source
    assert "semantic_qualification" not in source


def test_slice_7a_report_is_metric_only_without_acceptance_policy() -> None:
    fields = set(AssertionQualificationReport.model_fields)
    assert "passed" not in fields
    assert "accepted" not in fields
    assert "threshold" not in fields
    assert "adoption" not in fields


def test_slice_7b_cascade_report_has_no_acceptance_or_adoption_policy() -> None:
    fields = set(AssertionQualificationCascadeReport.model_fields)
    assert "passed" not in fields
    assert "accepted_assertions" not in fields
    assert "threshold" not in fields
    assert "adoption" not in fields


def test_slice_7c_auto_adoption_report_is_eligibility_only() -> None:
    fields = set(AssertionAutoAdoptionReport.model_fields)
    assert "adopted_assertions" not in fields
    assert "document_knowledge" not in fields
    assert "canonical_knowledge" not in fields
    assert "engineering_document" not in fields
    assert "auto_adoption_eligible_assertions" in fields
    assert "qualification_gate_passed" in fields


def test_offline_assertion_cli_does_not_eagerly_import_llm_adapters() -> None:
    import ast

    path = ROOT / "src/standards_atlas/cli/commands/evaluation_commands/assertion_qualification.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.ImportFrom)
        and (node.module or "").startswith("standards_atlas.adapters.llm")
        for node in tree.body
    )


def test_evaluation_and_projection_never_construct_a_productive_proposal() -> None:
    import ast

    for name in ("evaluation.py", "projection.py", "matching.py", "audit.py"):
        tree = ast.parse((PACKAGE / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "DocumentKnowledgeProposal"


def test_offline_regression_modules_do_not_import_model_or_embedding_infrastructure() -> None:
    import ast

    offline_modules = (
        "audit.py",
        "evaluation.py",
        "io.py",
        "matching.py",
        "projection.py",
        "reporting.py",
        "source_resolution.py",
    )
    forbidden_modules = {
        "standards_atlas.adapters.llm",
        "standards_atlas.application.assertion_qualification.cascade",
    }
    for name in offline_modules:
        tree = ast.parse((PACKAGE / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert module not in forbidden_modules and not module.startswith(
                    "standards_atlas.adapters.llm."
                ), (name, module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in forbidden_modules and not alias.name.startswith(
                        "standards_atlas.adapters.llm."
                    ), (name, alias.name)
        source = (PACKAGE / name).read_text(encoding="utf-8").casefold()
        assert "embedding" not in source, name
