# The pinned install, built reproducibly.
#
# DT-228. This image exists to make one claim checkable: that
# `uv tool install --with-requirements` produces the versions uv.lock names,
# and a bare `uv tool install .` does not. On the host that difference went
# unnoticed for two releases -- the deployment carried mcp 1.29.0 against a
# lock pinning 1.28.1, both satisfy <2, and nothing reported it until
# drunken-doctor grew a check (DT-252).
#
# It is deliberately NOT a serving image. The MCP servers speak stdio, so a
# long-running container would be a process reading stdin from nobody. A
# serving image needs the HTTP transport, which is DT-226 -- reviewed and not
# approved, because FastMCP silently disables DNS-rebinding protection on a
# non-loopback host. Manifests for that transport are deferred to that ticket
# rather than written against something that does not exist.
#
#   docker build -t drunken-team:pinned .
#   docker run --rm drunken-team:pinned          # reports what it installed

FROM python:3.13-slim

# uv comes from its own published image rather than a curl|sh: the version is
# pinned by the tag, and nothing is fetched from the network at build time
# beyond the declared bases.
COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /usr/local/bin/uv

ENV UV_TOOL_BIN_DIR=/usr/local/bin \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /src
COPY . /src

# Export the lock, then install against it. The two steps are separate on
# purpose: if the export fails the build fails here, rather than quietly
# falling back to an unpinned install that looks identical from outside.
RUN uv export --format requirements-txt --no-emit-project --no-dev \
        > /tmp/requirements.lock.txt \
 && uv tool install . --with-requirements /tmp/requirements.lock.txt

# State lives under $DRUNKEN_HOME and never beside the code (core/paths.py).
# A container mounts a volume here; nothing else has to know.
ENV DRUNKEN_HOME=/var/lib/drunken
RUN mkdir -p /var/lib/drunken && chmod 700 /var/lib/drunken

# Says what it actually installed, so the image can answer the question it was
# built for without anyone reading the build log.
CMD ["drunken-doctor", "--json"]
