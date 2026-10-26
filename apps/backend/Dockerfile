# syntax=docker/dockerfile:1
# One image for both backend processes:
#   API (default):  uvicorn fleetpulse_backend.api.app:app
#   Worker:         fleetpulse-worker
# Build from the repository root: docker build -f apps/backend/Dockerfile .

FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Install dependencies first so that code changes do not invalidate this layer.
COPY pyproject.toml uv.lock ./
COPY packages/contracts/pyproject.toml packages/contracts/
COPY apps/backend/pyproject.toml apps/backend/
COPY apps/simulator/pyproject.toml apps/simulator/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-workspace --package fleetpulse-backend

COPY packages/contracts packages/contracts
COPY apps/backend apps/backend
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --package fleetpulse-backend


FROM python:3.13-slim
RUN useradd --system --uid 10001 fleetpulse
# Same path as the build stage, because the virtualenv's scripts reference it.
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER fleetpulse
EXPOSE 8000
CMD ["uvicorn", "fleetpulse_backend.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
