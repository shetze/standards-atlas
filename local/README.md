# Local workspace

This directory separates non-versioned source material and consumable generated outputs from Standards Atlas internal artifacts.

- `sources/` contains copyrighted standards, TSI documents, Polarion exports, ReqIF packages and other local source documents.
- `exports/markdown/<hierarchy>/` contains readable Markdown exports.
- `exports/doorstop/<hierarchy>/` contains the result of `doorstop publish`.

Internal processing, debugging and Doorstop YAML artifacts remain below `.atlas/`. Except for this guide and placeholder files, `local/` is ignored by Git. Catalog metadata supplies the multidimensional Knowledge Domain classification; the physical source tree only provides a stable local storage boundary.
