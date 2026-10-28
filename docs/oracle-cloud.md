# Hosting on Oracle Cloud (Always Free)

How the public demo runs on one free Ampere VM. Everything here costs nothing as long as
only Always Free resources are used; a budget alert emails as soon as anything would.

## Cost safety rules

1. Stay on the **Free Tier**. Do not upgrade the account to Pay As You Go.
2. Create resources only with the Terraform in `infra/terraform`. It uses the Always Free
   shape (`VM.Standard.A1.Flex`, 2 OCPUs / 12 GB) and a 50 GB boot volume.
3. The Terraform also creates a budget with an alert on any forecast spending.
4. Terraform state (`terraform.tfstate`) stays on your machine and out of Git: it can
   contain sensitive values.

## 1. Account and API key (once)

1. Sign up at oracle.com/cloud/free. Pick your **home region** carefully (for example
   Stockholm, `eu-stockholm-1`): Always Free compute only exists there. A card is needed
   for identity verification only.
2. In the console, open **My profile > API keys > Add API key**, download the private key
   to `~/.oci/oci_api_key.pem`, and note the values shown (tenancy, user, fingerprint).

## 2. Create the server

```sh
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # fill in your values
terraform init
terraform plan     # review: one VM, a network, a budget; nothing else
terraform apply
```

The output shows the public IP. If the region reports *Out of host capacity* for Ampere,
try another `availability_domain_index`, or try again later.

On first boot, cloud-init installs Docker, opens ports 80/443 in the VM's own firewall
(Oracle's Ubuntu images block them by default, in addition to the cloud security list),
and clones the repository to `/opt/fleetpulse`.

## 3. Domain

Point a domain at the public IP. A free option is a DuckDNS subdomain
(`fleetpulse-demo.duckdns.org`): set its IP to the Terraform output.

## 4. Start FleetPulse on the server

```sh
ssh ubuntu@<public ip>
cd /opt/fleetpulse
cp .env.example .env    # fill in; secrets from: openssl rand -base64 32
docker compose -f compose.yaml -f compose.prod.yaml up -d --build
```

Caddy obtains the HTTPS certificate on the first request to the domain.

## 5. Automatic deployments (optional)

`.github/workflows/deploy.yml` deploys every commit that passes CI on `main`. To turn
it on, in the GitHub repository settings:

| Kind | Name | Value |
|---|---|---|
| Variable | `DEPLOY_ENABLED` | `true` |
| Variable | `DEPLOY_HOST` | the public IP |
| Variable | `DEPLOY_DOMAIN` | the domain, e.g. `fleetpulse-demo.duckdns.org` |
| Secret | `DEPLOY_SSH_KEY` | a private key whose public key is in the server's `~/.ssh/authorized_keys` (a key just for deployments) |
| Secret | `DEPLOY_KNOWN_HOSTS` | output of `ssh-keyscan <public ip>`, checked against the server |

The workflow checks out the exact commit CI tested, rebuilds, and waits until
`/api/v1/health/ready` answers over HTTPS.

## If Oracle reclaims the VM

Oracle may reclaim Always Free instances it considers idle. Everything is reproducible:
run `terraform apply` again, repeat steps 3 and 4, and the demo is back.
