# AP03 Codex Development workflow

This workflow is for AP03 Development diagnosis/prompt proposals only. It does not authorize Holdout
access, Golden publication, human review decisions or a direct Codex qualification arm.

## 1. Bind the server to real Series-D Development registrations

Copy `cfg/mcp-ap03-development.example.yaml` to a local, uncommitted configuration and replace the
placeholders with the registered S08 assertion-review handle, explicit Development document keys and,
when available, the exact Development experiment IDs. Keep the listener on loopback unless a separate
remote-operation security decision exists. Keep bearer-token values in the configured environment
variable, never in YAML or Codex config fragments.

Server startup is fail-closed. A registered assertion package with no Development cases, a missing
package, an empty document allowlist, a source-group/source-package/source-clause overlap with Holdout,
or an unsafe staging path prevents the AP03 profile from becoming usable.

## 2. Verify the server profile

```text
standards-atlas mcp probe \
  --url http://127.0.0.1:8765/mcp \
  --server-config <local-ap03-mcp.yaml>
```

This is a protocol/server probe, not Codex client recognition and not inference. In this profile the
absence of generic MCP resources and formula/media tools is intentional.

## 3. Generate the exact Codex MCP allowlist

```text
standards-atlas mcp codex-config \
  --url http://127.0.0.1:8765/mcp \
  --server-config <local-ap03-mcp.yaml> \
  --output <local-codex-fragment.toml>
```

`enabled_tools` is derived from the server profile's registered tool policy. It supplements server-side
authorization; changing the client allowlist cannot expand the server scope.

## 4. Optionally verify the actual Codex client

First run without opt-in. This reports client availability/version but performs no model call:

```text
standards-atlas mcp codex-client-probe \
  --url http://127.0.0.1:8765/mcp \
  --server-config <local-ap03-mcp.yaml>
```

Only after the chosen Codex/provider route is approved may one text-free real tool-read be requested:

```text
standards-atlas mcp codex-client-probe \
  --url http://127.0.0.1:8765/mcp \
  --server-config <local-ap03-mcp.yaml> \
  --allow-synthetic-model-call \
  --model <explicit-model-id>
```

The temporary probe profile enables only `get_server_info`; no standards clause, review source,
experiment text, media or report is offered. Success establishes only that this concrete client can see
and call that MCP tool. It says nothing about semantic quality.

## 5. Codex optimization mandate

Use the AP03 plan's local Codex mandate. Codex may read only the registered Development surfaces and
text-safe Development experiment diagnostics. It should identify at most three clusters and submit one
small role-prompt replacement through `submit_prompt_variant_proposal`.

Atlas rejects stale manifest hashes, foreign cases, non-Development experiments, unapproved data routes,
unsafe staging paths, oversized prompts and proposal fields attempting to alter budget, model route,
partition, Golden/evaluator/schema/source policy or human state. A successful submission only creates
an `unqualified-development` staged bundle plus receipt. It performs zero model calls.

## 6. Plan and run a staged variant through the existing runner

The receipt gives the staged version and bundle location. Use the staging root (the directory configured
as `ap03_development.staging_directory`, not the individual version directory) with the existing plan:

```text
standards-atlas evaluation assertion-experiment-plan \
  ...existing approved Development inputs... \
  --prompt-version codex-<variant> \
  --prompt-staging-root local/evaluation/assertions/ap03/codex-staging
```

Run/resume that new manifest with the same `--prompt-staging-root`. The existing planner recompiles the
real source-bound request and binds per-case request hashes; the runner validates those hashes and its
normal execution authorization/budget before inference. Do not edit the old manifest to point at the
new prompt.

## 7. Direct `CodexCliLlmGateway` is not the optimizer

The MCP optimizer/client described above is separate from `CodexCliLlmGateway`. Direct gateway
inference is disabled by default and remains non-qualifying because the current Codex CLI adapter cannot
control all experiment parameters. Seed/max-token/reasoning requests and non-default temperature are
rejected instead of being merely hashed. Do not use this optional arm for AP03 comparative claims until
a later explicitly controlled contract exists.
