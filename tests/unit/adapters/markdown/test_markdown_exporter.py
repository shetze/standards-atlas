from standards_atlas.adapters.markdown import MarkdownExporter
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentStructure,
    DocumentStructureClassification,
    FormulaBlock,
    ListBlock,
    ListItem,
    PictureBlock,
    SemanticClassification,
    Standard,
    StandardKey,
    StandardReference,
    TableBlock,
    TableCell,
    TableRow,
    TextBlock,
)


def _clause(reference: str, title: str, *, roles=(), text: str | None = None) -> Clause:
    return Clause(
        id=ClauseId(value=f"clause-{reference.replace('.', '-') or 'empty'}"),
        reference=StandardReference(standard="SAMPLE", year=2026, clause=reference),
        clause_type=ClauseType.CLAUSE,
        semantic_classification=(
            SemanticClassification(
                document_structure=DocumentStructureClassification(
                    family="iso_iec_standard", category=roles[0]
                )
            )
            if roles
            else SemanticClassification()
        ),
        title=title,
        content=(TextBlock(id=f"p-{reference}", text=text),) if text else (),
    )


def test_renders_structured_document_as_markdown():
    document = Standard.from_name(key=StandardKey(value="SAMPLE"), name="Sample", year=2026)
    document = document.model_copy(
        update={
            "clauses": (
                Clause(
                    id=ClauseId(value="scope"),
                    reference=StandardReference(standard="SAMPLE", year=2026, clause="1"),
                    clause_type=ClauseType.SCOPE,
                    title="Scope",
                    content=(TextBlock(id="p1", text="Applies here."),),
                ),
                Clause(
                    id=ClauseId(value="req"),
                    reference=StandardReference(standard="SAMPLE", year=2026, clause="4.1"),
                    clause_type=ClauseType.REQUIREMENT,
                    title="Requirements",
                    content=(
                        ListBlock(id="l1", ordered=False, items=(ListItem(text="First"),)),
                        TableBlock(
                            id="t1",
                            rows=(
                                TableRow(cells=(TableCell(text="A"), TableCell(text="B"))),
                                TableRow(cells=(TableCell(text="1"), TableCell(text="2"))),
                            ),
                        ),
                    ),
                ),
            )
        }
    )

    rendered = MarkdownExporter().render(document)

    assert rendered.startswith("# Sample\n")
    assert "## Contents" in rendered
    assert "- [1 Scope](#clause-1)" in rendered
    assert "  - [4.1 Requirements](#clause-4-1)" in rendered
    assert '<a id="clause-1"></a>\n## 1 Scope' in rendered
    assert '<a id="clause-4-1"></a>\n### 4.1 Requirements' in rendered
    assert "- First" in rendered
    assert "| A | B |" in rendered


def test_sorts_clauses_into_depth_first_standard_order():
    document = Standard.from_name(key=StandardKey(value="SAMPLE"), name="Sample", year=2026)
    document = document.model_copy(
        update={
            "clauses": (
                _clause("1", "Scope"),
                _clause("2", "Normative references"),
                _clause("3", "Terms"),
                _clause("1.1", "Purpose"),
                _clause("1.10", "Limits"),
                _clause("1.2", "Application"),
                _clause("3.1", "Definitions"),
            )
        }
    )

    rendered = MarkdownExporter().render(document)

    positions = [
        rendered.index(f">\n{heading}") if False else rendered.index(heading)
        for heading in (
            "## 1 Scope",
            "### 1.1 Purpose",
            "### 1.2 Application",
            "### 1.10 Limits",
            "## 2 Normative references",
            "## 3 Terms",
            "### 3.1 Definitions",
        )
    ]
    assert positions == sorted(positions)


def test_toc_stops_after_four_clause_levels():
    document = Standard.from_name(key=StandardKey(value="SAMPLE"), name="Sample", year=2026)
    document = document.model_copy(
        update={
            "clauses": (
                _clause("4", "Lifecycle"),
                _clause("4.1", "Development"),
                _clause("4.1.1", "Design"),
                _clause("4.1.1.1", "Detailed design"),
                _clause("4.1.1.1.1", "Deep detail"),
            )
        }
    )

    rendered = MarkdownExporter().render(document)
    toc = rendered.split("## Contents", 1)[1].split('<a id="clause-4"></a>', 1)[0]

    assert "[4.1.1.1 Detailed design](#clause-4-1-1-1)" in toc
    assert "Deep detail" not in toc
    assert "###### 4.1.1.1.1 Deep detail" in rendered


def test_omits_foreword_and_introduction_roles():
    document = Standard.from_name(key=StandardKey(value="SAMPLE"), name="Sample", year=2026)
    document = document.model_copy(
        update={
            "clauses": (
                _clause("F", "Foreword", roles=(DocumentStructure.FOREWORD,)),
                _clause("I", "Introduction", roles=(DocumentStructure.INTRODUCTION,)),
                _clause("1", "Scope"),
            )
        }
    )

    rendered = MarkdownExporter().render(document)

    assert "Foreword" not in rendered
    assert "Introduction" not in rendered
    assert "1 Scope" in rendered


def test_export_materializes_embedded_picture_asset(tmp_path):
    import base64
    import hashlib

    payload = b"png-payload"
    data_uri = "data:image/png;base64," + base64.b64encode(payload).decode("ascii")
    digest = hashlib.sha256(data_uri.encode("utf-8")).hexdigest()
    document = Standard.from_name(key=StandardKey(value="SAMPLE"), name="Sample", year=2026)
    document = document.model_copy(
        update={
            "clauses": (
                Clause(
                    id=ClauseId(value="figure"),
                    reference=StandardReference(standard="SAMPLE", year=2026, clause="1"),
                    clause_type=ClauseType.CLAUSE,
                    title="Figure",
                    content=(
                        PictureBlock(
                            id="p1",
                            caption="Figure 1 — Architecture",
                            media_type="image/png",
                            content_hash=digest,
                            embedded_data_uri=data_uri,
                        ),
                    ),
                ),
            )
        }
    )
    target = tmp_path / "sample.md"

    MarkdownExporter().export_document(document, target)

    asset = tmp_path / "assets" / f"{digest}.png"
    assert asset.read_bytes() == payload
    assert f"![Figure 1 — Architecture](assets/{digest}.png)" in target.read_text()


def test_visual_only_formula_is_not_presented_as_verified_semantics():
    document = Standard.from_name(key=StandardKey(value="SAMPLE"), name="Sample", year=2026)
    document = document.model_copy(
        update={
            "clauses": (
                Clause(
                    id=ClauseId(value="formula"),
                    reference=StandardReference(standard="SAMPLE", year=2026, clause="1"),
                    clause_type=ClauseType.CLAUSE,
                    title="Formula",
                    content=(
                        FormulaBlock(
                            id="f1",
                            expression="1 MUT A MUT MDT = <= +",
                            original_expression="1 MUT A MUT MDT = <= +",
                            extraction_status="visual_only",
                        ),
                    ),
                ),
            )
        }
    )

    rendered = MarkdownExporter().render(document)

    assert "semantic transcription unavailable" in rendered
    assert "1 MUT A MUT MDT = <= +" not in rendered
    assert "$$" not in rendered


def test_nested_lists_use_each_child_marker_kind() -> None:
    document = Standard.from_name(
        key=StandardKey(value="SAMPLE"),
        name="Sample",
        year=2026,
    )
    document = document.model_copy(
        update={
            "clauses": (
                Clause(
                    id=ClauseId(value="list-clause"),
                    reference=StandardReference(standard="SAMPLE", year=2026, clause="1"),
                    clause_type=ClauseType.CLAUSE,
                    title="List",
                    content=(
                        ListBlock(
                            id="list",
                            ordered=True,
                            items=(
                                ListItem(
                                    text="Parent",
                                    ordered=True,
                                    children=(ListItem(text="Child", ordered=False),),
                                ),
                            ),
                        ),
                    ),
                ),
            )
        }
    )

    rendered = MarkdownExporter().render(document)

    assert "1. Parent\n  - Child" in rendered


def test_export_writes_lineage_manifest(tmp_path):
    from standards_atlas.domain.model import ArtifactLineage, artifact_reference

    document = Standard.from_name(
        key=StandardKey(value="SAMPLE"),
        name="Sample",
        year=2026,
    )
    document = document.model_copy(
        update={
            "lineage": ArtifactLineage(
                artifact=artifact_reference("engineering_document", document)
            )
        }
    )
    target = tmp_path / "sample.md"

    MarkdownExporter().export_document(document, target)

    assert target.with_suffix(".md.lineage.json").exists()


def test_internal_reference_relations_are_rendered_as_links():
    from standards_atlas.domain.model import (
        RelationScope,
        SemanticClassification,
        SemanticRelation,
        SemanticRelationKind,
    )

    document = Standard.from_name(key=StandardKey(value="SAMPLE"), name="Sample", year=2026)
    source = _clause("4.1", "Source", text="The procedure in 5.2 shall be applied.")
    source = source.model_copy(
        update={
            "semantic_classification": SemanticClassification(
                relations=(
                    SemanticRelation(
                        kind=SemanticRelationKind.NORMATIVE_REFERENCE,
                        scope=RelationScope.INTERNAL,
                        target_reference="5.2",
                    ),
                )
            )
        }
    )
    document = document.model_copy(
        update={"clauses": (source, _clause("5.2", "Target", text="Target text."))}
    )

    rendered = MarkdownExporter().render(document)

    assert "The procedure in [5.2](#clause-5-2) shall be applied." in rendered


def test_visual_only_formula_asset_is_materialized_and_rendered(tmp_path):
    import base64
    import hashlib

    payload = b"formula-png"
    digest = hashlib.sha256(payload).hexdigest()
    data_uri = "data:image/png;base64," + base64.b64encode(payload).decode("ascii")
    document = Standard.from_name(key=StandardKey(value="SAMPLE"), name="Sample", year=2026)
    document = document.model_copy(
        update={
            "clauses": (
                Clause(
                    id=ClauseId(value="formula-visual"),
                    reference=StandardReference(standard="SAMPLE", year=2026, clause="1"),
                    clause_type=ClauseType.CLAUSE,
                    title="Formula",
                    content=(
                        FormulaBlock(
                            id="f1",
                            expression="",
                            extraction_status="visual_only",
                            media_type="image/png",
                            content_hash=digest,
                            embedded_data_uri=data_uri,
                        ),
                    ),
                ),
            )
        }
    )
    target = tmp_path / "sample.md"

    MarkdownExporter().export_document(document, target)

    asset = tmp_path / "assets" / f"{digest}.png"
    assert asset.read_bytes() == payload
    rendered = target.read_text(encoding="utf-8")
    assert f"![Formula](assets/{digest}.png)" in rendered
    assert "semantic transcription unavailable" in rendered
