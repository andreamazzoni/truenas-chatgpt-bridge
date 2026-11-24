# Licensing and upstream provenance

The bridge's own code is GPL-3.0-only; the complete license is at `LICENSE`.
The image is an aggregation of separate executables, not a fork of their tools.
No upstream source is modified. The added `cmd/bridge-probe/main.go` is clearly
marked bridge code and uses the upstream TrueNAS client package.

| Component | Pinned source | License and retained material |
| --- | --- | --- |
| TrueNAS MCP 1.0.1 | [b01f690](https://github.com/truenas/truenas-mcp/tree/b01f69021991d587bc4ff46a30eb6fe6d3797c40) | GPLv3, `licenses/truenas-mcp-GPL-3.0.txt`, with full source and vendored dependency sources and licenses in the image |
| OpenAI tunnel-client 0.0.21 | [714f2d6](https://github.com/openai/tunnel-client/tree/714f2d67844b660af25754f1d19b0360b346b13b) | Apache-2.0, with the license and NOTICE retained in the repo and image and the dependency license inventory and SPDX SBOM in the image |
| Go toolchain | 1.27.4 official image, locked index digest | Required to build the TrueNAS-based binaries |
| Python/Debian runtime | 3.13.18 slim-bookworm official image, locked index digest | Python and installed package licenses remain in the base image |

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
