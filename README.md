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
docker compose up --build          # everything: web app, API, worker, simulator, PostgreSQL, broker, InfluxDB
uv sync                            # Python tooling for tests and scripts
uv run python scripts/smoke_test.py
```

- Web app: http://localhost:8080
- Demo accounts: `demo-admin@example.com`, `demo-operator@example.com` and `demo-viewer@example.com`, password `fleetpulse-demo`
- API docs: http://localhost:8000/api/docs
- Live events: connect to `ws://localhost:8080/ws` and send `{"type": "subscribe", "channel": "fleet"}`

## Development

Backend (Python):

```sh
uv run pytest         # tests (database tests start PostgreSQL in Docker automatically)
uv run ruff check .   # lint
uv run mypy           # type check
uvx pre-commit install
```

Database changes: edit the models in `apps/backend/src/fleetpulse_backend/db/models.py`, then

```sh
docker compose up -d postgres
uv run alembic -c apps/backend/alembic.ini revision --autogenerate -m "describe the change"
```

API changes: the frontend's TypeScript types are generated from the API, and CI fails if they are out of date.

```sh
uv run python scripts/export_openapi.py   # writes apps/web/openapi.json
cd apps/web && npm run api:generate       # writes src/app/api/schema.d.ts
```

Frontend (Angular), with hot reload against the backend running in Docker:

```sh
cd apps/web
npm install
npm start             # http://localhost:4200, proxies /api and /ws to localhost:8000
npm test
npm run lint
```

## License

[MIT](LICENSE)
