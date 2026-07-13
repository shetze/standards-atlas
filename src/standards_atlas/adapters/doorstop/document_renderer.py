"""Render Doorstop document configuration."""

from __future__ import annotations

from pathlib import Path

import yaml

from standards_atlas.adapters.doorstop.models import DoorstopDocumentModel


class DoorstopDocumentRenderer:
    """Render .doorstop.yml."""

    def render(self, model: DoorstopDocumentModel) -> Path:
        settings = {
            "digits": model.digits,
            "prefix": model.prefix,
            "sep": model.separator,
            "itemformat": model.item_format,
        }

        if model.parent is not None:
            settings["parent"] = model.parent

        data: dict[str, object] = {
            "settings": settings,
        }

        if model.attributes:
            data["attributes"] = model.attributes

        path = model.target / ".doorstop.yml"

        path.write_text(
            yaml.safe_dump(
                data,
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        return path
