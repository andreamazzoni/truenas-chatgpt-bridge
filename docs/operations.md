# Operations

Use the [basic commands](../README.md#basic-commands) to start, stop, or
restart the bridge. Run Compose commands from the checkout, using the same
project name as the installation.

## Check the connection

| Check | What it tells you |
| --- | --- |
| `status` | Container state, tunnel process liveness, startup readiness, recent polling, and the last saved NAS result with its timestamp. |
| `probe` | Whether a fresh, read-only NAS request succeeded. It also reports tunnel state. |
| Docker health | Whether the tunnel is ready, has polled successfully within 120 seconds, and a fresh NAS read succeeded. |
| ChatGPT read | Whether the plugin can retrieve NAS data through the tunnel in your workspace. |

Compare the read-only ChatGPT result with the TrueNAS UI.
[ChatGPT setup](setup.md#connect-the-custom-app-in-chatgpt)

Add `--json` to `status` or `probe` for the original runtime format and exit
codes. With a running container, `status` succeeds when the report is available.
`probe` succeeds when the NAS read does, independently of tunnel readiness.

Docker restarts an exited container unless it was explicitly stopped. It reports
a running unhealthy container separately.

## Maintenance commands

| Operation | Command |
| --- | --- |
| Build from pinned inputs | `python3 scripts/bridge.py build` |
| Check Compose configuration, file access, and TLS | `python3 scripts/bridge.py validate` |
| Inspect recent logs locally | `docker compose logs --tail 100 bridge` |

## Rotate a key

1. Prepare the replacement in TrueNAS or OpenAI Platform with the permissions
   needed by the bridge.
2. Stop the bridge with `python3 scripts/bridge.py stop`, then remove its
   stopped container with `docker compose rm -f bridge` from the checkout so
   Compose will remount the credential files. A restart alone can keep an
   old file mounted.
3. Move the key file being replaced to protected encrypted storage outside the
   checkout. Run `python3 scripts/setup.py` and enter its replacement at the
   hidden prompt. Setup keeps the other key file. If the TrueNAS key owner
   changes, enter the new username.
4. Check that the tunnel is free, then run
   `python3 scripts/bridge.py start --single-instance-confirmed`. Run
   `python3 scripts/bridge.py probe` and repeat a read-only ChatGPT call before
   revoking the previous key if it is still active.

## Update and rollback

Review upstream release notes, CLI, API, and licensing changes. Update source
and artifact pins in `versions.lock.json` and version and digest pins in
`Dockerfile` together. Build and test a uniquely tagged local candidate.
[Development and offline checks](development.md)

```sh
docker buildx build --load -t truenas-chatgpt-bridge:upgrade-001 .
python3 -m unittest discover -s tests -v
BRIDGE_TEST_IMAGE=truenas-chatgpt-bridge:upgrade-001 python3 tests/integration.py
python3 scripts/bridge.py update --image truenas-chatgpt-bridge:upgrade-001
```

Update requires a healthy running bridge. It preflights the candidate image and
configuration without starting another tunnel, saves the current image and
settings/public CA in a rollback record, then stops the bridge before replacing
it. After health passes it saves the candidate image ID in `.env`. Refresh
changed plugin tools and verify a read-only ChatGPT call.

If the candidate fails, inspect its status and run
`python3 scripts/bridge.py rollback` from the new checkout. Rollback reads the
previous image and configuration from `.local/rollback.json`, preflights them,
and stops the candidate before restoring them. Run `status`, `probe`, and
the read-only ChatGPT check again.

Keep the previous image and source revision until you accept the update.
`docker image prune -a` can remove unused rollback images. Export images to
protected local storage if needed. Rollback assumes both revisions share the
Compose layout. If it changed, or the rollback record lacks a configuration
snapshot, restore the matching checkout, settings, and image while stopped.
The rollback record excludes credentials. Restore credentials and portal
permissions separately. Reversing changes made through the plugin requires
a separate operation in TrueNAS.

## Upgrade from TrueNAS MCP 0.0.6

Build and test a uniquely tagged 0.0.7 candidate first. Keep the existing
deployment running with its original settings until the coordinated update;
do not run setup on its mounted configuration to add the new username.

```sh
docker buildx build --load -t truenas-chatgpt-bridge:mcp-0.0.7-candidate .
BRIDGE_TEST_IMAGE=truenas-chatgpt-bridge:mcp-0.0.7-candidate python3 tests/integration.py
python3 scripts/bridge.py update --image truenas-chatgpt-bridge:mcp-0.0.7-candidate
```

Update asks locally for the **TrueNAS username that owns the existing API key**
when it is missing from the old settings. No key needs to be entered again.
`--api-user USERNAME` is also available for this non-secret setting. The candidate
uses `/api/current` and requires TrueNAS 25.04+. The preflight checks files and
TLS without authenticating; health after replacement verifies the NAS read and
tunnel polling. Refresh the ChatGPT tool catalog and test `system_info` again.
Some upstream destructive operations now require `confirm: true` and otherwise
return a preview; query and management tools remain available according to NAS
permissions. The upstream optional read-only/allow/deny flags are not currently
part of this bridge's configuration.

If the candidate fails, use `rollback` from this new checkout. It stops the
candidate before restoring both the original image and the old settings schema.
Do not switch back to the old scripts before restoring the configuration.

## Coordinated cutover

1. Build and validate on the new host. Check UID/GID, DNS, and TLS on both
   proxy hops if applicable. Keep the old deployment available for recovery.
2. Stop the old client, disable its automatic relaunch, and confirm it exited.
3. On the new host, run `python3 scripts/bridge.py start --single-instance-confirmed`,
   then `status` and `probe`. Refresh the existing ChatGPT plugin's tools if
   the catalog changed. Verify `system_info` from ChatGPT.
4. Restart the new bridge and repeat the read-only ChatGPT check.
5. To revert, stop the new bridge and confirm it exited before starting the old
   client. Refresh the plugin tools again if needed.

## Reset a local installation

Run `python3 scripts/bridge.py reset` in a local terminal and type `RESET` to
confirm. Use the installation's `COMPOSE_PROJECT_NAME` override, if any.
Reset removes the project's containers and Compose-owned networks, then
deletes `.env`, `config/local/`, `secrets/`, and `.local/` including rollback
metadata. It keeps the checkout, images, build cache, and external networks.

If Docker cleanup fails, the local files are kept. Retry an interrupted reset
before reinstalling. Revoke keys and remove the tunnel or plugin separately
in their respective portals. Keep encrypted backups outside the checkout.

## Backup categories

| Category | Include | Restore method |
| --- | --- | --- |
| Repository | Committed code, lock file, docs, license files | Clone the private remote and select the recorded revision |
| Local settings | `.env`, `config/local/`, `.local/rollback.json` (previous settings/public CA), image IDs/revision record | Restore with original access permissions; check hostname/CA for the target host |
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

## Troubleshooting

| Symptom | First thing to check |
| --- | --- |
| Build fails with a Docker Hub pull-rate message (HTTP 429) | Run `docker login` locally as the same user, complete the browser login, then retry. An authenticated account still has its own applicable limits. See [Docker's login guide](https://docs.docker.com/reference/cli/docker/login/). |
| Setup cannot verify TLS | Check DNS, the hostname on the certificate and your CA selection. With a proxy, also check HTTPS on its backend. |
| Container cannot read a credential file | Use the same non-root account for setup and operation; check file ownership and the UID/GID saved in `.env`. |
| Process is live but `tunnel_ready` is false | Check outbound connectivity, the tunnel ID, runtime-key permissions and any required organization context. |
| `nas_probe.ok` is false | Check NAS reachability, TLS and the key's associated user/permissions. A successful probe requires `system.info` access. |
| Health is good but ChatGPT discovery/calls fail | Check that the plugin uses the intended tunnel, refresh its tools and confirm there is no second stdio client. |

Avoid sharing raw logs publicly: keys should stay hidden, and logs can still
contain private hostnames or identifiers.
