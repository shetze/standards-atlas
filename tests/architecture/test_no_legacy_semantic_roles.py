"""Architecture guard for ADR 0051."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src" / "standards_atlas"
FORBIDDEN_TOKENS = (
    "SemanticRole",
    "semantic_roles",
    "semantic-role-classification",
)


def test_legacy_semantic_role_api_is_absent() -> None:
    violations: list[str] = []
    for path in SOURCE_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".json", ".yaml", ".txt"}:
            continue
        content = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_TOKENS:
            if token in content:
                violations.append(f"{path.relative_to(PROJECT_ROOT)}: {token}")
    assert violations == []


def test_legacy_semantic_role_modules_are_removed() -> None:
    removed_paths = (
        SOURCE_ROOT / "domain" / "model" / "semantic_role.py",
        SOURCE_ROOT / "application" / "services" / "semantic_role_classifier.py",
        SOURCE_ROOT / "application" / "ports" / "semantic_role_classifier.py",
        SOURCE_ROOT / "resources" / "semantic" / "tasks" / "semantic-role-classification",
        SOURCE_ROOT / "resources" / "semantic" / "prompts" / "semantic-role-classification",
    )
    assert [str(path.relative_to(PROJECT_ROOT)) for path in removed_paths if path.exists()] == []
