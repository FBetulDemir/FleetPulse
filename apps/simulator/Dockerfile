# syntax=docker/dockerfile:1
# Build from the repository root: docker build -f apps/simulator/Dockerfile .

FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY packages/contracts/pyproject.toml packages/contracts/
COPY apps/backend/pyproject.toml apps/backend/
COPY apps/simulator/pyproject.toml apps/simulator/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-workspace --package fleetpulse-simulator

COPY packages/contracts packages/contracts
COPY apps/simulator apps/simulator
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --package fleetpulse-simulator


FROM python:3.13-slim
RUN useradd --system --uid 10001 fleetpulse
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER fleetpulse
CMD ["fleetpulse-simulator"]
