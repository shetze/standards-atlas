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
