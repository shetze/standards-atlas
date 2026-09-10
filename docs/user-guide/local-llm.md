# Local LLM operation

Standards Atlas manages a project-owned RamaLama server for reproducible local evaluation. Configuration defaults are defined by the CLI and can be overridden with `--config`.

## Lifecycle

```bash
uv run standards-atlas llm start
uv run standards-atlas llm status
uv run standards-atlas llm stop
```

`status` validates the managed process state rather than merely trusting a stale PID file. Start and stop failures return a non-zero exit status and include the runtime detail.

## Preload qualification models

Download every distinct RamaLama model declared by a qualification manifest:

```bash
uv run standards-atlas llm preload-qualification-models   --manifest manifests/multidimensional-semantic-qualification-v3-semantic-profile-v1.yaml
```

Persistent model storage should be configured in the RamaLama/container runtime so downloads survive process restarts.

## Operational guidance

- start the server explicitly when investigating runtime problems;
- let supported evaluation workflows acquire and release managed server leases where configured;
- use `llm status` after interrupted runs;
- inspect the configured log and runtime state when stop reports a timeout;
- never assume that terminating a client also terminates an independently managed server.

## Handoff from context enrichment to qualification

Context enrichment and qualification share the endpoint and `active-runtime.json`, but use
separate configured container names and launcher PID directories. Matching `/v1/models` is not
sufficient to establish container ownership. Reuse reconciles a uniquely identifiable project
container with the shared receipt; stop validates the recorded container and its host port.

Runtime recovery uses `ps --format` followed by JSON `container inspect`, not the Docker-only
`publish` ps filter rejected by Podman. Nonzero inventory/inspection results, permission errors,
and timeouts are reported as technical failures rather than treated as an empty inventory.
TCP host mappings are checked explicitly: an exposed container port, UDP mapping or another host
port is not the configured endpoint. Host-network fallback requires a recognizable inference
server command with an explicit matching `--port`. Unknown cases remain blocked.

Only the configured name or a `standards-atlas-` name at the exact port is eligible for legacy
recovery. Explicit persisted ownership can identify a custom name. Foreign or multiple matching
runtimes are not force-stopped. Shutdown still requires the old endpoint to disappear before a
new model starts. If this verification fails, the ownership receipt remains available for
investigation; diagnostics include the endpoint, engine and receipt path. A running configured
container at another port is not removed as stale state.

Qualification reports cleanup errors without masking an existing inference/runtime failure and
releases the MCP lease even when server cleanup fails. A cleanup-only failure still returns a
nonzero exit status. A failed initial stop is not immediately repeated by the finalizer.

After a context baseline has been archived, see
[baseline continuation](enrichments-workflow.md#resume-a-frozen-context-baseline-after-a-downstream-runtime-failure)
for resuming qualification without another context run. Do not delete documents, model storage,
caches or baseline archives to resolve a runtime handoff problem.
