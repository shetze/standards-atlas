# Local LLM infrastructure

Standards Atlas accesses language models through an OpenAI-compatible application port. The
application does not start or manage RamaLama containers itself.

## Start the local server

The launcher defaults to the `granite` model, port `8080`, CUDA auto-detection, and disabled
SELinux container labels. Disabling labels is currently required for NVIDIA NVML access on the
qualified Fedora/Podman setup.

```bash
./tools/llm/start.sh
```

Override defaults through environment variables:

```bash
RAMALAMA_MODEL=<model> \
RAMALAMA_PORT=8080 \
RAMALAMA_SELINUX=false \
./tools/llm/start.sh
```

The launcher passes these effective options to RamaLama:

```text
ramalama serve --backend auto --selinux=false --port 8080 <model>
```

Check the service and GPU allocation:

```bash
./tools/llm/status.sh
```

Run a schema-constrained completion:

```bash
./tools/llm/smoke.sh
```

Stop the server:

```bash
./tools/llm/stop.sh
```

Runtime state and logs are written below `.atlas/llm/runtime`.

## Application configuration

The default configuration is stored in `cfg/llm.yaml`. Supported environment overrides are:

- `STANDARDS_ATLAS_LLM_BASE_URL`
- `STANDARDS_ATLAS_LLM_MODEL`
- `STANDARDS_ATLAS_LLM_TIMEOUT_SECONDS`
- `STANDARDS_ATLAS_LLM_API_KEY`
- `STANDARDS_ATLAS_LLM_CACHE_DIRECTORY`

An empty cache-directory override disables persistent response caching.

## Architectural boundary

Application code depends on `LlmGateway`. The initial adapter uses the OpenAI-compatible
`/v1/models` and `/v1/chat/completions` endpoints. Generated results include the model, prompt
version, input hash, response hash, duration, token usage, and cache status. No generated result
mutates an engineering document directly.
