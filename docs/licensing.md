# Licensing and upstream provenance

The bridge's own code is GPL-3.0-only; the complete license is at `LICENSE`.
The image is an aggregation of separate executables, not a fork of their tools.
No upstream source is modified. The added `cmd/bridge-probe/main.go` is clearly
marked bridge code and uses the upstream TrueNAS client package.

| Component | Pinned source | License and retained material |
| --- | --- | --- |
| TrueNAS MCP 0.0.6 | [542e59d0](https://github.com/truenas/truenas-mcp/tree/542e59d0f8b2909fe25cbc29ea23c7908fd2f6d7) | GPLv3, `licenses/truenas-mcp-GPL-3.0.txt`; full source and vendored dependency sources/licenses in image |
| OpenAI tunnel-client 0.0.18 | [274a5588](https://github.com/openai/tunnel-client/tree/274a5588414819f063d27100a4fb1096aae3830f) | Apache-2.0, license and NOTICE retained in repo and image; release dependency license inventory and SPDX SBOM retained |
| Go toolchain | 1.25.12 official image, locked index digest | Build-time only; source build requires the documented Go compiler |
| Python/Debian runtime | 3.13.13 slim-bookworm official image, locked index digest | Their own and installed package licenses remain in the base image |

TrueNAS source is downloaded using an immutable commit and a checked SHA-256.
Go dependencies are checked against upstream `go.sum`, verified, then vendored.
The final image includes `/usr/share/bridge/source/truenas-mcp/`, including the
added probe and every vendored Go package required by the two TrueNAS-based
executables. `/usr/share/bridge/versions.lock.json` records build provenance.

The official OpenAI release ZIP is checked against the SHA-256 locked from GitHub's
release metadata. Its `LICENSE`, `NOTICE`, `*-licenses.txt` and SPDX JSON are
copied into `/usr/share/bridge/licenses/tunnel-client/`. The ZIP also contains a
separate `cloudflared` executable; this project does **not** install or run it.
The full tunnel-client binary and its dependency license material are preserved.

For redistribution, accompany the TrueNAS GPL binaries with complete corresponding
source and build instructions, including bridge source and build scripts from the
exact repository revision, rather than relying solely on an upstream URL. The image
already includes the upstream/vendored source and probe; distribute the bridge
repository alongside any exported image so recipients also receive its Dockerfile,
fetch/lock files and runtime/operations scripts. Preserve Apache license/NOTICE,
all dependency attribution obligations, and any source obligations identified in
the release license inventory. Do not strip `/usr/share/bridge` to shrink exports.

Before redistributing an entire OS image, review its installed package license
obligations as well. This project performs no public publication or registry push.
TrueNAS and OpenAI names identify upstream projects and grant no trademark rights.
