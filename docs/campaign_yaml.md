# Campaign file format (YAML) — `warfighter-campaign/1`

A campaign can be written as a YAML file and loaded in two ways:

- **Web:** Campaigns → Builder → **Import…**. Paste the file or open it. The editor is filled with the
  campaign; nothing is saved until you click *Save draft* or *Publish*.
- **Command line:** `python scripts/import_campaign_yaml.py FILE.yaml [--owner NAME] [--draft]`. The owner
  is `--owner`, otherwise the file's `author:` (created without a password if missing). A campaign with the
  same name and owner is replaced. Published by default.

Example: `campaigns/normandia_pablosolano.yaml`.

## Top level

| Key | Type | Notes |
|---|---|---|
| `format` | text | `warfighter-campaign/1` (optional; other values give a warning) |
| `author` | text | Username of the owner (CLI only; the web import uses the logged-in user) |
| `language` | text | `en`, `es`… informational |
| `name` | text | Required to publish (≥ 3 chars) |
| `summary` | text | One or two lines; required to publish |
| `intro` | text | Stage-setting text read before the campaign; required to publish |
| `nation` | text | Nation code as used by the app: `US`, `UK`, `German`, `Russian`… |
| `theater`, `enemy`, `period` | text | Free text |
| `flow` | `linear` \| `branching` \| `free` | Default `linear` |
| `force` | mapping | `squad_size` (1–30), `restrictions`, `replacements` (text) |
| `persistence` | mapping | `xp`, `wounds`, `skills`, `soldiers`, `casualties`, `gear` — true/false. Missing keys default to true, except `gear` (false) |
| `rules` | list | `- title: …` / `body: …` (a plain string is a body without title) |
| `scoring` | text | How the campaign is scored |
| `outcomes` | list | `- label:`, `condition:`, `epilogue:` — at least one with label and epilogue to publish |
| `missions` | list | See below; at least 2 complete missions to publish |

## Missions

| Key | Type | Notes |
|---|---|---|
| `id` | text | Reference for `next` links (default `m1`, `m2`…). `code` also works as a reference |
| `code` | text | Short label shown in lists: `"1"`, `"2a"` (quote numbers) |
| `title` | text | Required to publish |
| `mission` | card | Mission card — required to publish |
| `objective` | card | Objective card — required to publish |
| `situation` | card | Optional Situation card |
| `entry` | bool | Branching flow: a starting mission (the first one is used if none is marked) |
| `rp`, `time`, `loadout` | whole number | Overrides of the mission card's Resource Points (1–300), Time (1–50), Loadout modifier (−10…10) |
| `briefing` | text | Read before the mission — required to publish |
| `debrief` | text | Read after the mission |
| `requirements` | text | Free-order flow: what unlocks the mission |
| `setup`, `victory`, `rewards` | text | Special setup, victory conditions, rewards |
| `next` | list | Branching flow only: `- to: <id or code>`, `when: success \| failure \| always \| choice` (default success), `label: …`. A bare value is `to:` |

**Cards** are given by card number (`W-018`, preferred) or by exact card name in English (or a translated
name once translations are loaded). A name matching several printings uses the earliest module and warns.

**Text** can use YAML block scalars: `|-` keeps line breaks (lists, tables), `>-` folds lines into one
paragraph. Card mentions `[[Card name]]` work as in the editor.

Do not use `on:` as a key: YAML reads it as *true*. Links use `when:`.

## Warnings vs errors

Only an unreadable file (invalid YAML, not a mapping) is rejected. Everything else is imported as far as
possible with warnings — unknown keys, cards not found, bad numbers, links to missing missions — so the
author can fix the rest in the editor.
