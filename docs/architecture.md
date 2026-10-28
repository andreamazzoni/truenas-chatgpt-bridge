# Architecture and trust boundaries

```text
ChatGPT personal plugin → OpenAI Secure MCP Tunnel
                                   ↑ outbound HTTPS
                         tunnel-client → stdio → truenas-mcp → WSS → TrueNAS
                         └──────── one non-root container ─────────┘
```

One container runs `tunnel-client run`. On demand, the official client starts
`python /opt/bridge/runtime.py mcp`, which validates TLS, reads the mounted TrueNAS
key and **execs the unmodified `truenas-mcp` binary**. The stdio pipes belong to
tunnel-client. No intermediary MCP server or protocol implementation is added.

The production control plane is the upstream default OpenAI HTTPS endpoint.
The wrapper uses an explicit environment allowlist: no inherited proxy,
debug, raw HTTP logging or insecure TLS options. Enterprise proxy and control-plane
mTLS customization are outside v0.1.0's supported configuration.

OpenAI's key is passed as a native `file:/run/secrets/openai_api_key` reference.
TrueNAS MCP v0.0.6 requires a flag or environment variable, so only its child
gets `TRUENAS_API_KEY` loaded from `/run/secrets/truenas_api_key`. It is never an
argument or image/container configuration value. It is necessarily present in
the child's memory/environment; privileged host processes can inspect that.

The Docker init process forwards signals and reaps orphaned children. Startup
uses `exec` instead of a background shell. Compose allows 30 seconds for shutdown,
then Docker can kill a stuck process. `unless-stopped` handles process exit and
Docker daemon/host restarts; it does not repair a running unhealthy container.
Only the bridge's own service is controlled by the scripts.

The container runs non-root with a read-only root filesystem, all capabilities
dropped, bounded temporary storage, and no Docker socket or NAS dataset mounts.
Logs rotate with `max-size: 10m` and `max-file: 3`.

Compose requests a 768 MiB memory cap. Docker reports that the current development
kernel cannot enforce memory/swap limits; this is an observed host limitation,
not a reason to modify other services or the host boot configuration. Check
`docker info` on your own host before relying on resource enforcement.

No host ports are published. Diagnostics bind `127.0.0.1:8080` **inside the
container**. Inspect sanitized status with `docker compose exec -T bridge python
/opt/bridge/runtime.py status`. Do not publish the admin UI or diagnostic endpoints
without a separate authenticated operator access design.

## Health semantics

The readable `status` and `probe` reports separate these signals. Their `--json`
output and Docker's health report expose the following fields:

| Field | Evidence |
| --- | --- |
| `process_live` | tunnel-client's local liveness endpoint responds successfully |
| `startup_ready` | upstream startup readiness; stdio may still be uninitialized |
| `tunnel_ready` | liveness and startup readiness, plus a successful poll within 120 seconds |
| `nas_probe.ok` | the official TrueNAS client completed `system.info` with verified TLS |

Docker health requires tunnel readiness and a successful NAS probe. It runs
every 60 seconds, with separate startup timing. An unhealthy state alone does
not restart a running container.

`/healthz` proves the tunnel daemon serves its liveness endpoint. `/readyz` is
upstream startup readiness, not a complete stdio test. `tunnel_ready` additionally
requires the upstream `commands_poll_last_successful_timestamp_seconds` metric
within 120 seconds. This tolerates the default 30-second long poll but degrades
on sustained authentication, connectivity or service failures.

Docker's periodic health command also launches `bridge-probe`: a small Go adapter
compiled against the same unmodified official `truenas` client package. It uses
verified TLS and calls **only `system.info`**, accepts a nonempty JSON object and
prints no NAS data or upstream errors. It uses its own short-lived connection,
bounded by a 20-second subprocess deadline plus an 8-second TLS preflight. This
does not start another tunnel instance or touch the tunnel's stdio streams.

The health command succeeds only when the tunnel is ready and the fresh NAS read
succeeds. Failure output consists of bounded booleans/timestamps. `probe` returns
success based on the NAS probe alone, while also showing tunnel state. `status`
performs no NAS call and returns the previous result and its timestamp. State is
in tmpfs and disappears on container recreation. Historical evidence must be
interpreted at its timestamp; it is not a reachability guarantee.

The official MCP child is lazy. Only discovery/calls through ChatGPT can verify
the full ChatGPT → hosted tunnel → official MCP → NAS path with real services.
Upstream `/health/mcp` can show same-child discovery evidence; no health read
triggers it. Offline fixtures separately exercise the official stdio server.

## Permissions and data exposure

The bridge does not filter upstream tools or add an authorization layer. A
Readonly Admin key limits API execution at TrueNAS; write tools can still be
advertised by the upstream catalog and fail at authorization. ChatGPT approval
settings do not replace TrueNAS role restrictions. Keep the initial key read-only.

Tool arguments and NAS results travel through the OpenAI tunnel and ChatGPT.
Review the intended users/workspace before enabling the personal plugin. Ordinary
upstream logs are enabled at metadata level; raw bodies and debug modes are off.
Hostnames and tunnel identifiers may appear in logs, although keys must not.
Treat diagnostic output as private operational information.

## Scope and limitations

- Only TrueNAS and ChatGPT; no autonomous scheduling of administrative actions.
- Only Linux ARM64/AMD64 image targets. Other platforms and Docker namespace modes
  are not claimed compatible.
- The pinned TrueNAS MCP uses the older protocol at `/websocket`. TrueNAS calls
  this the [legacy API](https://github.com/truenas/api_client#about), distinct
  from JSON-RPC 2.0 at `/api/current`; both use WebSocket transport. Future servers
  may remove the older endpoint. Migrating to the newer NAS API requires a
  separately reviewed upstream MCP upgrade.
- TLS preflight verifies the front-facing certificate, never the reverse proxy's
  backend hop. Secure that hop before supplying a key.
- A host operations lock serializes this checkout's scripts. It cannot discover
  other machines, other checkouts, or manually started competing clients.
- No persistent application database or NAS data is mounted. Task state inside
  the upstream MCP process is ephemeral and not restored after replacement.
