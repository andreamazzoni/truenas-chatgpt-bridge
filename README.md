# truenas-chatgpt-bridge

Run the official TrueNAS MCP server behind OpenAI Secure MCP Tunnel using Docker
Compose, on the Linux host where you clone this repository.

```text
ChatGPT personal plugin → OpenAI Secure MCP Tunnel
                                   ↑ outbound HTTPS
                         tunnel-client → stdio → truenas-mcp → WSS → TrueNAS
                         └──────── one non-root container ─────────┘
```

Each operator supplies their own NAS, existing tunnel, credentials and personal
ChatGPT plugin. This project packages upstream software; it does not implement
TrueNAS tools, a tunnel protocol or an autonomous agent. Nothing is published to
a public plugin catalog or container registry.

The TrueNAS MCP upstream is a **research preview**. See
[verification status](docs/verification.md) for what has actually been tested.
The real deployment and ChatGPT call require an operator-coordinated cutover.

## Requirements

- Linux ARM64 or AMD64, Docker Engine with Compose v2+ and BuildKit.
- Python 3.11+ on the clone host for the setup/operations scripts.
- A TrueNAS account and API key with the minimum necessary permissions. Start
  with a dedicated **Readonly Admin** account; do not elevate it for a health check.
- An existing OpenAI tunnel and runtime key with tunnel use permissions, plus
  permission to add a custom MCP server in the intended ChatGPT account/workspace.
- Outbound HTTPS to OpenAI and verified TLS reachability to TrueNAS. No inbound
  ports are required. Builds download public upstream artifacts and base images.

## Quick start

Run these commands from your clone. Docker must be accessible to your user.
There is no SSH deployment step and no dependency on another computer.

```sh
python3 scripts/bridge.py build
python3 scripts/setup.py
python3 scripts/bridge.py validate
```

Setup checks DNS/TLS **before** requesting credentials, uses hidden terminal
input, reuses existing credential files, and never starts the tunnel. Do not paste
keys into chat, shell arguments or `.env`. See [setup](docs/setup.md) for the
manual OpenAI/TrueNAS steps and certificate preparation.

If another host uses the same stdio tunnel, stop its tunnel-client first and
confirm it stays stopped. Then:

```sh
python3 scripts/bridge.py start --single-instance-confirmed
python3 scripts/bridge.py status
python3 scripts/bridge.py probe
```

`start` waits up to 180 seconds for health. It cannot detect a competing instance
on another host; the flag records your confirmation that you stopped it.
In ChatGPT, select the same tunnel, refresh the personal plugin's tools, and ask
for the TrueNAS version using `system_info`. An old demo tool catalog must be
refreshed. Complete the [cutover checklist](docs/setup.md#coordinated-cutover).

Compose is the runtime interface. For routine operations:

```sh
docker compose ps
docker compose logs --tail 100 bridge
python3 scripts/bridge.py restart
python3 scripts/bridge.py stop
```

## Security and health

The container runs non-root, drops all capabilities, uses a read-only root
filesystem and bounded tmpfs, and has no published ports, Docker socket or NAS
dataset mounts. Credentials are mounted read-only from ignored `secrets/` files.
Logs rotate at 10 MiB × 3. Docker restarts exited containers with `unless-stopped`;
an `unhealthy` status alone does **not** cause Docker to restart a running process.

Health reports separate facts:

| Field | Evidence |
| --- | --- |
| `process_live` | tunnel-client `/healthz` returns 200 |
| `startup_ready` | upstream `/readyz` returns 200; stdio may still be uninitialized |
| `tunnel_ready` | both above and a successful poll within 120 seconds |
| `nas_probe.ok` | official upstream client completed `system.info` with verified TLS |

Docker health runs a bounded read-only NAS probe every 60 seconds. `status` only
reads the last observation; `probe` requests a fresh read. A probe uses a separate
NAS session, does not initialize the tunnel's MCP child, and does not prove a
ChatGPT call. There is no application database or durable NAS data in the bridge.
See [architecture and security](docs/architecture.md).

## Builds and development

Stable inputs are pinned in `versions.lock.json` and `Dockerfile`: tunnel-client
0.0.18 release checksums, TrueNAS MCP 0.0.6 source commit/checksum, Go 1.25.12,
Python 3.13.13 and multi-platform base image digests. No stable `latest` tags.
TrueNAS MCP is built from source for both architectures. No upstream code is patched.

```sh
docker buildx build --platform linux/arm64 -t truenas-chatgpt-bridge:0.1.0 --load .
docker buildx build --platform linux/amd64 -t truenas-chatgpt-bridge:0.1.0-amd64 --load .
python3 -m unittest discover -s tests -v
python3 tests/integration.py
python3 scripts/audit.py --build-check
```

Cross-builds require no emulation: all build commands run on the native build
platform. An AMD64 image assembled on ARM64 still needs an AMD64 host (or an
explicitly installed emulator) to test its runtime. The integration test requires
host `openssl`, uses a distinct temporary Compose project and an internal Docker
network, and never contacts a real NAS or OpenAI. It uses only the local image.

The build pins its inputs and strips Go build paths/IDs. It does not claim identical
OCI image digests across independent builds: exporter timestamps and attestations
can differ. Do not publish images as part of these build commands.

## Operations and licensing

- [Guided setup and manual portal steps](docs/setup.md)
- [Update, rollback, backup and restore](docs/operations.md)
- [Architecture, trust boundaries and limits](docs/architecture.md)
- [Verified results and pending acceptance checks](docs/verification.md)
- [Licenses, attributions and binary redistribution](docs/licensing.md)

Bridge code: GPL-3.0-only. TrueNAS MCP: GPLv3. OpenAI tunnel-client: Apache-2.0.
Upstream notices, dependency licenses and corresponding TrueNAS source are
preserved in the image. See [LICENSE](LICENSE), [NOTICE](NOTICE) and
[licensing details](docs/licensing.md).
