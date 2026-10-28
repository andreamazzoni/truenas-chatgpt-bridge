# truenas-chatgpt-bridge

Ask ChatGPT how your TrueNAS is doing, with the official TrueNAS MCP server
running on a Linux host you control. Docker Compose keeps the bridge in one
container, and OpenAI Secure MCP Tunnel carries requests into your network
without opening inbound internet ports.

A good first question: *“Which TrueNAS version am I running?”*

```text
ChatGPT personal plugin → OpenAI Secure MCP Tunnel
                                   ↑ outbound HTTPS
                         tunnel-client → stdio → truenas-mcp → WSS → TrueNAS
                         └──────── one non-root container ─────────┘
```

You bring your NAS, credentials and personal ChatGPT plugin. This repository
packages [TrueNAS MCP](https://github.com/truenas/truenas-mcp/tree/v0.0.6) and
[OpenAI tunnel-client](https://github.com/openai/tunnel-client/tree/v0.0.18),
with guided setup and a few small scripts to help you run them. Deployment stays
on the host where you clone the project. There is no autonomous agent or public
plugin submission, and the build commands keep images local.

## Can I try it on my machine?

| Platform | Verified so far |
| --- | --- |
| Linux ARM64, including the tested Raspberry Pi 4 deployment | Full image build, local integration tests, restart, rollback and a real read-only ChatGPT → TrueNAS call |
| Linux AMD64, for Intel/AMD hosts | Full image build completed; execution and integration tests still pending |

TrueNAS MCP is an upstream **research preview**. We pin version 0.0.6, which uses
the legacy `/websocket` API over TLS. Compatibility with every TrueNAS release
is not established; read the [verification record](docs/verification.md) before
trying a different setup.

### Can it change my NAS?

**Yes, if the associated TrueNAS user has permission.** The official MCP includes
both information queries and management tools, such as creating datasets and
starting or stopping apps. This bridge passes those tools through; it has no
additional filter that makes them read-only.

Start with a dedicated **Readonly Admin** user and a key linked to that user.
TrueNAS enforces the user's permissions, even if ChatGPT can see a write tool in
the catalog. Our real-service acceptance test used read-only calls. The
container's read-only filesystem protects the container itself; it does not
restrict what an API key can do on the NAS. See [permissions and data exposure](docs/architecture.md#permissions-and-data-exposure).

## Before you start

Have these ready on the Linux host where you want the bridge to run:

- Git, Python 3.11+, and Docker Engine with Compose (`docker compose`) and
  Buildx/BuildKit. Use a non-root account that can access Docker. The Go compiler
  runs inside the build container.
- Your TrueNAS hostname and a suitable API key. Reuse an existing dedicated
  read-only account/key when you have one.
- An OpenAI tunnel ID and runtime key with permission to use that tunnel, plus
  access to custom MCP servers in your intended ChatGPT account/workspace.
- Outbound HTTPS access to OpenAI and TLS reachability to TrueNAS, including
  working DNS and a trusted certificate.

**New to OpenAI tunnels?** Start with the [manual portal steps](docs/setup.md#openai-portal-and-personal-chatgpt-plugin)
and the [official Secure MCP Tunnel guide](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).
Reuse an existing tunnel and runtime key where possible; otherwise prepare them
in the OpenAI portal. Availability and permissions depend on your account and
workspace. Logins, tunnel associations and authorizations are manual steps.

If you use a reverse proxy, both **bridge → proxy** and **proxy → TrueNAS** must
use encrypted transport. The proxy hostname must match its certificate. TrueNAS
can revoke a key presented over an unencrypted connection, so check the proxy's
backend before starting. The bridge's TLS check only verifies the connection it
can see. More on [certificates and hostname](docs/setup.md#certificates-and-hostname).

## Let's get it running

Clone or download this repository onto your Linux host, then open a terminal in
the `truenas-chatgpt-bridge` directory. Run the commands below from that directory.

### Recommended: one guided command

In a local interactive terminal, run:

```sh
python3 scripts/bridge.py install
```

This checks Docker, Compose and Buildx, builds the local image, walks through
configuration, validates certificate trust and credential access, then asks for
confirmation before starting the tunnel. Confirm only after checking that no
other client is using this tunnel ID, including on another host. Keys are entered
only at hidden terminal prompts. The account, key and tunnel preparation above
still applies; the installer does not create them or configure ChatGPT for you.

If interrupted before startup, rerun the same command: Docker reuses its build
cache, saved settings become prompt defaults, and existing keys are kept. If a
bridge container already exists, the installer leaves it unchanged and directs
you to the day-to-day commands. After a startup failure or interruption, check
`status` before using `start` or `restart` as appropriate. The installer waits for
tunnel and NAS health, then tells you how to perform the ChatGPT check in step 4
below. That final call remains a manual verification.

The individual steps below are also available for manual operation.

### 1. Build the image manually

```sh
python3 scripts/bridge.py build
```

This builds for your host's architecture and downloads pinned upstream components
and base images. It needs no NAS or OpenAI credentials, and the first build may
take a few minutes.

### 2. Walk through setup

```sh
python3 scripts/setup.py
python3 scripts/bridge.py validate
```

Setup checks the hostname and TLS before asking for keys, hides secret input,
and saves the configuration without starting the tunnel. Here is what to enter:

| Prompt | What to enter |
| --- | --- |
| TrueNAS hostname or IP | For example, `nas.example.net` or `nas.example.net:8443`. Leave out `https://` and any path. If the certificate is on your reverse proxy, use the proxy's hostname. |
| OpenAI tunnel ID | The tunnel ID from the OpenAI portal. |
| Platform organization ID | Leave blank unless your tunnel requires an explicit `org-…` organization context. You can add it later. |
| PEM CA/certificate path | On first setup, leave blank for a publicly trusted certificate. For a private CA or self-signed certificate, enter the local path to its independently verified public PEM certificate. |
| OpenAI runtime key and TrueNAS API key | Enter each only at its hidden prompt. Keep keys out of chat, shell commands and `.env`. |

Rerunning setup keeps existing keys. Blank answers keep existing settings;
`-` clears the optional organization ID or returns certificate trust to the
system's trusted CAs. Setup and validation do not start a tunnel. The
[setup guide](docs/setup.md#hidden-local-configuration) explains certificate
preparation and credential replacement.

Your keys live in `secrets/openai_api_key` and `secrets/truenas_api_key`, with
mode `0600`, inside a private directory. They are excluded from Git and the build
context, and mounted read-only at runtime. They are **plain files on disk**, so
back them up separately with encryption. Local settings live in `config/local/`
and `.env`; cloning the repository alone does not restore them or your keys.

### 3. Start the bridge

Make sure there is only **one active client for this stdio tunnel**. If you are
moving it from another host, stop the old tunnel-client and disable automatic
relaunch there first. On a fresh installation, simply confirm no other client
is using the tunnel.

```sh
python3 scripts/bridge.py start --single-instance-confirmed
python3 scripts/bridge.py status
python3 scripts/bridge.py probe
```

The flag confirms that you checked for another instance; the script cannot check
other hosts for you. `start` waits up to 180 seconds for health. `status` and
`probe` show a readable report separating the container, tunnel process, startup,
recent polling and NAS read result. `status` labels the NAS result as saved and
shows its timestamp; `probe` performs a fresh, read-only `system.info` call and
prints its success status rather than your NAS information. Neither command
verifies the full ChatGPT path.

For scripts or structured diagnostics, add `--json` to either command. In those
reports, look for `process_live` and `tunnel_ready` set to `true`, plus
`"ok": true` inside `nas_probe`.

### 4. Try your first ChatGPT question

In ChatGPT, add your personal custom MCP plugin using **Tunnel** as the connection
and select the same tunnel ID. If you already have a plugin for it, use that one
and refresh its tools when needed, especially after replacing a demo server.
Follow the [portal guide](docs/setup.md#openai-portal-and-personal-chatgpt-plugin)
for account permissions and the current setup flow.

Enable the plugin in your chat and ask:

> Use the TrueNAS `system_info` tool to tell me the system version. Do not make any changes.

A successful tool call completes the first end-to-end check. You're connected!
For an existing deployment, the [cutover checklist](docs/setup.md#coordinated-cutover)
also covers restart testing and returning to the old host if needed.

## Day-to-day commands

Pick the command for the job:

| Task | Command |
| --- | --- |
| See container state | `docker compose ps` |
| See tunnel health and the last NAS probe | `python3 scripts/bridge.py status` |
| Run a fresh read-only NAS probe | `python3 scripts/bridge.py probe` |
| Get the original structured report | `python3 scripts/bridge.py status --json` |
| Read recent logs | `docker compose logs --tail 100 bridge` |
| Restart and wait for health | `python3 scripts/bridge.py restart` |
| Stop the bridge | `python3 scripts/bridge.py stop` |
| Remove this deployment and its local settings/keys | `python3 scripts/bridge.py reset` |

Docker restarts exited containers with `unless-stopped`, including after an
ordinary host restart. An intentional stop keeps the bridge stopped until you
start it again. An `unhealthy` status alone does not restart a running container.
For upgrades, use the [update and rollback guide](docs/operations.md), which
retains the previous working image before replacing it. Rolling back the bridge
does not undo changes already made to TrueNAS.

To start over, `reset` shows the checkout and resolved Compose project and asks
you to type `RESET`. It removes that project's containers and non-external
networks first, then deletes `.env`, `config/local/`, `secrets/` (including any
backup files inside it), and `.local/`. If Docker cleanup fails, local files are
kept. Code, Git history, Docker images and build cache remain available for a
new `install`. The command refuses containers belonging to another checkout
with the same Compose project name. See [reset details](docs/operations.md#reset-a-local-installation).

## If something gets stuck

| Symptom | First thing to check |
| --- | --- |
| Build fails with a Docker Hub pull-rate message (HTTP 429) | Run `docker login` locally as the same user, complete the browser login, then retry. An authenticated account still has its own applicable limits. See [Docker's login guide](https://docs.docker.com/reference/cli/docker/login/). |
| Setup cannot verify TLS | Check DNS, the hostname on the certificate and your CA selection. With a proxy, also check HTTPS on its backend. |
| Container cannot read a credential file | Use the same non-root account for setup and operation; check file ownership and the UID/GID saved in `.env`. |
| Process is live but `tunnel_ready` is false | Check outbound connectivity, the tunnel ID, runtime-key permissions and any required organization context. |
| `nas_probe.ok` is false | Check NAS reachability, TLS and the key's associated user/permissions. A successful probe requires `system.info` access. |
| Health is good but ChatGPT discovery/calls fail | Check that the plugin uses the intended tunnel, refresh its tools and confirm there is no second stdio client. |

The [operations guide](docs/operations.md) has more recovery steps. Avoid sharing
raw logs publicly: keys should stay hidden, and logs can still contain private
hostnames or identifiers.

## What the health checks mean

Health separates three useful questions: is the process alive, is the tunnel
polling, and can the NAS answer a read-only request? The following fields are
available in `status --json`, `probe --json` and the Docker health report.

| Field | Evidence |
| --- | --- |
| `process_live` | tunnel-client's local liveness endpoint responds successfully |
| `startup_ready` | upstream startup readiness; stdio may still be uninitialized |
| `tunnel_ready` | liveness and startup readiness, plus a successful poll within 120 seconds |
| `nas_probe.ok` | the official TrueNAS client completed `system.info` with verified TLS |

Docker health requires tunnel readiness and a successful NAS probe. It runs every
60 seconds, with separate startup timing. `status` reads the latest NAS result;
`probe` requests a fresh one. The probe uses a separate NAS session, so a healthy
result is useful evidence, while your ChatGPT call verifies the full tool path.
See [health semantics](docs/architecture.md#health-semantics) for the details.

The container runs non-root with a read-only root filesystem, all capabilities
dropped, bounded temporary storage, and no published diagnostic ports, Docker
socket or NAS dataset mounts. Logs rotate with `max-size: 10m` and `max-file: 3`.
The Compose file requests a 768 MiB RAM cap; enforcement depends on host support.
Our current host reports that memory limits are unavailable. See the
[verification record](docs/verification.md) and check your own host's `docker info`
before relying on that cap.

## For contributors and curious tinkerers

Stable inputs are pinned in `versions.lock.json` and `Dockerfile`: tunnel-client
0.0.18, TrueNAS MCP 0.0.6, Go 1.25.12 and Python 3.13.13, including upstream artifact
checksums and base image digests. TrueNAS MCP is built from source. Upstream code
is kept unchanged, with a small bridge probe added alongside it.

To build a candidate and run the offline checks on your host's architecture:

```sh
docker buildx build --load -t truenas-chatgpt-bridge:dev-001 .
python3 -m unittest discover -s tests -v
BRIDGE_TEST_IMAGE=truenas-chatgpt-bridge:dev-001 python3 tests/integration.py
python3 scripts/audit.py --image truenas-chatgpt-bridge:dev-001 --build-check
```

The integration test needs host `openssl`. It uses its own temporary Compose
project, test credentials and an internal Docker network, without contacting a
real NAS or OpenAI. Its candidate and rollback image tags remain local.

For separate architecture builds:

```sh
docker buildx build --platform linux/arm64 -t truenas-chatgpt-bridge:0.1.0-arm64 --load .
docker buildx build --platform linux/amd64 -t truenas-chatgpt-bridge:0.1.0-amd64 --load .
```

Cross-builds need no emulation because build commands run on the builder's native
architecture. Running the resulting image requires a matching host or emulation;
the AMD64 runtime has not yet been tested. Pinned inputs and stripped Go build
paths/IDs help repeatability; OCI exporter timestamps and attestations can still
produce different image digests across independent builds.

## More reading and licenses

- [Guided setup and manual portal steps](docs/setup.md)
- [Update, rollback, backup and restore](docs/operations.md)
- [Architecture, permissions and health checks](docs/architecture.md)
- [Verification record and remaining limits](docs/verification.md)
- [Licenses, attributions and binary redistribution](docs/licensing.md)

Bridge code: GPL-3.0-only. TrueNAS MCP: GPLv3. OpenAI tunnel-client: Apache-2.0.
Upstream notices, dependency licenses and corresponding TrueNAS source are
preserved in the image. See [LICENSE](LICENSE), [NOTICE](NOTICE) and
[licensing details](docs/licensing.md).
