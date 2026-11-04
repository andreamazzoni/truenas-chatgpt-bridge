# Architecture and security

```text
ChatGPT → OpenAI Secure MCP Tunnel
                     ↑ Outbound HTTPS polling and responses
          tunnel-client → stdio → truenas-mcp → WSS → TrueNAS
          └──────── one non-root container ─────────┘
```

The official tunnel client starts the official TrueNAS MCP server on demand
over stdio. A small wrapper verifies TLS and execs the unmodified MCP binary.
TrueNAS MCP 0.0.7 connects to `/api/current` using JSON-RPC 2.0 and
`auth.login_ex`, with the API key and its owner's username. It requires
TrueNAS 25.04+. [Tested platforms and releases](verification.md)

The tunnel client reads the OpenAI runtime key from a mounted file. The
wrapper supplies the TrueNAS key as `TRUENAS_API_KEY` only to the MCP child.
Privileged host processes can inspect that child's environment. Host and
Docker administrators can access the mounted secrets.

Compose runs the bridge with a non-root UID, a read-only root filesystem,
all capabilities dropped, and bounded temporary storage. Diagnostics bind to
loopback inside the container. Compose publishes no ports and mounts no
Docker socket or NAS datasets. Logs rotate at 10 MiB with three files, and
Compose allows 30 seconds for graceful shutdown.

## Permissions and data exposure

Everyone who can use the plugin shares its configured TrueNAS credential.
Restrict plugin access through your workspace and use a dedicated **Readonly
Admin** account for initial use. The NAS enforces the role, even when the
MCP catalog advertises tools that the account cannot execute. The pinned MCP
server has built-in confirmations for some destructive operations. The
bridge exposes the upstream tool catalog without its own filter or optional
upstream read-only, allow, or deny settings.

Tool arguments and NAS results travel through OpenAI, including when the
account is read-only. Raw HTTP and debug logging are disabled. Treat logs as
private because they can contain hostnames and tunnel identifiers.

## Health semantics

| Field | Evidence |
| --- | --- |
| `process_live` | The tunnel client's local liveness endpoint responds. |
| `startup_ready` | The tunnel client reports startup readiness. The stdio server starts on demand. |
| `tunnel_ready` | Liveness, startup readiness, and a successful OpenAI poll within 120 seconds. |
| `nas_probe.ok` | A separate connection using the official TrueNAS client completed `system.info` over verified TLS. |

Docker health requires tunnel readiness and a fresh NAS read, and checks them
every 60 seconds after startup. The bounded probe prints no NAS data. It uses
its own connection and leaves the tunnel's stdio session alone.

`status` shows the saved NAS result and timestamp. `probe` runs a fresh read.
Probe state lives in tmpfs and is cleared when the container is recreated.
Verify the full path separately with a read-only call from ChatGPT.
[Connection checks](operations.md#check-the-connection)

## Scope and limitations

- Use one active stdio client per tunnel ID. The host operations lock
  serializes this checkout's scripts. The operator checks for clients on
  other hosts or in other checkouts.
- The bridge verifies the TLS certificate it sees. For reverse proxies, verify
  TLS on the proxy-to-TrueNAS hop separately.
- Linux ARM64 and AMD64 are the image targets. Check Docker's support for
  memory limits on your host before relying on the configured 768 MiB cap.
  [Verification record](verification.md)
- The bridge uses the upstream OpenAI HTTPS endpoint. Enterprise proxy and
  control-plane mTLS customization are outside the supported configuration.
