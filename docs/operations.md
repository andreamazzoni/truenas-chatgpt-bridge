# Operations

Run commands on the clone host. The Python scripts locate their checkout using
their own path; the shell's working directory is irrelevant. Docker must be
accessible to the operator. Do not enable shell tracing while handling credentials.

## Start, inspect, restart, stop

```sh
python3 scripts/bridge.py start --single-instance-confirmed
python3 scripts/bridge.py status
python3 scripts/bridge.py probe
python3 scripts/bridge.py restart
python3 scripts/bridge.py stop
docker compose logs --tail 100 bridge
```

`status` and `probe` print readable reports by default. They separate container
state, tunnel process liveness, startup readiness, recent OpenAI polling and the
NAS read result. `status` performs no NAS request: it labels the previous result
as saved and shows its UTC timestamp and age. An old successful result is not
evidence that the NAS is reachable now. Use `probe` for a fresh read-only check.
Neither command can establish whether a ChatGPT call succeeded.

Scripts that consumed the previous JSON output must now request it explicitly:

```sh
python3 scripts/bridge.py status --json
python3 scripts/bridge.py probe --json
```

The runtime JSON schema and its exit codes are preserved: `status` returns zero
when its runtime report is available, even if a reported check is unhealthy;
`probe` returns success based on the fresh NAS result, independently of tunnel
readiness. Readable output also reports a stopped or absent container without
attempting a NAS request and returns a nonzero exit code. Direct container
runtime commands and Docker health checks continue to use JSON.

The confirmation flag means the operator has stopped any previous host's stdio
tunnel. Docker starts this deployment automatically after host/daemon restart if
it was running. `stop` intentionally suppresses that restart until started again.
Do not restart the Docker daemon as a bridge test: it affects unrelated services.

After a fresh installation, verify both the NAS probe and a read-only ChatGPT
call. An unhealthy status is diagnostic, not an instruction to change NAS roles.
For failures inspect `status`, local file permissions and DNS/TLS; check that no
second host is polling the same tunnel. For a live daemon with stale polling,
check OpenAI permissions and network reachability. For a healthy tunnel but failed
NAS probe, check certificates and key/account status in TrueNAS. Avoid raw logging.

## Update while retaining the previous working image

First inspect the candidate upstream release notes, CLI, license and API changes.
Update the lock file's commit/checksum and Dockerfile's pinned versions/digests
together. Build from a clean revision and use a **unique local tag**:

```sh
docker buildx build --load -t truenas-chatgpt-bridge:upgrade-001 .
python3 -m unittest discover -s tests -v
BRIDGE_TEST_IMAGE=truenas-chatgpt-bridge:upgrade-001 python3 tests/integration.py
python3 scripts/bridge.py update --image truenas-chatgpt-bridge:upgrade-001
python3 scripts/bridge.py status
```

The update script requires the currently running container to be healthy, resolves
the candidate to its immutable local image ID, and preflights its files and TLS
without starting a tunnel. It tags the old image with a unique `rollback-*` name
and records it in ignored `.local/rollback.json`. It then **stops the current
container before recreating it**, waits for health and saves the selected immutable
image ID in `.env`. Never scale this service or start a parallel Compose project
against the same real tunnel.

Keep the old source revision too: commit local changes before an update and record
the previous revision in a private change record. The image rollback command
assumes the old and new revisions share the current Compose/settings layout. If
that layout changes, restore the old checkout/configuration while stopped before
recreating its image. No automatic schema migration is implemented.

After health passes, refresh changed plugin tools and verify a read-only ChatGPT
call. The script cannot perform that user-facing acceptance step. If an update
fails health, it leaves the candidate available for diagnosis and the previous
image retained; explicitly roll back. It does not blindly replay NAS tool calls.

## Rollback

```sh
python3 scripts/bridge.py rollback
python3 scripts/bridge.py status
python3 scripts/bridge.py probe
```

Rollback verifies the retained image exists locally, stops the current container,
recreates the exact previous image, waits for health and saves its image ID in
`.env`. Repeat the read-only ChatGPT test. The rollback record remains available;
the next successful update establishes a new immediate rollback target.

Do not prune retained images before accepting the update. An image tag protects
against normal dangling-image cleanup, but `docker image prune -a` can still
remove unused rollback images. Export retained images to protected local storage
if stronger retention is needed. Never push them to a public registry.

**Rolling back the bridge does not undo any changes already made to TrueNAS.**
It also does not restore revoked/expired keys or portal permissions.

## Reset a local installation

In a local interactive terminal, run:

```sh
python3 scripts/bridge.py reset
```

The command displays the checkout, resolved Compose project and files to delete.
Type the exact word `RESET` to confirm; any other answer cancels without changes.
Use the same `COMPOSE_PROJECT_NAME` environment setting, if any, that you used
when installing. Reset refuses containers from another checkout sharing that
project name. It rejects symlinked configuration paths rather than following
them outside the checkout. Internal symlinks are removed without deleting their
targets.

Reset runs Compose `down --remove-orphans` and verifies that no containers or
Compose-owned networks remain for that project. If Docker cleanup fails, local
configuration and credentials are kept for recovery. Once cleanup succeeds, it
deletes `.env`, `config/local/`, `secrets/` (including backups stored there), and
`.local/` with its rollback metadata. This does not require working credentials,
NAS reachability or a healthy tunnel. An interrupted reset can be retried;
filesystem errors may leave partial local cleanup.

Repository files, Git history, Docker images/build cache and external networks
are preserved. No global Docker prune is run. The checkout lock remains held
through deletion, preventing another current CLI operation in this checkout
from starting during reset. Coordinate other checkouts and manually started
clients separately. Reset does not revoke keys, delete the OpenAI tunnel or
ChatGPT plugin, undo NAS changes, or guarantee secure erasure from disk/backups.

After reset, `python3 scripts/bridge.py install` starts configuration again.
Exported `COMPOSE_PROJECT_NAME` and `BRIDGE_IMAGE` variables remain in the current
shell; keep or unset them deliberately before reinstalling or switching projects.

## Backup categories

| Category | Include | Restore method |
| --- | --- | --- |
| Repository | Committed code, lock file, docs, license files | Clone the private remote and select the recorded revision |
| Local settings | `.env`, `config/local/`, `.local/rollback.json`, image IDs/revision record | Restore with original access permissions; check hostname/CA for the target host |
| Credentials | `secrets/` and any external credential source | Back up separately with encryption and restricted access; never commit or attach to issues |
| Images | Working and previous immutable images | `docker image save` into protected storage, `docker image load` on compatible architecture |
| Bridge runtime | No required durable application state | Recreated; tmpfs health, sessions and in-memory tasks are discarded |
| TrueNAS data | NAS datasets and configuration are outside this project | Use the NAS's independent backup/recovery plan |

Back up repository and secrets separately. A repository clone alone cannot
recover keys or local trust/configuration. A Docker volume backup is unnecessary
for the bridge: no application volume exists. Docker's rotated logs are optional
operational records, not application restore data.

## Restore

1. Ensure the old deployment cannot automatically restart the same stdio tunnel.
2. Restore/clone the recorded code revision, or load the saved working image for
   the target architecture. Keep the previous working image available.
3. Restore private settings and decrypt credentials locally, without displaying
   their contents. Set `secrets/` and `config/local/` to mode 0700 and key files
   to 0600. Ensure their ownership and `.env` UID/GID match the new operator.
4. Run `python3 scripts/bridge.py validate`; certificate and DNS checks must pass
   before authentication. Reuse the existing tunnel and keys if still valid.
5. Start with `--single-instance-confirmed`, run the read-only NAS probe, refresh
   tools if necessary, and confirm a read-only ChatGPT call.

NAS data restoration and reversal of earlier NAS operations are separate work.
