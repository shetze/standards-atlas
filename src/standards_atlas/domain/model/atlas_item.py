from __future__ import annotations

from typing import Literal


class AtlasItem:
    kind: Literal["TOC", "TEXT"]
    hash: str
    reference: str
    content: str
    item_type: str | None
