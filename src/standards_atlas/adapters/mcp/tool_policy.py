"""Single source of truth for server-registered MCP tool names."""

from __future__ import annotations

from standards_atlas.adapters.mcp.configuration import McpServerConfig

GENERAL_SOURCE_TOOLS = (
    "get_server_info",
    "list_standards",
    "get_clause",
    "list_clauses",
    "search_clauses",
    "list_knowledge_tables",
    "get_knowledge_table",
    "list_knowledge_records",
    "get_knowledge_record",
    "list_untranscribed_formulas",
    "get_formula",
    "submit_formula_transcription",
    "sample_clauses",
)

LEGACY_REVIEW_TOOLS = (
    "list_review_packages",
    "get_review_package",
    "list_review_candidates",
    "get_review_case",
    "list_review_cases",
    "submit_review_selection",
    "submit_review_annotations",
)

AP03_DEVELOPMENT_SOURCE_TOOLS = (
    "get_server_info",
    "list_standards",
    "get_clause",
    "list_clauses",
    "search_clauses",
    "sample_clauses",
)

AP03_DEVELOPMENT_REVIEW_TOOLS = (
    "list_review_packages",
    "get_review_package",
    "list_review_cases",
    "get_review_case",
)

AP03_DEVELOPMENT_EXPERIMENT_TOOLS = (
    "list_development_experiments",
    "get_development_experiment_manifest",
    "get_development_experiment_state",
    "get_development_experiment_comparison",
)

# S10 extends this tuple with the controlled prompt-proposal handoff; keeping the policy centralized
# ensures `mcp codex-config` never advertises tools the selected server profile does not register.
AP03_DEVELOPMENT_OPTIMIZATION_TOOLS: tuple[str, ...] = ("submit_prompt_variant_proposal",)


def registered_tool_names(config: McpServerConfig) -> tuple[str, ...]:
    if config.is_ap03_development:
        return (
            *AP03_DEVELOPMENT_SOURCE_TOOLS,
            *AP03_DEVELOPMENT_REVIEW_TOOLS,
            *AP03_DEVELOPMENT_EXPERIMENT_TOOLS,
            *AP03_DEVELOPMENT_OPTIMIZATION_TOOLS,
        )
    tools = list(GENERAL_SOURCE_TOOLS)
    if config.review.enabled:
        tools.extend(LEGACY_REVIEW_TOOLS[:5])
        if config.capabilities.review_preparation:
            tools.extend(LEGACY_REVIEW_TOOLS[5:])
    return tuple(tools)
