from __future__ import annotations

import pytest

from standards_atlas.application.evaluation.models import PromptDefinition
from standards_atlas.application.prompt_workbench.compiler import (
    PromptCompilationError,
    PromptCompiler,
)
from standards_atlas.application.prompt_workbench.context import ClausePromptContextAssembler
from standards_atlas.application.semantic_qualification.clause_access import ClauseDescriptor
from standards_atlas.domain.model import ClauseType


def _context():
    clause = ClauseDescriptor(
        id="clause-a",
        document_key="TEST",
        reference="TEST:2026 1",
        clause_reference="1",
        content_hash="sha256:" + "c" * 64,
        clause_type=ClauseType.CLAUSE,
        text="The supplier shall verify the result.",
    )
    return ClausePromptContextAssembler().assemble(clause, variant_id="none")


def _prompt(template: str) -> PromptDefinition:
    return PromptDefinition(
        task="test-task",
        version="1.0.0",
        system_prompt="Return JSON.",
        user_template=template,
        output_schema={"type": "object", "additionalProperties": False, "properties": {}},
    )


def test_compiles_known_variables_and_literal_braces() -> None:
    compiled = PromptCompiler().compile(
        _prompt('Clause: {content}\nExample: {{"value": true}}'), _context()
    )

    assert compiled.placeholders == ("content",)
    assert compiled.user_prompt.endswith('Example: {"value": true}')


def test_rejects_unknown_variable_invalid_braces_and_invalid_schema() -> None:
    compiler = PromptCompiler()
    with pytest.raises(PromptCompilationError, match="unavailable template variables"):
        compiler.compile(_prompt("{unknown}"), _context())
    with pytest.raises(PromptCompilationError, match="escape literal braces"):
        compiler.compile(_prompt("literal { brace"), _context())
    with pytest.raises(ValueError, match="invalid Draft 2020-12 output schema"):
        compiler.compile(_prompt("{content}"), _context(), output_schema={"type": "invalid"})
