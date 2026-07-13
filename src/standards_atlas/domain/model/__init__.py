"""Domain model exports."""

from standards_atlas.domain.model.clause import Clause, ClauseType
from standards_atlas.domain.model.content import (
    ContentBlock,
    FormulaBlock,
    ListBlock,
    ListItem,
    NoteBlock,
    PictureBlock,
    TableBlock,
    TableCell,
    TableRow,
    TextBlock,
    render_content_as_plain_text,
)
from standards_atlas.domain.model.source_evidence import (
    BoundingBox,
    CoordinateOrigin,
    SourceEvidence,
)
from standards_atlas.domain.model.annotation import (
    AnnotationType,
    AnnotationVisibility,
    ClauseAnnotation,
)
from standards_atlas.domain.model.identifiers import (
    AnnotationId,
    ClauseId,
    DocumentKey,
    StandardKey,
    StandardReference,
)
from standards_atlas.domain.model.document import DocumentType, EngineeringDocument
from standards_atlas.domain.model.relation import Relation, RelationType
from standards_atlas.domain.model.standard import Standard
from standards_atlas.domain.model.semantic_role import SemanticRole
from standards_atlas.domain.model.doorstop_attributes import (
    DoorstopItemAttributes,
    DoorstopReference,
)

__all__ = [
    "AnnotationId",
    "AnnotationType",
    "AnnotationVisibility",
    "Clause",
    "ClauseAnnotation",
    "ClauseId",
    "ClauseType",
    "ContentBlock",
    "CoordinateOrigin",
    "DocumentKey",
    "BoundingBox",
    "DocumentType",
    "DoorstopItemAttributes",
    "DoorstopReference",
    "EngineeringDocument",
    "FormulaBlock",
    "ListBlock",
    "ListItem",
    "NoteBlock",
    "PictureBlock",
    "Relation",
    "RelationType",
    "SemanticRole",
    "Standard",
    "StandardKey",
    "StandardReference",
    "SourceEvidence",
    "TableBlock",
    "TableCell",
    "TableRow",
    "TextBlock",
    "render_content_as_plain_text",
]
