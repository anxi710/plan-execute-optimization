FROM node:22-bookworm-slim AS node-runtime
FROM python:3.11-slim-trixie AS runtime-base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/workspace/src
WORKDIR /workspace/src

RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends openjdk-21-jre-headless \
    && rm -rf /var/lib/apt/lists/*

FROM runtime-base AS wheels
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake \
    && rm -rf /var/lib/apt/lists/*
COPY toolkit/requirements.txt toolkit/requirements-core.txt toolkit/
RUN mkdir /build-bin \
    && printf '%s\n' '#!/bin/sh' 'exec /usr/bin/make "$@" -j4' > /build-bin/make \
    && chmod +x /build-bin/make \
    && PATH="/build-bin:$PATH" python -m pip wheel --no-cache-dir --wheel-dir /wheels -r toolkit/requirements.txt

FROM runtime-base
RUN --mount=type=bind,from=wheels,source=/wheels,target=/wheels,readonly \
    python -m pip install --no-cache-dir --no-index /wheels/*.whl \
    && python -m pip check
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules/npm/ /usr/local/lib/node_modules/npm/
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm
COPY toolkit/ toolkit/
COPY recipe/ recipe/

WORKDIR /workspace
CMD ["bash"]
