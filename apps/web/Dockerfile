# syntax=docker/dockerfile:1
# Builds the Angular app and serves it with Caddy.
# The Caddyfile is mounted at runtime (see compose.yaml), so the same image works
# locally and in production.

FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY . .
RUN npx ng build


FROM caddy:2-alpine
COPY --from=build /app/dist/fleetpulse-web/browser /srv
