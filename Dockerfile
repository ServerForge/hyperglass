FROM python:3.12-alpine AS base
WORKDIR /opt/hyperglass
ENV HYPERGLASS_APP_PATH=/etc/hyperglass
ENV HYPERGLASS_HOST=0.0.0.0
ENV HYPERGLASS_PORT=8001
ENV HYPERGLASS_DEBUG=false
ENV HYPERGLASS_DEV_MODE=false
ENV HYPERGLASS_REDIS_HOST=redis
ENV HYPERGLASS_DISABLE_UI=false
ENV HYPERGLASS_CONTAINER=true
RUN apk add --no-cache build-base nodejs npm && npm install -g pnpm@9

# Dependencies are installed before copying the source, so they're cached until a lockfile changes.
FROM base AS dependencies
COPY requirements.lock ./
RUN grep -v '^-e' requirements.lock > /tmp/requirements.txt \
    && pip3 install --no-cache-dir -r /tmp/requirements.txt
COPY hyperglass/ui/package.json hyperglass/ui/pnpm-lock.yaml hyperglass/ui/pnpm-workspace.yaml hyperglass/ui/
RUN cd hyperglass/ui && pnpm install --frozen-lockfile

FROM dependencies AS hyperglass
COPY . .
# The UI is built into the image, without configuration. At startup, hyperglass only renders the
# configuration into the existing build, so configuration changes don't require a new UI build.
RUN pip3 install --no-cache-dir --no-deps -e . \
    && mkdir -p "$HYPERGLASS_APP_PATH" \
    && python3 -m hyperglass.console build-ui

EXPOSE ${HYPERGLASS_PORT}
CMD ["python3", "-m", "hyperglass.console", "start"]
