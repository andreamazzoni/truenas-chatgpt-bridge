# Development and offline checks

For installation and daily use, start with the [quick start](../README.md).

Stable inputs are pinned in `versions.lock.json` and `Dockerfile`: tunnel-client
0.0.18, TrueNAS MCP 0.0.7, Go 1.27.3 and Python 3.13.13, including upstream artifact
checksums and base image digests. TrueNAS MCP is built from source. Upstream code
is kept unchanged, with a small bridge probe added alongside it.

To build a candidate and run the offline checks on your host's architecture:

```sh
docker buildx build --load -t truenas-chatgpt-bridge:dev-001 .
python3 -m unittest discover -s tests -v
BRIDGE_TEST_IMAGE=truenas-chatgpt-bridge:dev-001 python3 tests/integration.py
python3 scripts/audit.py --image truenas-chatgpt-bridge:dev-001 --build-check
```

The integration test needs host `openssl`. It uses its own temporary Compose
project, test credentials and an internal Docker network, without contacting a
real NAS or OpenAI. Its candidate and rollback image tags remain local.

For separate architecture builds:

```sh
docker buildx build --platform linux/arm64 -t truenas-chatgpt-bridge:0.1.0-arm64 --load .
docker buildx build --platform linux/amd64 -t truenas-chatgpt-bridge:0.1.0-amd64 --load .
```

Cross-builds need no emulation because build commands run on the builder's native
architecture. Running the resulting image requires a matching host or emulation;
the AMD64 runtime has not yet been tested. Pinned inputs and stripped Go build
paths/IDs help repeatability; OCI exporter timestamps and attestations can still
produce different image digests across independent builds.

To verify migration from a retained, previously tested 0.0.6 image, set
`BRIDGE_TEST_LEGACY_IMAGE` as well as the new `BRIDGE_TEST_IMAGE` when running
`tests/integration.py`. The fixture accepts both NAS protocols and checks that
rollback restores the legacy settings schema along with the old image. Both
images must already exist locally; no live deployment is used.
