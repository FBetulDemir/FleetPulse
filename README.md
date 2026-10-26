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

## License

[MIT](LICENSE)
