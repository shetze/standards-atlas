# Local workspace

`local/` is the persistent **human-facing** workspace and is intentionally not
published through Git.

Use it for artifacts that a human reads, edits, reviews, archives, or consumes
directly:

- `local/exports/` for published Markdown and Doorstop documents;
- `local/review/` for all HITL and editable review material;
- `local/evaluation/` for human-readable evaluation reports and immutable
  evidence archives;
- `local/sources/` for copyrighted or otherwise local-only source material.

Machine-facing persistent state belongs in `.atlas/data`, disposable caches in
`.atlas/cache`, and retained workflow scratch artifacts in `.atlas/work`.
`standards-atlas clean` never removes files from `local/`.
