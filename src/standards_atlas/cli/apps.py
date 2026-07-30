"""Typer application tree for the Standards Atlas CLI."""

import typer

app = typer.Typer(
    name="standards-atlas",
    help="Semantic traceability platform for technical standards.",
    no_args_is_help=True,
)
inspect_app = typer.Typer(
    help="Inspect Standards Atlas artifacts for debugging and development.", no_args_is_help=True
)
atlasdata_app = typer.Typer(help="Work with legacy AtlasData files.", no_args_is_help=True)
document_app = typer.Typer(
    help="Import, transform, and persist engineering documents.", no_args_is_help=True
)
docling_app = typer.Typer(
    help="Convert and inspect private PDF extraction artefacts with Docling.", no_args_is_help=True
)
normalize_app = typer.Typer(
    help="Normalize extracted documents before semantic alignment.", no_args_is_help=True
)
reference_app = typer.Typer(
    help="Detect and inspect clause-reference candidates.", no_args_is_help=True
)
align_app = typer.Typer(
    help="Align reference candidates with the AtlasData document structure.", no_args_is_help=True
)
document_export_app = typer.Typer(
    help="Export persisted engineering documents.", no_args_is_help=True
)
catalog_app = typer.Typer(help="Validate and inspect standard catalogs.", no_args_is_help=True)
workflow_app = typer.Typer(
    help="Plan and run catalog-driven end-to-end workflows.", no_args_is_help=True
)
doorstop_app = typer.Typer(
    help="Publish internal hierarchy-based Doorstop projects.", no_args_is_help=True
)
llm_app = typer.Typer(help="Manage the project-owned local LLM server.", no_args_is_help=True)
mcp_app = typer.Typer(
    help="Expose read-only Standards Atlas data through Model Context Protocol.",
    no_args_is_help=True,
)
semantic_evaluation_app = typer.Typer(
    help="Benchmark prompts and models against versioned semantic gold datasets.",
    no_args_is_help=True,
)
evaluation_app = typer.Typer(
    help="Build local corpora and run reproducible evaluation matrices.", no_args_is_help=True
)
qualification_app = typer.Typer(
    help="Execute reproducible qualification checks and persist evidence.", no_args_is_help=True
)

app.add_typer(inspect_app, name="inspect")
app.add_typer(atlasdata_app, name="atlasdata")
app.add_typer(document_app, name="document")
app.add_typer(docling_app, name="docling")
app.add_typer(normalize_app, name="normalize")
app.add_typer(reference_app, name="references")
app.add_typer(align_app, name="align")
document_app.add_typer(document_export_app, name="export")
app.add_typer(catalog_app, name="catalog")
app.add_typer(workflow_app, name="workflow")
app.add_typer(doorstop_app, name="doorstop")
app.add_typer(llm_app, name="llm")
app.add_typer(mcp_app, name="mcp")
app.add_typer(semantic_evaluation_app, name="semantic-evaluation")
app.add_typer(evaluation_app, name="evaluation")
app.add_typer(qualification_app, name="qualification")
