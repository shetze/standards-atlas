import json
from pathlib import Path

import pytest

from standards_atlas.cli.composition import build_golden_corpus_qualifier

pytestmark = pytest.mark.qualification

CORPUS = Path("tests/golden_corpus")
REQUIRED_FEATURES = {
    "simple_clause",
    "multi_page_clause",
    "header",
    "footer",
    "table",
    "picture",
    "formula",
    "list",
    "split_heading",
    "hyphenation",
    "annex",
    "multilingual_pages",
    "multipart_standard",
    "malformed_docling",
    "real_excerpt",
}


def test_versioned_golden_corpus_passes() -> None:
    report = build_golden_corpus_qualifier().run(CORPUS)
    assert report.passed, {case.case_id: case.failures for case in report.cases if not case.passed}


def test_corpus_covers_required_edge_case_features() -> None:
    index = json.loads((CORPUS / "corpus.json").read_text(encoding="utf-8"))
    covered: set[str] = set()
    for case_id in index["cases"]:
        manifest = json.loads(
            (CORPUS / "cases" / case_id / "manifest.json").read_text(encoding="utf-8")
        )
        covered.update(manifest["features"])
    assert REQUIRED_FEATURES <= covered


def test_corpus_contains_snapshots_and_invariant_only_cases() -> None:
    index = json.loads((CORPUS / "corpus.json").read_text(encoding="utf-8"))
    manifests = [
        json.loads((CORPUS / "cases" / case_id / "manifest.json").read_text(encoding="utf-8"))
        for case_id in index["cases"]
    ]
    assert any(manifest.get("expected_artifact") for manifest in manifests)
    assert any(not manifest.get("expected_artifact") for manifest in manifests)
