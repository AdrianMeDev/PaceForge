# syntax=docker/dockerfile:1
FROM node:24-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build


FROM caddy:2.10-alpine AS runtime

RUN addgroup -S -g 10001 paceforge \
    && adduser -S -u 10001 -G paceforge -H -s /sbin/nologin paceforge

COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=builder /app/dist/paceforge/browser /srv

RUN caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile \
    && chown -R paceforge:paceforge /srv /data /config

USER paceforge
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/healthz"]

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
