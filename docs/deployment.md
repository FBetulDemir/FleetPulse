# Deployment

FleetPulse runs in production as the same Docker Compose stack as locally, plus
`compose.prod.yaml` for production settings. One small VM is enough.

## What changes in production

| | Local (`compose.yaml`) | Production (+ `compose.prod.yaml`) |
|---|---|---|
| Reachable from outside | Ports on 127.0.0.1 only | Only Caddy, on 80 and 443 |
| HTTPS | No | Automatic Let's Encrypt certificate for `FLEETPULSE_DOMAIN` |
| Cookies | Not `Secure` (plain HTTP) | `Secure`, `httpOnly`, `SameSite=Strict` |
| MQTT | Anonymous | One login per service, topic rights in `infra/mosquitto/acl` |
| Secrets | Development defaults | From `.env`; the stack refuses to start without them |
| JWT secret | Development value | Required: 32+ characters, or the API refuses to start |
| InfluxDB | No authentication | No authentication, but unreachable outside the Docker network |
| Security headers | Yes | Yes, plus HSTS |

## Security headers

Set by Caddy for every response (`infra/caddy/security-headers.caddy`):

- **Content-Security-Policy**: scripts only from this site, no inline scripts. Angular's
  critical-CSS inlining is turned off because it needs an inline script. The API docs at
  `/api/docs` get a separate, looser policy so Swagger UI can load.
- `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`,
  `Cross-Origin-Opener-Policy`, and `Strict-Transport-Security` (production only).

The same headers apply locally, so a resource the policy blocks shows up in development
and in CI, not first in production.

## First deployment

1. A VM with Docker and the Compose plugin, ports 80 and 443 open.
2. A domain pointing at the VM's public IP (for example a free DuckDNS subdomain).
3. On the VM:

   ```sh
   git clone https://github.com/FBetulDemir/FleetPulse.git && cd FleetPulse
   cp .env.example .env
   # fill in .env; generate each secret with: openssl rand -base64 32
   docker compose -f compose.yaml -f compose.prod.yaml up -d --build
   ```

4. Open `https://<your domain>`. The first request can take a few seconds while Caddy
   obtains the certificate.

## Updating

```sh
git pull
docker compose -f compose.yaml -f compose.prod.yaml up -d --build
```

Database migrations run automatically (the `migrate` service) before the API starts.

## Trying the production setup locally

Use `localhost` as the domain: Caddy then issues a certificate from its own local
authority (the browser warns about it). Use a separate project name so the local
development database is not touched:

```sh
docker compose -p fleetpulse-prodtest --env-file prod-test.env \
  -f compose.yaml -f compose.prod.yaml up -d --build
```
