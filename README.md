# truenas-chatgpt-bridge

Inspect and manage your TrueNAS from ChatGPT: ask about your system, create
datasets, or start and stop apps through the tools your NAS account permits.
This project runs the official
[TrueNAS MCP server](https://github.com/truenas/truenas-mcp/tree/v0.0.6) and
[OpenAI Secure MCP Tunnel client](https://github.com/openai/tunnel-client/tree/v0.0.18)
in one Docker Compose container on your Linux host, without opening inbound
internet ports. It does not run an autonomous agent or publish a public plugin.

## Before you start

- Use a non-root Linux account with Git, Python 3.11+, Docker Engine, Compose
  and Buildx/BuildKit installed and access to Docker.
- Have your TrueNAS hostname and API key, an OpenAI tunnel ID and authorized
  runtime key, and access to custom MCP servers in ChatGPT. For account and
  tunnel preparation, see the [setup guide](docs/setup.md#openai-portal-and-personal-chatgpt-plugin).
- Allow outbound HTTPS to OpenAI and a connection to TrueNAS with a verified
  TLS certificate. With a reverse proxy, secure both hops, including
  **proxy → TrueNAS**; see [certificate setup](docs/setup.md#certificates-and-hostname).

**Choose a dedicated account with permissions for the tasks you want.** The
bridge exposes the official MCP's query and management tools; TrueNAS enforces
the account's permissions. For the first connection, we recommend **Readonly
Admin** so you can try it without changing NAS state. For management tasks,
grant the permissions those tasks require. Requests and NAS results travel
through OpenAI and ChatGPT. Read the
[permissions and data exposure notes](docs/architecture.md#permissions-and-data-exposure).

Linux ARM64 has been tested through a real read-only ChatGPT call. The AMD64
image builds, but its runtime is not yet verified. The pinned TrueNAS MCP is a
research preview using the legacy WebSocket API; compatibility with every NAS
release is not established. See [verified compatibility](docs/verification.md).

## Install

Clone or download this repository onto the Linux host where it will run. From
its directory, in a local interactive terminal:

```sh
python3 scripts/bridge.py install
```

The command builds the image, guides configuration, checks TLS and credential
access, and asks before starting. Enter a hostname such as `nas.example.net`
(without `https://` or a path). Enter keys **only at the hidden prompts**, never
in chat, shell commands or `.env`. They are stored in private files under
`secrets/`, excluded from Git and the image, but **not encrypted on disk**.

Before confirming startup, stop any previous client using the same tunnel and
disable its automatic relaunch. **Only one client may use this tunnel ID.**

If interrupted before startup, rerun `install`: it reuses the build cache and
saved settings/keys. If a container already exists, it leaves it unchanged;
check `status` and use the [operations guide](docs/operations.md) to continue.
For prompt explanations or individual commands, see [manual setup](docs/setup.md#manual-installation-and-setup-prompts).

## Connect ChatGPT

Add or reuse a personal custom MCP plugin with **Tunnel** as the connection,
selecting the same tunnel ID. Follow the [portal steps](docs/setup.md#openai-portal-and-personal-chatgpt-plugin)
for access and setup; refresh existing tools if needed. For a first check that
does not change NAS state, enable the plugin and ask:

> Use the TrueNAS `system_info` tool to tell me the system version. Do not make any changes.

A successful tool call verifies the full connection. Container health alone
does not prove that a ChatGPT call works.

You can then use the plugin for management tasks supported by the pinned MCP
version and your account's permissions. The bridge adds no read-only filter.

## Daily commands

| Task | Command |
| --- | --- |
| Show tunnel state and the last saved NAS check | `python3 scripts/bridge.py status` |
| Run a fresh read-only NAS check | `python3 scripts/bridge.py probe` |
| Get structured output for scripts | Add `--json` to `status` or `probe` |
| Restart and wait for health | `python3 scripts/bridge.py restart` |
| Stop | `python3 scripts/bridge.py stop` |
| Start after stopping | `python3 scripts/bridge.py start --single-instance-confirmed` |
| Remove this deployment, configuration and keys | `python3 scripts/bridge.py reset` |

`status` shows the time of the saved NAS result; `probe` checks again now.
`reset` asks you to type `RESET` before removing this project's containers,
networks, configuration and secrets (including backups in `secrets/`). It keeps
code and Docker images and does not revoke keys. See [reset details](docs/operations.md#reset-a-local-installation).

## Detailed guides

- [Setup, certificates, credentials and migration](docs/setup.md)
- [Troubleshooting](docs/operations.md#troubleshooting), [updates, rollback and backups](docs/operations.md)
- [Architecture, security and health checks](docs/architecture.md)
- [Verified compatibility and limitations](docs/verification.md)
- [Development, builds and offline tests](docs/development.md)
- [Licenses and binary redistribution](docs/licensing.md)

Bridge code: GPL-3.0-only. TrueNAS MCP: GPLv3. OpenAI tunnel-client: Apache-2.0.
See [LICENSE](LICENSE), [NOTICE](NOTICE) and the licensing guide above.
