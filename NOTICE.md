# Notice — fan project, intellectual property and credits

## This is a fan-made project

**Warfighter WWII - Squad Builder is an unofficial, fan-made web application. It is not affiliated with, authorised,
sponsored or endorsed by DVG (Dan Verssen Games).**

*Warfighter* (including *Warfighter WWII* and all related games, expansions, card names and texts, rules, artwork,
logos and trademarks) is the property of **DVG**. All rights regarding the Warfighter games and their assets belong
to DVG. If you enjoy the game, please support the publisher: <https://www.dvg.com>.

## What the licenses cover

| Part | Terms |
|---|---|
| Source code and documentation in this repository | [MIT License](LICENSE) |
| `cards/warfighter_cards.csv` — card names, stats, card text, module names | **Not covered by the MIT License.** Owned by DVG. A fan transcription included only so that players can use the app; see below |
| Warfighter card images, scans, artwork, logos, rulebook text | **Not included** and not covered — owned by DVG |
| `app/metric_reference.json` | Aggregate statistics only (distributions of Hostile Cover/Penetration, Location entrance costs, metric values of reference squads) — numbers, no card text |
| The demo card set (`examples/cards.sample.csv`) | Entirely fictional placeholder cards written for this project (MIT) |

The card CSV is included for the convenience of people who own the game. It is DVG's intellectual property and remains
so; no license to it is granted by this repository. **If DVG (or any rights holder) asks for it to be changed or removed,
it will be removed promptly** — please open an issue or contact the maintainer. Card images are never part of this
repository: to see them in the app you add your own scans locally (they are git-ignored). Please do not commit or publicly
redistribute scans or artwork, and if you host a public instance consider a non-commercial, no-ads setup in the spirit of
fan content and keep the footer notice.

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
