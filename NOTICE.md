# Notice — fan project, intellectual property and credits

## This is a fan-made project

**Warfighter Squad Builder is an unofficial, fan-made web application. It is not affiliated with, authorised,
sponsored or endorsed by DVG (Dan Verssen Games).**

*Warfighter* (including *Warfighter WWII* and all related games, expansions, card names and texts, rules, artwork,
logos and trademarks) is the property of **DVG**. All rights regarding the Warfighter games and their assets belong
to DVG. If you enjoy the game, please support the publisher: <https://www.dvg.com>.

## What the licenses cover

| Part | Terms |
|---|---|
| Source code and documentation in this repository | [MIT License](LICENSE) |
| Warfighter cards, card text, rules text, artwork, logos, names | **Not covered** — owned by DVG. Not included in this repository |
| `app/metric_reference.json` | Aggregate statistics only (distributions of Hostile Cover/Penetration, Location entrance costs, and metric values of reference squads) — numbers, no card text. Rebuild it from your own data with `scripts/build_metric_reference.py` |
| The demo card set (`examples/cards.sample.csv`) | Entirely fictional placeholder cards written for this project (MIT) |

The repository deliberately contains **no** Warfighter card database, scans, images, or rulebook text. To use the app
with your own copy of the game you supply your own card data and images; see [docs/card_data.md](docs/card_data.md).
Please do not open issues or pull requests that attach DVG's card text, scans or artwork, and do not publicly
redistribute them from a deployment you run.

If you host a public instance, keep the footer notice, and consider a non-commercial, no-ads setup in the spirit of
fan content. If DVG (or any rights holder) asks for changes or removal, they will be made promptly — please open an
issue or contact the maintainer.

## Community content included with credit

Some files are fan-written scenario content that the app can import. They are included with credit to their authors:

- `campaigns/normandia_pablosolano.yaml` — campaign by **Pablo Solano**.
- `campaigns/carentan44_*.yaml` — *Carentan 44* regiment campaigns by **Mariano Rico Castillo** (Spanish files are translations).
- `scripts/import_bgg_community_squads.py` — squad lists from the BoardGameGeek community compilation
  *"Warfighter WW2 Scenarios and Campaigns"* (published by **PyroDoctor**); the compilation itself is not included.

Authors: if you would like your work credited differently, relicensed, or removed, open an issue and it will be done.

## Third-party software and fonts

- Python dependencies (Flask, SQLAlchemy, Flask-Login, Flask-Limiter, PyYAML, python-dotenv, Werkzeug) keep their own
  licenses; see [requirements.txt](requirements.txt).
- The UI loads the *Roboto Condensed* and *Special Elite* fonts from Google Fonts (open-licensed fonts).
- `scripts/translate.py` (optional, not used by the app) can call the Anthropic API to draft card-text translations.
