# Prompt workbench

The prompt workbench is a local browser interface for testing one enrichment prompt against
one persisted EngineeringDocument clause. It displays packaged prompts as editable system and
user templates, offers the implemented CBox context projections, and activates a
manifest-declared model in the project-owned RamaLama server.

## Start the service

Install the optional web runtime and start the explicitly selected chat service from the
project root:

```bash
uv sync --extra chat --dev
uv run standards-atlas chat serve --service prompt-workbench
```

Open `http://127.0.0.1:8765`. The command also accepts `--service-type` as an alias and offers
`--workspace`, `--llm-config`, `--manifest-directory`, and `--port`. A non-loopback `--host` is
rejected because this slice is a local development tool, not a remotely exposed application.

## Run an experiment

1. Select a versioned prompt and context variant.
2. Select a model from the qualification manifests. **Activate** can warm or switch RamaLama
   before the experiment; running an experiment also activates the selected model atomically.
3. Resolve a clause by stable `clause.id`, qualified key such as `DOCUMENT:7.4.2`, unique
   reference, or use full-text search.
4. Edit the system prompt, user template, or JSON Schema. The original packaged resource is
   not modified.
5. Inspect the context preview, set generation parameters, and run the experiment.

The result reports schema validity, token/runtime metadata, input and response hashes, and the
fully compiled prompt. Response caching is disabled by default so prompt trials are genuinely
fresh; enable it explicitly when deterministic reuse is useful.

The workbench does not persist experiments or write enrichments back to EngineeringDocuments
in this slice.
