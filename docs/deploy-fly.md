# Deploying to Fly.io

Fly-specific files: `fly.toml` and `.github/workflows/deploy.yml` (delete them if you host elsewhere — see
[deploy-docker.md](deploy-docker.md)). Expect about $3–4 / month (shared-cpu-1x, 512 MB + a 1 GB volume).

## One-time setup

```bash
fly apps create warfighterww2          # or change `app` in fly.toml
fly volumes create wf_data --region ams --size 1  # same region as primary_region
fly secrets set SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" \
                RESEND_API_KEY=re_...             # or use MAIL_BACKEND=smtp and MAIL_* secrets
fly deploy --ha=false
fly ips list                                      # if empty: fly ips allocate-v4 --shared && fly ips allocate-v6
fly ssh console -C "python scripts/create_admin.py --email you@example.com"
```

Always keep **one machine** (`fly scale count 1`): the database is a SQLite file on that machine's volume.
Edit `APP_BASE_URL` / `MAIL_FROM` in `fly.toml` when you add a custom domain (`fly certs add your.domain`). Resend
only sends to arbitrary recipients from a domain you verified there (a `*.fly.dev` name cannot be verified), so use
e.g. `no-reply@mail.your.domain` after the domain shows as Verified in Resend.

## Deploying from GitHub

Either use the dashboard's **Launch an App from GitHub**, or the included workflow: create a token with
`fly tokens create deploy -x 999999h`, store it as the repository secret `FLY_API_TOKEN`, and every push to `main`
runs the tests and deploys. The dashboard generates its own Dockerfile if the repository has none; this repository has
one, so check that the build uses it.

## Backups

Fly snapshots the volume daily (a few days kept) — not a complete backup. Also copy the database out now and then:
`fly ssh sftp get /data/warfighter.db`.

## Without the fly CLI (GitHub Actions only)

`.github/workflows/fly-setup.yml` runs the one-time tasks from the repository's **Actions** tab:

1. Create a Fly access token in the Fly dashboard (account/organization **Tokens** page; an organization token is
   needed to create volumes and open SSH) and save it as the repository secret `FLY_API_TOKEN`
   (Settings → Secrets and variables → Actions). Optional secrets: `RESEND_API_KEY`, `SECRET_KEY`
   (generated automatically if missing), `ADMIN_EMAIL` and `ADMIN_PASSWORD` (for `create-admin`; kept as secrets because logs of a
   public repository are public). Delete `fly-setup.yml` and revoke the organization token when the setup is done.
2. Actions → **Fly.io setup** → Run workflow → `setup`: creates the volume, secrets, IPs, and keeps one machine.
3. Deploy (push to `main`, or Actions → **Deploy to Fly.io** → Run workflow).
4. Actions → **Fly.io setup** → `create-admin` (uses the `ADMIN_EMAIL` and `ADMIN_PASSWORD` secrets). `status` lists
   machines, volumes, IPs and secret names.
