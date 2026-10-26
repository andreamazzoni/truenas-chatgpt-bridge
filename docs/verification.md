# Verification record

This file records observations from 2026-10-26, not a general compatibility guarantee.

## Current implementation acceptance

The following records distinguish local fixture checks from real-service cutover evidence:

| Check | Status |
| --- | --- |
| Compose configuration | Passed `docker compose config --quiet` |
| Native Linux ARM64 build and execution | Passed; non-root, read-only root, no published ports, all capabilities dropped |
| Linux AMD64 cross-build | All 3 executables built/verified as static x86-64 ELF; full runtime image blocked by Docker Hub anonymous pull quota (HTTP 429); AMD64 execution not tested |
| Strict hostname/secret permissions and health distinction tests | 7 tests passed |
| Official MCP stdio discovery and `system_info` against TLS fixture | Passed with official TrueNAS MCP 0.0.6 |
| Container restart and graceful shutdown | Offline restart/retest passed with shutdown exit code 0; real deployment also returned healthy after restart |
| Candidate replacement and retained-image rollback | Passed using the actual host update/rollback functions and exact previous image ID |
| Credential exclusion from build context, image and tracked files | Passed tracked-path/token-pattern scan, ignored canary rebuild and scan of every exported image layer; no real credentials supplied |
| Real tunnel polling and read-only NAS call after cutover | Passed after operator-confirmed cutover; fresh polling and official-client `system.info` probe succeeded, including after container restart |
| Personal ChatGPT plugin read-only call | Passed; operator confirmed the requested `system_info` call succeeded against the running deployment after restart |

The operator confirmed stopping the previous stdio tunnel host and HTTPS on the
proxy-to-TrueNAS hop before the real container started. Host and container TLS
preflight passed without authentication. The running bridge subsequently reported
process liveness, startup readiness, recent successful hosted tunnel polling and
a successful read-only NAS probe. A container restart returned the same checks
to healthy. The verified image is retained under a local rollback tag, with its
immutable ID recorded in the ignored local rollback metadata.

The real `system.info` probe uses the official client's separate NAS session.
The operator subsequently confirmed the requested read-only call from ChatGPT,
providing acceptance evidence for the full ChatGPT → hosted tunnel → stdio MCP →
TrueNAS path. No credentials, private endpoints, tunnel IDs or raw NAS results
are recorded here.

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

## ChatGPT acceptance outcome

After the coordinated cutover and successful container restart, the operator
confirmed that the requested read-only `system_info` call from the personal
ChatGPT plugin worked. This completes real-service acceptance for the deployed
Linux ARM64 bridge. The AMD64 runtime and host memory-limit limitations recorded
above remain unchanged; this result does not certify other TrueNAS versions or
account/workspace configurations.
