# Running with Docker (any host)

The `Dockerfile` builds a self-contained image: Python 3.12, gunicorn (one process, four threads) on port **8080**, and the
SQLite database on the `/data` volume. Nothing in it is specific to one hosting provider.

```bash
docker build -t wf-squad-builder .
docker run --rm -p 8080:8080 -v wf-data:/data \
  -e DEBUG=true -e APP_BASE_URL=http://localhost:8080 -e COOKIE_SECURE=false \
  wf-squad-builder                                  # http://localhost:8080
```

On the first start the entrypoint imports `cards/warfighter_cards.csv` into `/data/warfighter.db`; it imports again only
when the CSV changes. Set `SKIP_CARD_IMPORT=1` to disable that, or `CARDS_CSV=…` to use another file.

## Production

| Setting | Value |
|---|---|
| `DEBUG` | `false` |
| `SECRET_KEY` | random, 32+ characters |
| `APP_BASE_URL` | your public `https://` origin |
| `MAIL_BACKEND` | `resend` or `smtp` (+ their variables, see [INSTALL.md](../INSTALL.md#8-configuration-reference)) |
| `PROXY_FIX_HOPS` | `1` behind one reverse proxy / platform router |

Rules that come from SQLite and the in-memory rate limiter: **run exactly one container**, and keep `/data` on a
persistent disk. Put an HTTPS reverse proxy in front (Caddy, nginx, or your platform's router). `GET /healthz` is the
health-check URL. Back up with `sqlite3 /data/warfighter.db ".backup /data/backup.db"`.

Create the admin account: `docker exec -it <container> python scripts/create_admin.py --email you@example.com`.

Not suitable: platforms without a persistent disk (Cloud Run, Heroku, Vercel).
Without Docker, see [INSTALL.md](../INSTALL.md#9-deploying-publicly).
