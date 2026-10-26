# Verification record

This file records observations from 2026-10-26, not a general compatibility guarantee.

## Current implementation acceptance

The following checks are performed locally before a real-service cutover:

| Check | Status |
| --- | --- |
| Compose configuration | Passed `docker compose config --quiet` |
| Native Linux ARM64 build and execution | Passed; non-root, read-only root, no published ports, all capabilities dropped |
| Linux AMD64 cross-build | All 3 executables built/verified as static x86-64 ELF; full runtime image blocked by Docker Hub anonymous pull quota (HTTP 429); AMD64 execution not tested |
| Strict hostname/secret permissions and health distinction tests | 7 tests passed |
| Official MCP stdio discovery and `system_info` against TLS fixture | Passed with official TrueNAS MCP 0.0.6 |
| Container restart and graceful shutdown | Passed restart/retest; final tunnel exit code 0 |
| Candidate replacement and retained-image rollback | Passed using the actual host update/rollback functions and exact previous image ID |
| Credential exclusion from build context, image and tracked files | Passed tracked-path/token-pattern scan, ignored canary rebuild and scan of every exported image layer; no real credentials supplied |
| Real tunnel polling and read-only NAS call after cutover | Pending operator credentials and coordinated cutover |
| Personal ChatGPT plugin tool refresh and read-only call | Pending operator-assisted acceptance |

The Docker daemon reports no memory/swap limit support on the development host.
Compose requests a memory cap but that kernel does not enforce it. No kernel,
boot, Docker daemon or unrelated service settings were changed. CPU/PID/tmpfs
limits remain configured; do not infer a memory cap from this Compose file on
an unsupported host.

The full AMD64 build can be retried when the base image is accessible:

```sh
docker buildx build --platform linux/amd64 -t truenas-chatgpt-bridge:0.1.0-amd64 --load .
```

To reproduce the already successful AMD64 artifact build without an AMD64 base
image or emulator:

```sh
docker buildx build --platform linux/amd64 --target binaries --output type=local,dest=.local/amd64-binaries .
file .local/amd64-binaries/*
```

The offline integration fixture uses loopback TLS, a minimal mock NAS and mock
control plane on an internal Docker network. It cannot establish compatibility
with the hosted OpenAI service or a particular TrueNAS release. Tests never
change real NAS settings and never reuse a real tunnel ID or credential.

## Earlier operator-reported baseline

Before this container implementation, the operator reported a successful manual
deployment using tunnel-client 0.0.18, an official released TrueNAS MCP binary,
TrueNAS 25.10.7, a dedicated Readonly Admin account, stdio transport and a personal
ChatGPT plugin. The exact TrueNAS MCP binary version was not recorded in this
repository; it must not be assumed identical to the pinned v0.0.6 build.

That observation does not certify this Linux container. The known operational
lessons are preserved in the setup guide: no `https://` hostname prefix, TLS on
every proxy hop, no shared environment between terminal sessions, and tool catalog
refresh after replacing a demo MCP with TrueNAS.

## Remaining real acceptance evidence

After the agreed cutover, record only non-sensitive outcomes: tunnel polling
ready, `system.info` probe success, plugin tools refreshed, successful read-only
ChatGPT result, restart/retest outcome, and rollback decision if needed. Do not
record keys, raw NAS inventories, private hostnames or tunnel identifiers here.
