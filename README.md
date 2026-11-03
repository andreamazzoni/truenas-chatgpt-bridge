# truenas-chatgpt-bridge

Create a private **TrueNAS plugin for ChatGPT** that you can enable in a chat
to inspect and manage your self-hosted TrueNAS. The Docker Compose bridge runs
the official components and connects the plugin through OpenAI Secure MCP
Tunnel, without opening inbound internet ports.

## Example prompts

Enable the TrueNAS plugin in a ChatGPT conversation and try these read-only
requests with a Readonly Admin account:

- **Check the version.** “Use TrueNAS `system_info` to tell me the system
  version. Do not make any changes.”
- **Review system information.** “Use TrueNAS `system_info` to summarize the
  system information available, including the version and uptime if provided.
  Do not make any changes.”

| Component | Pinned version |
| --- | --- |
| TrueNAS MCP | **[0.0.7](https://github.com/truenas/truenas-mcp/releases/tag/v0.0.7)** |
| OpenAI Secure MCP Tunnel client | **[0.0.18](https://github.com/openai/tunnel-client/releases/tag/v0.0.18)** |

## Requirements

- Linux, Git, Python 3.11+, Docker Engine with Compose and Buildx; a non-root user with Docker access.
- TrueNAS **25.04+**, hostname, API key and its owner username; verified TLS on both hops if using a reverse proxy.
- OpenAI tunnel ID and runtime key, outbound HTTPS, and custom MCP access in ChatGPT.

TrueNAS permissions control which actions are allowed. Use a dedicated account;
**Readonly Admin** is recommended for the first test. Requests and NAS results
pass through OpenAI and ChatGPT. [Permissions and data exposure](docs/architecture.md#permissions-and-data-exposure).

TrueNAS MCP is an upstream research preview. See [verified platforms and
compatibility](docs/verification.md) for build, fixture and operator acceptance results.

## Quick start

Clone this repository and, from its directory in a local terminal, run:

```sh
python3 scripts/bridge.py install
```

The installer builds, configures, checks and starts the bridge. Enter keys only
at hidden prompts; they are stored in private, unencrypted files under `secrets/`,
excluded from Git and the image. **Stop any previous client and disable its
automatic relaunch before confirming startup: one client per tunnel ID.**

In ChatGPT, add a custom MCP server named **TrueNAS** or reuse your personal
plugin, choose **Tunnel** and the same ID, then enable the plugin in a chat
([setup steps](docs/setup.md#openai-portal-and-personal-chatgpt-plugin)). Try:

> Use TrueNAS `system_info` to tell me the system version. Do not make any changes.

This tests the full connection; container health alone does not. Management
actions are available according to the MCP tools and your account's permissions.

## Commands

| Task | Command |
| --- | --- |
| Tunnel state and last saved NAS check | `python3 scripts/bridge.py status` |
| Fresh read-only NAS check | `python3 scripts/bridge.py probe` |
| Restart | `python3 scripts/bridge.py restart` |
| Stop | `python3 scripts/bridge.py stop` |
| Start again (after checking for other clients) | `python3 scripts/bridge.py start --single-instance-confirmed` |
| Delete this deployment, configuration and secrets | `python3 scripts/bridge.py reset` |

Add `--json` to `status` or `probe` for structured output. `reset` requires typing
`RESET`; it keeps code and images and does not revoke keys. [Operations](docs/operations.md).

## Guides

[Setup and certificates](docs/setup.md) · [Troubleshooting](docs/operations.md#troubleshooting) ·
[Updates and backups](docs/operations.md) · [Architecture and health checks](docs/architecture.md) ·
[Development and tests](docs/development.md) · [Licenses](docs/licensing.md)

Bridge: [GPL-3.0-only](LICENSE). TrueNAS MCP: GPLv3. OpenAI tunnel-client: Apache-2.0. [Notices](NOTICE).
