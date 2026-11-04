# TrueNAS plugin for ChatGPT

Use your self-hosted TrueNAS as a private ChatGPT plugin. The Docker Compose
bridge connects the official TrueNAS MCP server through OpenAI Secure MCP Tunnel
without opening inbound internet ports.

> “Use TrueNAS `system_info` to tell me the system version. Do not make any changes.”

**Start with a dedicated Readonly Admin account.** The plugin uses the same
TrueNAS API key for everyone who can access it. TrueNAS enforces the account's
permissions, and tool requests and results pass through OpenAI.
[Permissions and data exposure](docs/architecture.md#permissions-and-data-exposure)

## Quickstart

**Requirements**

- TrueNAS **25.04+** with a hostname or IP reachable from the bridge over verified TLS.
- Linux with Git, Python 3.11+, Docker Engine, Compose v2, Buildx, and outbound HTTPS to OpenAI.
- An OpenAI Platform organization and a ChatGPT workspace that allows custom MCP plugins.

1. **TrueNAS.** Have a dedicated Readonly Admin account, its username, and its
   API key ready. With a reverse proxy, verify TLS on both hops.
   [TrueNAS account and TLS](docs/setup.md#truenas-portal)
2. **OpenAI.** Create or reuse a tunnel, associate it with your ChatGPT
   workspace, and copy its ID. Use a runtime API key with **Tunnels Read + Use**.
   [Tunnel setup](docs/setup.md#create-the-tunnel)
3. **Bridge host.** Run this from the checkout in a local terminal as a
   non-root user with Docker access.

   ```sh
   python3 scripts/bridge.py install
   ```

   Enter the hostname, key owner's username, tunnel ID, and credentials at the
   prompts. Credential input is hidden. If another client uses this tunnel, stop
   it and disable its automatic relaunch before typing `yes`.
4. **ChatGPT.** Add a custom MCP server named **TrueNAS**, select **Tunnel** and
   choose your tunnel. Install the plugin and enable it in a new chat. Try the
   prompt above and compare the version with the TrueNAS UI.
   [ChatGPT setup](docs/setup.md#connect-the-custom-app-in-chatgpt)

## Example prompts

- **System information.** “Use TrueNAS `system_info` to summarize the system information available. Do not make any changes.”
- **Uptime.** “Use TrueNAS `system_info` to report the uptime if available. Do not make any changes.”

## Basic commands

| Command | What it does |
| --- | --- |
| `python3 scripts/bridge.py status` | Show tunnel state and the last saved NAS probe. |
| `python3 scripts/bridge.py probe` | Run a fresh read-only NAS check. |
| `python3 scripts/bridge.py stop` | Stop the bridge. |
| `python3 scripts/bridge.py start --single-instance-confirmed` | Start after checking that the tunnel is free. |
| `python3 scripts/bridge.py restart` | Restart the container and wait for health. |

## Guides

[Setup](docs/setup.md) · [Operations](docs/operations.md) ·
[Architecture](docs/architecture.md) · [Verification](docs/verification.md) ·
[Development](docs/development.md) · [Licensing](docs/licensing.md)

Pinned components are TrueNAS MCP **0.0.7** (upstream research preview) and
OpenAI tunnel-client **0.0.18**. See the [verification record](docs/verification.md)
for tested platforms and the [license and notices](docs/licensing.md) for provenance.
