# Installing and running Warfighter Squad Builder

This guide covers a local development setup, loading card data, and a basic production deployment.

## 1. Requirements

- Python **3.10 or newer** (developed and tested on 3.12)
- `git`
- On Debian/Ubuntu you may need `sudo apt install python3-venv python3-pip`
- SQLite (bundled with Python) — no database server is needed

## 2. Get the code and install dependencies

```bash
git clone https://github.com/meeplecoder/warfighter-squad-builder.git
cd warfighter-squad-builder
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Configure

```bash
cp .env.example .env
```

The defaults in `.env.example` are fine for local development (`DEBUG=true`, emails printed to the terminal). Every
variable is described in the table in [section 8](#8-configuration-reference).

## 4. Load card data

The database starts empty. You need a cards CSV.

**Try it with the demo set** (fictional cards, included):

```bash
python scripts/import_cards.py --csv examples/cards.sample.csv
```

**Use your own Warfighter data.** The repository does not ship DVG's cards (see [NOTICE.md](NOTICE.md)). Create a CSV in
the format described in [docs/card_data.md](docs/card_data.md) and import it the same way:

```bash
python scripts/import_cards.py --csv /path/to/my_cards.csv
```

The import is **idempotent**: run it again after editing the CSV and cards are updated in place. It also records each
soldier's pre-printed gear and skills (`card_associations`), so no extra step is needed.

*Advanced:* `python scripts/build_metric_reference.py` rebuilds the reference statistics behind the squad metrics
(`app/metric_reference.json`, which ships with the app) from your CSV's Hostile and Location cards and from the squads in
your database. It **overwrites that tracked file**, so only run it if you need metrics calibrated to your own data.

### Card images (optional)

Put your own images in `static/card_images/<lang>/<prefix>/<number>.jpg` (all lowercase, e.g. `en/w/w-001.jpg`). See
[static/card_images/README.md](static/card_images/README.md). Images are ignored by git — do not commit or publicly
redistribute them. Re-run the card import after adding images.

## 5. Run

```bash
python run.py
```

Open <http://127.0.0.1:5000>. The development server only listens on localhost; set `HOST=0.0.0.0` in `.env` if you
really need it reachable from other machines (never together with `DEBUG=true` on an untrusted network).

### Create an account

Use **Register** in the app. With `MAIL_BACKEND=console` (the default) the verification email is **printed in the
terminal** where the server runs — open the link it shows to activate the account.

### Make yourself an admin (optional)

The card-translation editor is admin-only:

```bash
python scripts/make_admin.py YOUR_USERNAME
```

### Choose the modules you own

The generator and pickers only use cards from the modules you own. Open **Profile** and tick them. Until you save a
selection, every module counts as owned.

## 6. Optional data

| What | How |
|---|---|
| Spanish (or other) card text | `scripts/import_translations.py import FILE.json\|FILE.csv`; export with `export --lang es` |
| Machine-drafted translations | `pip install anthropic`, set `ANTHROPIC_API_KEY`, then `scripts/translate.py --lang es` (drafts are marked for review) |
| Example campaigns | `python scripts/import_campaign_yaml.py campaigns/normandia_pablosolano.yaml` (see [docs/campaign_yaml.md](docs/campaign_yaml.md)) |
| Check UI translations | `python scripts/i18n_check.py` |

## 7. Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests create a temporary database from the demo cards, so they never touch your real data.

## 8. Configuration reference

| Variable | Default | Meaning |
|---|---|---|
| `DEBUG` | `false` | `true` for development. With `false` the app refuses to start with an unsafe configuration |
| `SECRET_KEY` | dev placeholder | **Required in production**: random, 32+ characters (`python -c "import secrets; print(secrets.token_urlsafe(48))"`) |
| `DATABASE_URL` | `sqlite:///data/warfighter.db` | SQLAlchemy URL; the SQLite file lives in `data/` (git-ignored) |
| `CARDS_CSV` | `../cards2.csv` | Default CSV for `import_cards.py` (or pass `--csv`) |
| `APP_BASE_URL` | — | Public origin used in emailed links (e.g. `https://squads.example.com`). **Required when `DEBUG=false`** |
| `HOST`, `PORT` | `127.0.0.1`, `5000` | Development server only |
| `LOCAL_REGISTRATION_ENABLED` | `true` | Set `false` to close sign-ups |
| `PASSWORD_MIN_LENGTH` | `15` | Minimum password length |
| `COOKIE_SECURE` | `true` unless `DEBUG` | Send session cookies over HTTPS only |
| `PROXY_FIX_HOPS` | `0` | Number of reverse proxies in front of the app (client IP and https scheme) |
| `MAIL_BACKEND` | `console` | `console` (prints), `smtp`, or `resend` |
| `MAIL_FROM` | `Warfighter Squad Builder <no-reply@localhost>` | Sender address |
| `RESEND_API_KEY` | — | For `MAIL_BACKEND=resend` |
| `MAIL_HOST`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_USE_SSL` | — / `587` | For `MAIL_BACKEND=smtp` |
| `TTS_IMAGE_BASE_URL`, `TTS_CARD_BACK_URL` | — | Public URLs of card images for the Tabletop Simulator export |

## 9. Deploying publicly

The built-in server is for development. A minimal production setup:

1. **Environment** — `DEBUG=false`, a strong `SECRET_KEY`, `APP_BASE_URL=https://your.domain`, a real `MAIL_BACKEND`
   (`smtp` or `resend`, otherwise verification emails are not delivered), `PROXY_FIX_HOPS=1` behind one proxy.
2. **WSGI server** — run a **single process** with threads (rate-limit counters are kept in memory):
   ```bash
   pip install gunicorn
   gunicorn -w 1 --threads 4 -b 127.0.0.1:8000 run:app
   ```
3. **Reverse proxy with HTTPS** — put nginx or Caddy in front; the app serves its own static files.
4. **Backups** — everything lives in the SQLite file: `sqlite3 data/warfighter.db ".backup backup.db"` (safe while running).
5. **Updating** — `git pull`, `pip install -r requirements.txt`, restart. Database tables are created automatically;
   re-run `scripts/import_cards.py` if the card data changed.
6. **Legal** — keep the footer notice and read [NOTICE.md](NOTICE.md) before hosting a public instance that shows
   Warfighter content.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `RuntimeError: APP_BASE_URL must be set` or `SECRET_KEY must be…` | You are running with `DEBUG=false`; set the variables above, or use `DEBUG=true` for local work |
| `ERROR: CSV file not found` | Pass `--csv path/to/file.csv`, or try `--csv examples/cards.sample.csv` |
| The generator says you own no Player Soldier for a nation | Import a CSV that has Player Soldiers for that nation, and check your modules in **Profile** |
| No verification email arrives | In development it is printed in the server terminal (`MAIL_BACKEND=console`) |
| `No module named venv` / `ensurepip` | `sudo apt install python3-venv` (Debian/Ubuntu) |
