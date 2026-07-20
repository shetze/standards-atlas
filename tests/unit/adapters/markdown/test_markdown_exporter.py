from standards_atlas.adapters.markdown import MarkdownExporter
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    ListBlock,
    ListItem,
    SemanticRole,
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
        semantic_roles=roles,
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
                _clause("F", "Foreword", roles=(SemanticRole.FOREWORD,)),
                _clause("I", "Introduction", roles=(SemanticRole.INTRODUCTION,)),
                _clause("1", "Scope"),
            )
        }
    )

    rendered = MarkdownExporter().render(document)

    assert "Foreword" not in rendered
    assert "Introduction" not in rendered
    assert "1 Scope" in rendered
