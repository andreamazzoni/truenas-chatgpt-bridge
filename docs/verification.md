# Verification record

This file separates build/fixture observations from real-service acceptance;
it is not a general compatibility guarantee.

## Current sources: TrueNAS MCP 0.0.7 (2026-10-28)

Pinned components are TrueNAS MCP 0.0.7 at
`e5a2d27fe61006847f1e2715d6349cedef0089df`, OpenAI tunnel-client 0.0.18 and
Go 1.27.3. Source/artifact checksums and multi-architecture base image digests
are recorded in `versions.lock.json` and `Dockerfile`.

| Check | Result |
| --- | --- |
| Compose configuration and unit tests | Passed; 43 tests, including staged settings, failed preflight/health and configuration rollback |
| Linux ARM64 image | Built and executed against isolated fixtures; official MCP discovery and `system_info` passed over JSON-RPC 2.0 with `auth.login_ex` |
| Linux AMD64 image | Full cross-build completed; metadata confirms `linux/amd64` and non-root `1000:1000`; runtime not executed |
| Management tool discovery | Fixture verified `create_dataset`, `start_app`, `stop_app`, upstream annotations and the `confirm` parameter; no NAS write was executed |
| Restart, update and rollback | Passed with the actual operations functions; 0.0.6 → 0.0.7 → 0.0.6 restored the exact image and original settings schema/public CA |
| Health/reporting and reset | Readable and JSON reports, graceful shutdown and repeated reset passed in temporary Compose projects |
| Credential exclusion | Audit passed tracked paths, pins, non-root image configuration and ignored canary rebuild/layer scan |
| Real NAS, hosted tunnel and ChatGPT with 0.0.7 | Operator confirmed successful upgrade, status/probe and the requested ChatGPT call after testing the candidate |

The fixture accepts the legacy protocol only to test the retained 0.0.6 image;
the new runtime exclusively uses `/api/current`. Upstream requires TrueNAS
25.04+, but that minimum is not a verified real-service result for this bridge.
The host memory-limit limitation recorded below remains unchanged.

After the isolated checks, the operator reported that all requested deployment
tests worked, including the real-service ChatGPT check. This is operator-reported
acceptance of the 0.0.7 deployment; it does not establish AMD64 runtime support
or compatibility with every TrueNAS release. The automated fixtures did not
contact real services or change real credentials. Real-service rollback was
not separately reported; its image/configuration recovery was verified offline.

Reproduce the migration test with separately retained local images:

```sh
BRIDGE_TEST_IMAGE=truenas-chatgpt-bridge:mcp-0.0.7-candidate BRIDGE_TEST_LEGACY_IMAGE=truenas-chatgpt-bridge:probe-race-fix-98452e5 python3 tests/integration.py
```

The legacy tag names the previously tested local 0.0.6 image, not a public
registry image. Substitute your own retained and verified local tag if needed.

## Historical 0.0.6 acceptance (2026-10-26 and 2026-10-27)

The following records distinguish local fixture checks from real-service cutover evidence:

| Check | Status |
| --- | --- |
| Compose configuration | Passed `docker compose config --quiet` |
| Native Linux ARM64 build and execution | Passed; non-root, read-only root, no published ports, all capabilities dropped |
| Linux AMD64 cross-build | Full image built and loaded locally on 2026-10-27 after operator Docker Hub login, using tag `truenas-chatgpt-bridge:0.1.0-amd64`; all 3 executables previously verified as static x86-64 ELF; AMD64 execution not tested |
| Strict hostname/secret permissions, health distinction and probe-state tests | 10 tests passed, including concurrent probe publication, failed-publication cleanup and NAS-failure reporting |
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

The initial full AMD64 build was blocked by Docker Hub's anonymous pull quota
(HTTP 429). After the operator authenticated Docker locally, the unchanged build
completed successfully on 2026-10-27. The image was loaded under a separate local
tag; no image was published and the live ARM64 bridge remained healthy. Docker
image inspection confirmed `linux/amd64` and non-root user `1000:1000`.

To reproduce the successful full AMD64 build:

```sh
docker buildx build --platform linux/amd64 -t truenas-chatgpt-bridge:0.1.0-amd64 --load .
```

The AMD64 image has not been executed. Startup, fixture integration, restart and
rollback still require an AMD64 host or an explicitly identified emulation test.
Successful cross-compilation and image assembly do not establish runtime support.

To reproduce the successful AMD64 artifact build without an AMD64 base
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

## Guided first-install acceptance (2026-10-28)

The guided `install` command passed 17 unit tests, including rejection of an
existing deployment, validation before startup, explicit single-client
confirmation, and recovery of saved settings/credentials after interrupted
hidden input. The isolated Docker fixture also passed native execution,
restart, candidate replacement, rollback and graceful shutdown using the
existing local runtime image; no runtime image changes were needed for this CLI
addition.

The operator stopped the original deployment and tested a fresh checkout under
a separate Compose project and image tag, reusing the tunnel without concurrent
clients. Initial health failures showed successful NAS reads but no successful
tunnel polling; tunnel logs identified a rejected OpenAI runtime credential.
After supplying working credentials locally, the operator reported success and
then confirmed a further installation from scratch worked. This is
operator-reported first-install acceptance, not a new architecture or TrueNAS
compatibility claim. No credentials or private identifiers are recorded here.

## Local reset verification (2026-10-28)

The suite passed 28 unit tests after adding the confirmed `reset` command,
including cancellation, Docker failure, filesystem failure, checkout ownership,
symlink boundaries and locking while local state is removed. The isolated Docker
fixture passed restart/rollback and then ran reset twice: the temporary project's
container and network were removed, its configuration and fake credentials were
deleted, and its Compose source and runtime image were preserved. This used the
existing local runtime image; only host-side CLI code changed. No reset of the
real deployment or deletion of real credentials was performed by these tests.

## Readable status verification (2026-10-28)

The suite passed 36 unit tests after making host-side `status` and `probe`
readable by default. Coverage includes cached NAS results, absent probes,
missing/stale polling, stopped containers, failed probes and preservation of
the original runtime output and exit codes through `--json`. The isolated Docker
fixture verified both readable and JSON reports for each command, followed by
the existing restart, rollback and reset checks. The runtime image and Docker
health output are unchanged; these checks do not establish a real ChatGPT call.
