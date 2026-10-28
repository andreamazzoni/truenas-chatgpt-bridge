FROM --platform=$BUILDPLATFORM python:3.13.13-slim-bookworm@sha256:355bfa66770995d7e9a0da4b3473b44d0cb451f6b56f5615ad9c39e3c4eca03f AS fetch
ARG TARGETARCH
WORKDIR /build
COPY versions.lock.json build/fetch.py ./
RUN python fetch.py "$TARGETARCH"

FROM --platform=$BUILDPLATFORM golang:1.27.3-bookworm@sha256:d9b6a1beb9474adc2a1ce842573639b44b2a0dd49b6669f51d3821baf9ec37c9 AS compile
ARG TARGETOS
ARG TARGETARCH
ENV GOTOOLCHAIN=local CGO_ENABLED=0 GOMAXPROCS=2
WORKDIR /src/truenas-mcp
COPY --from=fetch /build/source/ ./
COPY build/probe.go ./cmd/bridge-probe/main.go
RUN go mod download && go mod verify && go mod vendor
RUN GOOS=$TARGETOS GOARCH=$TARGETARCH go build -mod=vendor -trimpath -buildvcs=false -ldflags='-s -w -buildid= -X main.Version=0.0.7' -o /out/truenas-mcp ./cmd/truenas-mcp \
    && GOOS=$TARGETOS GOARCH=$TARGETARCH go build -mod=vendor -trimpath -buildvcs=false -ldflags='-s -w -buildid=' -o /out/bridge-probe ./cmd/bridge-probe

FROM scratch AS binaries
COPY --from=compile /out/ /
COPY --from=fetch /build/tunnel-client /tunnel-client

# All RUN instructions execute on BUILDPLATFORM. Target runtime is assembled
# with COPY only, allowing AMD64 image builds on ARM64 without QEMU.
FROM python:3.13.13-slim-bookworm@sha256:355bfa66770995d7e9a0da4b3473b44d0cb451f6b56f5615ad9c39e3c4eca03f AS runtime
LABEL org.opencontainers.image.title="truenas-chatgpt-bridge" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.licenses="GPL-3.0-only"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp/home
COPY --from=fetch --chmod=0555 /build/tunnel-client /usr/local/bin/tunnel-client
COPY --from=compile --chmod=0555 /out/ /usr/local/bin/
COPY --from=compile /src/truenas-mcp/ /usr/share/bridge/source/truenas-mcp/
COPY --from=fetch /build/legal/ /usr/share/bridge/licenses/tunnel-client/
COPY LICENSE NOTICE /usr/share/bridge/
COPY licenses/ /usr/share/bridge/licenses/
COPY versions.lock.json /usr/share/bridge/
COPY bridge/ /opt/bridge/
USER 1000:1000
WORKDIR /opt/bridge
ENTRYPOINT ["python", "/opt/bridge/runtime.py"]
CMD ["run"]
