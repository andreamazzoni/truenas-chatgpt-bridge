# Project principles

- GitHub repository: https://github.com/andreamazzoni/truenas-chatgpt-bridge
  (private, remote `github`, default branch `main`). The configured private
  `origin` remains the only push destination under the policy below.
- Scope: a generic, self-hosted TrueNAS to ChatGPT bridge using the official
  TrueNAS MCP server and OpenAI Secure MCP Tunnel. No autonomous agent, other
  backends, public plugin, or public registry publishing.
- Docker Compose is the primary interface. Everything runs on the clone host;
  no personal paths, NAS addresses, SSH deployment, or development host details
  in public configuration.
- Keep upstream tools and protocols upstream. Pin release commits, artifact
  checksums, toolchains, and base image digests for Linux ARM64 and AMD64.
- Preserve licenses, notices, dependency licenses and corresponding source when
  distributing binaries. Document verified compatibility separately from claims.
- Never read or print real secret contents. Accept secrets only via local hidden
  terminal input; keep them out of Git, build contexts, images, arguments and logs.
  Mount credential files read-only. Use a minimal file-to-environment adapter only
  where the upstream component requires it.
- Require verified TLS to TrueNAS, including the proxy-to-NAS hop. Reject schemes,
  paths and embedded credentials in the hostname configuration. Do not offer an
  insecure switch. Prefer a dedicated Readonly Admin account for initial use.
- Run non-root, read-only, without privileges, Docker socket, NAS dataset mounts
  or published diagnostic ports. Use bounded logs and graceful shutdown.
- Report process liveness, recent tunnel polling, and successful NAS read probes
  separately. Never present readiness as proof of a successful ChatGPT call.
- One active stdio tunnel instance per tunnel ID. Stop the old instance before
  starting a replacement, including during migration and rollback.
- Do not change other host services, NAS settings, or an existing deployment.
  Real cutover and ChatGPT verification require the operator's coordination.
- Keep small meaningful commits and push only to the configured private origin.
  Do not publish repositories, images or plugins publicly.
- Validate Compose, native builds, restart and rollback with isolated fixtures
  before requesting credentials. Do not claim end-to-end success without evidence.
