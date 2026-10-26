# FleetPulse

Real-time monitoring for a simulated fleet of electric vessels: live positions, sensor telemetry, history and alerts.

> **Status:** in development. A live demo link, screenshots and setup instructions will be added as features land.

## Planned architecture

```text
Vessel simulator ──MQTT──▶ Mosquitto ──▶ Worker ──▶ InfluxDB (telemetry)
                                │           └─────▶ PostgreSQL (alerts, state)
                                ▼
                         FastAPI (REST + WebSocket) ──▶ Angular app
```

- **Frontend:** Angular, TypeScript, Angular Material, ECharts, Leaflet
- **Backend:** Python, FastAPI, Pydantic, SQLAlchemy, Alembic
- **Data and messaging:** PostgreSQL, InfluxDB 3, MQTT (Mosquitto)
- **Infrastructure:** Docker Compose, GitHub Actions, Terraform, Caddy

## Run locally

Requires [Docker](https://docs.docker.com/get-docker/) and [uv](https://docs.astral.sh/uv/).

```sh
docker compose up --build          # broker, InfluxDB, simulator, worker, API
uv sync                            # Python tooling for tests and scripts
uv run python scripts/smoke_test.py
```

- API docs: http://localhost:8000/api/docs
- Live events: connect to `ws://localhost:8000/ws` and send `{"type": "subscribe", "channel": "fleet"}`

## Development

```sh
uv run pytest         # tests
uv run ruff check .   # lint
uv run mypy           # type check
uvx pre-commit install
```

## License

[MIT](LICENSE)
