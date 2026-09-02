"""Safe compilation of editable packaged prompt templates."""

from __future__ import annotations

from collections.abc import Mapping
from string import Formatter
from typing import Any

from standards_atlas.application.evaluation.models import PromptDefinition
from standards_atlas.application.evaluation.schema import validate_schema_definition
from standards_atlas.application.prompt_workbench.models import (
    AssembledPromptContext,
    CompiledPrompt,
)


class PromptCompilationError(ValueError):
    """Raised when an editable prompt cannot be rendered deterministically."""


class PromptCompiler:
    """Compile a prompt definition with explicit, audited template variables."""

    def placeholders(self, template: str) -> tuple[str, ...]:
        fields: list[str] = []
        try:
            parsed = Formatter().parse(template)
            for _, field_name, _, _ in parsed:
                if not field_name:
                    continue
                if any(token in field_name for token in (".", "[", "]")):
                    raise PromptCompilationError(
                        f"complex template field {field_name!r} is not supported"
                    )
                if field_name not in fields:
                    fields.append(field_name)
        except ValueError as exc:
            raise PromptCompilationError(
                f"invalid user template: {exc}; escape literal braces as '{{{{' and '}}}}'"
            ) from exc
        return tuple(fields)

    def compile(
        self,
        definition: PromptDefinition,
        context: AssembledPromptContext,
        *,
        system_prompt: str | None = None,
        user_template: str | None = None,
        output_schema: Mapping[str, Any] | None = None,
    ) -> CompiledPrompt:
        resolved_system = definition.system_prompt if system_prompt is None else system_prompt
        resolved_template = definition.user_template if user_template is None else user_template
        resolved_schema = definition.output_schema if output_schema is None else output_schema
        if not resolved_system.strip():
            raise PromptCompilationError("system prompt must not be empty")
        if not resolved_template.strip():
            raise PromptCompilationError("user template must not be empty")
        validate_schema_definition(resolved_schema)

        placeholders = self.placeholders(resolved_template)
        unknown = tuple(item for item in placeholders if item not in context.values)
        if unknown:
            raise PromptCompilationError(
                "prompt references unavailable template variables: " + ", ".join(unknown)
            )
        try:
            user_prompt = resolved_template.format_map(dict(context.values))
        except (KeyError, ValueError) as exc:
            raise PromptCompilationError(f"could not render user template: {exc}") from exc
        return CompiledPrompt(
            definition=definition,
            system_prompt=resolved_system,
            user_prompt=user_prompt,
            output_schema=dict(resolved_schema),
            placeholders=placeholders,
            context=context,
        )
