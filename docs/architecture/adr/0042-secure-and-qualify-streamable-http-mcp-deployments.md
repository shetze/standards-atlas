# ADR 0042: Secure and qualify Streamable HTTP MCP deployments

## Status

Accepted

## Context

The MCP adapter must support local command-line clients as well as remote clients such as the MCP
Inspector and engineering assistants. A remotely reachable Streamable HTTP endpoint introduces
additional risks beyond the stdio transport:

- unauthorized access to licensed clause text;
- DNS-rebinding attacks through forged `Host` headers;
- cross-origin browser requests;
- oversized request bodies;
- accidental disclosure through logs; and
- regressions caused by MCP SDK or protocol changes.

Successful startup or a health endpoint alone does not demonstrate protocol interoperability.

## Decision

Standards Atlas applies explicit transport-security policy to every Streamable HTTP deployment.

Public network binding requires bearer-token authentication. Configuration defines allowed hosts and
allowed origins and propagates both lists to the MCP SDK's transport-security settings while keeping
DNS-rebinding protection enabled. Request bodies are bounded before reaching the MCP application.
Audit logs record request metadata and outcomes but never tokens, request bodies, clause text, or
model responses.

The server supports stateless Streamable HTTP by default. TLS termination is delegated to a reverse
proxy or deployment platform for non-local use.

A protocol-level compatibility probe is maintained independently of the server implementation. It
performs initialization, verifies the negotiated protocol version, discovers the required tools,
executes `list_standards`, checks the document resource, and writes a content-safe JSON report. The
probe and shell smoke test are suitable for CI, deployment checks, and MCP SDK upgrades.

## Consequences

### Positive

- LAN and reverse-proxy deployments have explicit host and origin policy.
- DNS-rebinding protection remains active instead of being disabled for convenience.
- Authentication is mandatory when binding beyond loopback.
- Operational logs avoid protected engineering content.
- Interoperability is demonstrated through real protocol operations.
- SDK and protocol upgrades can be qualified against durable evidence.

### Negative

- Remote deployment requires additional configuration and secret management.
- Browser clients may also require a proxy or correctly configured CORS handling.
- Allowed-host and allowed-origin lists must track deployment topology.
- The compatibility probe verifies the supported contract, not every possible MCP client behavior.

## Alternatives considered

### Disable DNS-rebinding protection

Rejected because it would make remote operation easier at the cost of an avoidable security risk.

### Accept tokens in query parameters

Rejected because URLs commonly appear in browser history, proxy logs, and referrer information.
Bearer tokens remain HTTP headers.

### Rely only on unit tests

Rejected because mocked registration tests cannot prove Streamable HTTP negotiation, discovery,
tool invocation, or resource interoperability.

### Treat the MCP Inspector as the qualification mechanism

Rejected because an interactive external tool is useful for diagnosis but is not deterministic,
headless, or suitable as durable CI evidence.
