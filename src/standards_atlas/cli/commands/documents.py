"""Compatibility facade for document-related CLI commands."""

from standards_atlas.cli.commands.document_commands.atlasdata import (
    generate_toc,
    onboard_docling,
    onboard_docling_parts,
    set_atlasdata_status,
)
from standards_atlas.cli.commands.document_commands.exports import (
    export_document_to_doorstop,
    export_document_to_markdown,
)
from standards_atlas.cli.commands.document_commands.inspection import inspect_data
from standards_atlas.cli.commands.document_commands.management import (
    compose_family_document,
    derive_document_part,
    derive_document_view,
    enrich_document_content,
    import_document,
)
from standards_atlas.cli.commands.document_commands.publication import (
    publish_doorstop_hierarchy,
)

__all__ = [
    "compose_family_document",
    "derive_document_part",
    "derive_document_view",
    "enrich_document_content",
    "export_document_to_doorstop",
    "export_document_to_markdown",
    "generate_toc",
    "import_document",
    "inspect_data",
    "onboard_docling",
    "onboard_docling_parts",
    "publish_doorstop_hierarchy",
    "set_atlasdata_status",
]
