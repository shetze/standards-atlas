"""Compatibility facade for evaluation-related CLI commands."""

import typer

from standards_atlas.cli.commands.evaluation_commands.annotations import (
    evaluate_annotation_metrics,
    export_annotation_reviews,
    extract_clause_references,
    import_annotation_reviews,
    propose_evaluation_annotations,
    publish_annotation_reviews,
)
from standards_atlas.cli.commands.evaluation_commands.benchmark import (
    qualify_golden_corpus,
    run_evaluation_matrix,
    run_semantic_evaluation,
)
from standards_atlas.cli.commands.evaluation_commands.challenger import qualify_challengers
from standards_atlas.cli.commands.evaluation_commands.corpus import (
    build_evaluation_corpus,
    build_role_golden_corpus,
    evaluate_role_corpus,
)
from standards_atlas.cli.commands.evaluation_commands.qualification_archive import (
    finalize_qualification_archive,
)
from standards_atlas.cli.commands.evaluation_commands.qualification_matrix import (
    _format_duration,
    _MatrixProposalProgress,
    qualify_model_prompt_matrix,
)
from standards_atlas.cli.commands.evaluation_commands.semantic_extraction_qualification import (
    qualify_semantic_extraction,
)
from standards_atlas.cli.composition import build_golden_corpus_qualifier

__all__ = [
    "_MatrixProposalProgress",
    "_format_duration",
    "build_evaluation_corpus",
    "build_role_golden_corpus",
    "build_golden_corpus_qualifier",
    "evaluate_annotation_metrics",
    "evaluate_role_corpus",
    "export_annotation_reviews",
    "extract_clause_references",
    "import_annotation_reviews",
    "propose_evaluation_annotations",
    "publish_annotation_reviews",
    "qualify_challengers",
    "qualify_golden_corpus",
    "qualify_model_prompt_matrix",
    "finalize_qualification_archive",
    "qualify_semantic_extraction",
    "run_evaluation_matrix",
    "run_semantic_evaluation",
    "typer",
]
