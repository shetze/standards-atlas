from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "tests/fixtures/ap02/reference-test-matrix.json"


def _test_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


def test_ap02_reference_matrix_closes_exactly_t01_through_t34_with_real_pytest_nodes() -> None:
    payload = json.loads(MATRIX.read_text(encoding="utf-8"))
    cases = payload["cases"]

    assert payload["contract_id"] == "ap02-structural-reference-matrix-v1"
    assert [case["id"] for case in cases] == [f"T{index:02d}" for index in range(1, 35)]
    assert all(case["intent"] and case["tests"] for case in cases)

    for case in cases:
        for node_id in case["tests"]:
            relative_path, separator, function_name = node_id.partition("::")
            assert separator, f"{case['id']} must use an exact pytest function node: {node_id}"
            test_path = ROOT / relative_path
            assert test_path.is_file(), f"{case['id']} points to missing test file: {relative_path}"
            assert function_name in _test_functions(test_path), (
                f"{case['id']} points to missing pytest function: {node_id}"
            )


def test_model_free_inspection_service_has_no_llm_verifier_or_cascade_dependency() -> None:
    source = (
        ROOT / "src/standards_atlas/application/knowledge_proposal_extraction/inspection.py"
    ).read_text(encoding="utf-8")

    forbidden = (
        "adapters.llm",
        "llm_gateway",
        "AssertionQualificationCascadeService",
        "AssertionProposalVerifier",
        "KnowledgeProposalExtractor",
        "embedding",
    )
    assert all(token not in source for token in forbidden)
