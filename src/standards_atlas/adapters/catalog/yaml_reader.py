from pathlib import Path

import yaml

from standards_atlas.application.catalog import StandardCatalog


class YamlStandardCatalogReader:
    def read(self, path: Path) -> StandardCatalog:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return StandardCatalog.model_validate(data)
