"""Architecture guards for non-canonical assertion proposals."""

from __future__ import annotations

import ast
from pathlib import Path

CANONICAL_DOCUMENT = Path("src/standards_atlas/domain/model/document.py")
FORMAL_PROJECTOR = Path("src/standards_atlas/application/formal_semantics/projector.py")
PROPOSAL_MODEL = Path("src/standards_atlas/domain/model/knowledge_proposal.py")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def test_proposal_contract_is_not_embedded_in_canonical_document() -> None:
    imports = _imports(CANONICAL_DOCUMENT)
    assert "standards_atlas.domain.model.knowledge_proposal" not in imports


def test_proposal_contract_has_no_direct_formal_projection_path() -> None:
    imports = _imports(FORMAL_PROJECTOR)
    assert "standards_atlas.domain.model.knowledge_proposal" not in imports


def test_proposal_contract_does_not_define_an_adoption_shortcut() -> None:
    tree = ast.parse(PROPOSAL_MODEL.read_text(encoding="utf-8"), filename=str(PROPOSAL_MODEL))
    document_proposal = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "DocumentKnowledgeProposal"
    )
    method_names = {
        node.name
        for node in document_proposal.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert not method_names & {
        "adopt",
        "to_document_knowledge",
        "to_engineering_document",
        "project",
    }


def test_slice_5c_has_no_legacy_semantic_extraction_contract() -> None:
    legacy_files = (
        Path("src/standards_atlas/domain/model/semantic_extraction.py"),
        Path("src/standards_atlas/application/ports/semantic_extraction.py"),
        Path("src/standards_atlas/adapters/filesystem/semantic_extraction_repository.py"),
        Path("src/standards_atlas/adapters/llm/formal_semantic_extractor.py"),
        Path(
            "src/standards_atlas/application/semantic_qualification/"
            "semantic_extraction_qualification.py"
        ),
        Path(
            "src/standards_atlas/cli/commands/evaluation_commands/"
            "semantic_extraction_qualification.py"
        ),
    )
    legacy_packages = (Path("src/standards_atlas/application/semantic_extraction"),)

    assert all(not path.exists() for path in legacy_files)
    assert all(not any(path.rglob("*.py")) for path in legacy_packages)
