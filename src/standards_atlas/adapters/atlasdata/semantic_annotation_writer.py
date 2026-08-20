"""Apply reviewed, text-free semantic gold annotations to AtlasData TOC records."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.adapters.atlasdata.parser import (
    InitializationRecord,
    parse_initialization_records,
)
from standards_atlas.adapters.atlasdata.semantic_tags import (
    encode_semantic_tags,
    is_supported_semantic_profile,
)
from standards_atlas.domain.model import (
    ApplicabilityFunction,
    DocumentStructure,
    DocumentStructureClassification,
    KnowledgeKind,
    NormativeStatus,
    ProcessFunction,
    ResponsibilityFunction,
    SemanticClassification,
    StatementFunction,
)

_DATA_MARKER = "#---data---#"


class PublicSemanticAnnotation(BaseModel):
    """One publishable semantic annotation without protected clause content."""

    model_config = ConfigDict(extra="forbid")
    reference: str = Field(min_length=1)
    primary_statement_function: StatementFunction | None = None
    secondary_statement_functions: tuple[StatementFunction, ...] = ()
    knowledge_kinds: tuple[KnowledgeKind, ...] = ()
    process_functions: tuple[ProcessFunction, ...] = ()
    applicability_functions: tuple[ApplicabilityFunction, ...] = ()
    responsibility_functions: tuple[ResponsibilityFunction, ...] = ()
    document_structure: DocumentStructure | None = None
    normative_status: NormativeStatus | None = None

    def classification(self) -> SemanticClassification:
        statements = self.secondary_statement_functions
        if self.primary_statement_function is not None:
            statements = (self.primary_statement_function, *statements)
        return SemanticClassification(
            statement_functions=statements,
            knowledge_kinds=self.knowledge_kinds,
            process_functions=self.process_functions,
            applicability_functions=self.applicability_functions,
            responsibility_functions=self.responsibility_functions,
            document_structure=(
                DocumentStructureClassification(
                    family="public_semantic_annotation",
                    category=self.document_structure,
                )
                if self.document_structure is not None
                else None
            ),
            normative_status=self.normative_status or NormativeStatus.UNSPECIFIED,
        )


class PublicSemanticAnnotationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "1.0"
    semantic_profile: str = Field(min_length=1)
    annotations: tuple[PublicSemanticAnnotation, ...] = ()


@dataclass(frozen=True)
class AtlasDataSemanticAnnotationResult:
    source: Path
    backup: Path | None
    semantic_profile: str
    updated_records: int
    unchanged_records: int
    changed: bool


class AtlasDataSemanticAnnotationService:
    """Persist accepted semantic facts into public AtlasData TOC metadata."""

    def apply(
        self,
        source: Path,
        manifest_path: Path,
        *,
        write: bool = False,
    ) -> AtlasDataSemanticAnnotationResult:
        payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        manifest = PublicSemanticAnnotationManifest.model_validate(payload)
        task, sep, version = manifest.semantic_profile.rpartition(":")
        if not sep or not is_supported_semantic_profile(task):
            raise ValueError(
                "semantic_profile must be semantic-profile-classification:<version> "
                "(legacy statement-function-classification is also accepted)"
            )

        original = source.read_text(encoding="utf-8")
        records = parse_initialization_records(original)
        annotations = {item.reference: item for item in manifest.annotations}
        known_toc = {record.reference for record in records if record.kind == "TOC"}
        missing = sorted(set(annotations) - known_toc)
        if missing:
            raise ValueError(
                "Semantic annotation references not found in TOC: " + ", ".join(missing)
            )

        updated = 0
        unchanged = 0
        merged: list[InitializationRecord] = []
        for record in records:
            annotation = annotations.get(record.reference) if record.kind == "TOC" else None
            if annotation is None:
                merged.append(record)
                continue
            tags = encode_semantic_tags(annotation.classification(), version=version)
            replacement = InitializationRecord(
                kind=record.kind,
                hash_value=record.hash_value,
                reference=record.reference,
                content=record.content,
                type_marker=record.type_marker,
                semantic_tags=tags,
            )
            merged.append(replacement)
            if replacement == record:
                unchanged += 1
            else:
                updated += 1

        rendered = _replace_data_section(
            _set_metadata_field(original, "semanticProfile", manifest.semantic_profile), merged
        )
        changed = rendered != original
        backup = None
        if write and changed:
            backup = _numbered_backup(source)
            source.write_text(rendered, encoding="utf-8")
        return AtlasDataSemanticAnnotationResult(
            source=source,
            backup=backup,
            semantic_profile=manifest.semantic_profile,
            updated_records=updated,
            unchanged_records=unchanged,
            changed=changed,
        )


def _render_record(record: InitializationRecord) -> str:
    base = (
        f"{record.kind};{record.hash_value};{record.reference};"
        f"{record.content};{record.type_marker}"
    )
    return f"{base};{','.join(record.semantic_tags)}" if record.semantic_tags else base


def _replace_data_section(text: str, records: list[InitializationRecord]) -> str:
    head = text.split(_DATA_MARKER, 1)[0].rstrip()
    body = "\n".join(_render_record(record) for record in records)
    return f"{head}\n\n{_DATA_MARKER}\n{body}\n"


def _set_metadata_field(text: str, key: str, value: str) -> str:
    head, marker, data = text.partition(_DATA_MARKER)
    lines = head.rstrip().splitlines()
    prefix = f"{key}="
    replacement = f'{key}="{value}"'
    for index, line in enumerate(lines):
        if line.strip().startswith(prefix):
            lines[index] = replacement
            break
    else:
        structure_index = next(
            (index for index, line in enumerate(lines) if line.strip().startswith("structure=")),
            len(lines),
        )
        lines.insert(structure_index, replacement)
    rebuilt = "\n".join(lines) + "\n\n"
    return rebuilt + (marker + data if marker else "")


def _numbered_backup(source: Path) -> Path:
    counter = 1
    while True:
        backup = source.with_name(f"{source.name}.bak.{counter}")
        if not backup.exists():
            shutil.copy2(source, backup)
            return backup
        counter += 1
