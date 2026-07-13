"""Render Doorstop item files."""

from __future__ import annotations

from pathlib import Path

import yaml

from standards_atlas.adapters.doorstop.models import DoorstopItemModel


class DoorstopItemRenderer:
    """Render Doorstop items as deterministic YAML files."""

    def render(
        self,
        item: DoorstopItemModel,
        target_directory: Path,
    ) -> Path:
        attributes = dict(item.attributes)
        idx = attributes.pop("idx", None)
        standard = attributes.pop("standard", None)

        data = {
            "active": item.active,
            "derived": item.derived,
            "header": item.header,
            "idx": idx,
            "level": item.level,
            "links": list(item.links),
            "normative": item.normative,
            "notes": list(item.notes),
            "rationale": item.rationale,
            "references": [
                reference.model_dump(
                    mode="json",
                    exclude_none=True,
                )
                for reference in item.references
            ],
            "reviewed": item.reviewed,
            "standard": standard,
            "text": item.text,
            **item.attributes,
        }
        data = {
            key: value
            for key, value in data.items()
            if value is not None
        }

        path = target_directory / f"{item.uid}.yml"

        path.write_text(
            yaml.safe_dump(
                data,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            ),
            encoding="utf-8",
        )

        return path
