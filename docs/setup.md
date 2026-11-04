# Setup

Start with the [quickstart](../README.md#quickstart). Use one active client per
tunnel ID, including when moving between hosts.

## TrueNAS portal

1. In the TrueNAS web interface, check the dedicated user's roles and API key
   under **Credentials → Users** and **API Keys**. Menu labels vary by release.
2. Start with **Readonly Admin**. Have the username and its API key ready.
   If the key is unavailable, manage its replacement in TrueNAS. Keep the same
   permissions when troubleshooting access.
3. Verify TLS before using the key. With a reverse proxy, both bridge → proxy
   and proxy → TrueNAS must use verified TLS. Check the backend configuration
   separately from the certificate the bridge sees. TrueNAS can revoke keys
   presented over an unencrypted connection.

TrueNAS MCP 0.0.7 requires TrueNAS 25.04+ and authenticates with the key and its
owner's username. [Pinned TrueNAS MCP source](https://github.com/truenas/truenas-mcp/tree/v0.0.7)

## Create the tunnel

1. In the intended OpenAI Platform organization, create or reuse a tunnel and
   copy its ID. Creating or editing tunnels requires **Tunnels Read + Manage**.
2. Associate the tunnel with the target ChatGPT workspace so it is available
   when you add the custom MCP server. The workspace must allow custom MCP plugins.
3. Create or reuse a runtime API key with **Tunnels Read + Use**. This permission
   also applies to the person selecting the tunnel in ChatGPT. Use a restricted
   runtime key and keep the optional `org-…` ID handy if your organization needs it.

[Platform tunnel settings](https://platform.openai.com/settings/organization/tunnels) ·
[Secure MCP Tunnel guide](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels) ·
[Pinned client onboarding](https://github.com/openai/tunnel-client/blob/v0.0.18/docs/onboarding.md)

## Configure the host

Run the [installer](../README.md#quickstart) in a private local terminal as
the non-root user who operates Docker. It builds the pinned image, verifies the
TrueNAS hostname and TLS, prompts for configuration and keys, validates
Compose, and offers to start the tunnel. Use it for a first installation.
It refuses to run if a bridge container already exists in this Compose
project. Retries reuse saved setup and build cache.

Enter a bare hostname or IP such as `nas.example.net`, `nas.example.net:8443`,
or `[2001:db8::1]`. Leave out schemes, paths, user information, queries, and
fragments. If using a reverse proxy, enter the hostname on its certificate.
Both the host and the container must be able to resolve the name and reach it.

Enter each key at its hidden prompt. Keep keys out of chat, shell arguments,
environment exports, logs, and screenshots. Press Enter to keep saved settings.
Setup keeps existing key files in place. Enter `-` to clear the optional
organization ID or return to system CA trust.

| Git-ignored path | Contents |
| --- | --- |
| `config/local/settings.json` | NAS hostname and key owner, tunnel and organization IDs, CA selection |
| `config/local/truenas-ca.pem` | Optional public PEM certificate |
| `secrets/openai_api_key` | OpenAI runtime key |
| `secrets/truenas_api_key` | TrueNAS API key |
| `.env` | Operator UID/GID and optional image selection |

Setup uses mode 0700 for private directories and 0600 for credential files.
Secrets are stored as plaintext on disk. Compose mounts them read-only and
runs the container with the operator's UID/GID. Check file access separately
if using rootless Docker or user namespace remapping.

### HTTPS with a private CA

For a publicly trusted certificate, leave the CA path blank on first setup.
For a private CA or self-signed certificate, obtain its public PEM through a
trusted administrative channel. Verify the fingerprint and check that the NAS
certificate covers the configured hostname or IP in its SAN. Enter the local
PEM path at the setup prompt. The pinned Go client uses this bundle as its
trust store for TrueNAS.

### Manual installation

Run these steps from the checkout to build and validate without starting a
tunnel. Validation checks Compose, file access, and TLS before any API
authentication or tunnel polling.

```sh
python3 scripts/bridge.py build
python3 scripts/setup.py
python3 scripts/bridge.py validate
```

After checking that no other client is using the tunnel or will automatically
restart, start the bridge and check the connection.

```sh
python3 scripts/bridge.py start --single-instance-confirmed
python3 scripts/bridge.py status
python3 scripts/bridge.py probe
```

For an existing deployment, follow the relevant procedure for
[key rotation](operations.md#rotate-a-key),
[a host move](operations.md#coordinated-cutover), or
[an upgrade from MCP 0.0.6](operations.md#upgrade-from-truenas-mcp-006).

## Connect the custom app in ChatGPT

Keep the bridge running during discovery. Menu labels and access depend on
your account and workspace policy.

1. Open **Plugins → + → Add custom MCP server** in the target workspace.
2. Name the plugin **TrueNAS** and choose **Tunnel** under **Connection**.
   Select the intended tunnel or enter its ID.
3. Select **No authentication** if the workspace offers it. The local stdio
   server uses the mounted TrueNAS key for NAS authentication. Keep the key on
   the bridge host.
4. Complete the portal prompts, install the plugin, and review its discovered
   tools. If reusing a plugin on the same tunnel, refresh its tools after
   replacing the previous MCP server.
5. Enable the plugin in a new chat using the app picker or `@TrueNAS`. Ask for
   a read-only `system_info` call and compare the version with the TrueNAS UI.

[Add a custom MCP server](https://developers.openai.com/api/docs/guides/custom-mcp-server) ·
[Verification](verification.md)
