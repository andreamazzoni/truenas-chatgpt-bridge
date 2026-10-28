# Setup and coordinated cutover

## TrueNAS portal

Reuse an appropriate existing account and API key. In the TrueNAS web interface,
inspect the dedicated user's roles and existing API key under Credentials / Users
and API Keys (menu labels vary by release). The initial baseline is **Readonly
Admin**. The bridge does not create accounts, generate keys, change roles, or
change TrueNAS settings. If the existing key cannot be recovered, the operator
must manage its replacement in TrueNAS; do not grant broader rights to solve a
permission failure.

The pinned MCP uses `/websocket` and `auth.login_with_api_key`, as implemented in
[v0.0.6 source](https://github.com/truenas/truenas-mcp/tree/v0.0.6).
Do not assume newer TrueNAS releases retain this endpoint. The upstream default
branch differs from this pinned release; follow the pinned CLI and source.

API key authentication must use TLS. TrueNAS can revoke a key presented over
unencrypted HTTP/WebSocket. With a reverse proxy, **both** client → proxy and
proxy → TrueNAS must be HTTPS/WSS. A successful client TLS handshake cannot verify
the proxy's backend configuration: inspect it independently before authenticating.

## Certificates and hostname

Configure `nas.example.net`, an IPv4 address, `[IPv6]`, or a host with an explicit
port. Do not include `https://`, a URL path, username, password, query or fragment.
The bridge constructs the pinned upstream's supported `wss://host:port/websocket`
URL to preserve non-default ports and IPv6. No `ws://` or insecure mode is offered.

For a publicly trusted certificate, leave the CA path blank. For a private CA or
self-signed certificate, export its PEM certificate through a trusted TrueNAS UI
session or an independently verified administrative channel. Verify its fingerprint
and hostname/SAN before trusting it. Do not blindly trust a certificate obtained
from an unauthenticated network connection. Setup copies the public PEM to
`config/local/truenas-ca.pem`; no private certificate key belongs there.

DNS must resolve on the clone host and inside Docker. Host-only DNS overrides and
multicast `.local` names may not resolve from a container. Prefer routable DNS;
if needed, configure a site-specific Compose override locally and protect it.
The NAS certificate must match the configured hostname or IP SAN. A custom CA
bundle replaces the NAS trust store for the pinned Go client.

## OpenAI portal and personal ChatGPT plugin

Follow the [official Secure MCP Tunnel guide](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
and [tunnel-client onboarding](https://github.com/openai/tunnel-client/blob/v0.0.18/docs/onboarding.md).
The stable build deliberately pins a reviewed release rather than following an
upstream latest-release download link automatically.

1. Open [Platform tunnel settings](https://platform.openai.com/settings/organization/tunnels).
   Reuse the existing tunnel ID and suitable runtime API key. Inspect its Platform
   organization and target ChatGPT workspace associations.
2. Creating/managing a tunnel requires **Tunnels Read + Manage**. Running the client
   and selecting it for a plugin requires **Tunnels Read + Use**. Have the organization
   administrator grant missing rights; do not use an administrator credential as
   the container's runtime key. Set the organization ID in setup if required by your
   tunnel's organization context.
3. ChatGPT account/workspace access to custom MCP servers is a separate permission.
   In ChatGPT **Plugins → + → Add custom MCP server**, choose **Tunnel**, then the
   intended tunnel. Current UI wording and account policy may differ; use the
   official guide. Complete any access and risk acknowledgment in the portal.
4. For this stdio bridge the NAS key authenticates the private MCP child; do not
   paste it into the ChatGPT plugin's URL or authentication fields. Configure the
   personal tunnel connection according to the portal's offered authentication
   flow. Review the actual discovered tools before enabling the plugin.

These logins, permissions, associations and acknowledgments are manual steps;
the bridge does not automate unsupported authorization flows. It does not create
or submit a public plugin.

## Hidden local configuration

For a first installation, `python3 scripts/bridge.py install` guides you through
build, setup, validation and startup in one local terminal session. It refuses
to alter an existing bridge container and requires explicit confirmation that
any previous tunnel client has been stopped before starting. On retries it
reuses Docker's build cache and the settings/keys already saved by setup.
After startup, verify the full connection with a read-only ChatGPT call.

To configure separately without starting a tunnel:

Run on the clone host, in a private interactive terminal:

```sh
python3 scripts/setup.py
python3 scripts/bridge.py validate
```

Enter the two **existing** keys only at the hidden prompts. Do not place literal
keys in shell commands, environment exports, screenshots, logs or chat. Secrets
are not requested by any agent tool. Separate terminal sessions do not share
exported variables; this deployment consistently reads mounted files instead.

Setup creates ignored local files:

| Path | Purpose | Backup category |
| --- | --- | --- |
| `config/local/settings.json` | NAS hostname, tunnel/org ID, CA selection | Private configuration |
| `config/local/truenas-ca.pem` | Optional verified public trust material | Private configuration |
| `secrets/openai_api_key` | OpenAI runtime credential, mode 0600 | Encrypted credentials backup |
| `secrets/truenas_api_key` | Existing TrueNAS credential, mode 0600 | Encrypted credentials backup |
| `.env` | Host UID/GID and optional local image selection; no keys | Private configuration |

Directories are mode 0700. Files belong to the non-root operator. Compose local
secrets are read-only bind mounts, **not encrypted at rest**. Compose cannot remap
file ownership using the Swarm secret `uid` option; the container UID/GID matches
the operator via `.env`. Docker administrators can access mounted credentials.
Rootless Docker/user namespace remapping needs separate permission validation;
it has not been tested.

Rerunning setup preserves existing keys without reading them to the screen.
To replace a key, stop the bridge, move the old credential file to protected
encrypted storage outside the checkout, rerun setup to enter the replacement, and
recreate the container. Mounts can retain an old inode after an atomic file
replacement; `docker compose restart` alone is insufficient for rotation.

`validate` checks syntax, required files, ownership access in the container, and
certificate verification without API authentication or tunnel polling. If setup
partially fails, rerun after correcting TLS/files; it never starts the bridge.

## Coordinated cutover

1. Build the new image and complete setup/validation. Keep the old deployment
   available. Verify the reverse proxy backend is encrypted, if applicable.
2. Agree on a short cutover window. Stop the old tunnel-client and disable its
   automatic relaunch. Confirm its process has exited. Do not run two clients on
   one stdio tunnel, even if discovery appears to work.
3. On the new host, run `python3 scripts/bridge.py start --single-instance-confirmed`.
   Inspect `status`; run `probe` and require `nas_probe.ok: true`.
4. In ChatGPT, refresh/update the existing personal plugin's tools, especially if
   it previously used a demo server. Verify the tools identify TrueNAS.
5. Ask for a **read-only** `system_info` call (for example, the TrueNAS version).
   The operator confirms the returned result in ChatGPT. Do not ask ChatGPT to
   modify the NAS as an acceptance test.
6. Test `restart`, then repeat the read-only plugin call. Record only non-sensitive
   outcomes in the verification report.
7. If reverting to the old host, stop the new bridge first, confirm it exited,
   then start the old tunnel-client. Refresh the plugin tools if its catalog differs.

The repository's automated fixtures do not complete steps 3–6 against real services.
