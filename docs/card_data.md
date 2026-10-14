# Card data

The application loads its cards from a **CSV file**. The repository includes `cards/warfighter_cards.csv` (names, stats and
card text; DVG's content — see [NOTICE.md](../NOTICE.md)), and a small *fictional* demo set,
[`examples/cards.sample.csv`](../examples/cards.sample.csv), that the tests and screenshots use. Card **images** are not
included. You can also import your own file in the same format:

```bash
python scripts/import_cards.py                        # cards/warfighter_cards.csv
python scripts/import_cards.py --csv path/to/cards.csv
```

## Columns

The first row is the header; columns are matched **by name**. The first (unnamed) column is just a row index and is ignored.

| Column | Required | Meaning |
|---|---|---|
| `Number` | yes | Unique card number, `PREFIX-NNN` (e.g. `S-001`). The prefix selects the image folder (`static/card_images/<lang>/s/s-001.jpg`) and is the key translations attach to |
| `Name` | yes | Card name |
| `Type` | yes | Raw card type — see the table below |
| `Nation` | no | `US`, `UK`, `German`, `Japan`, … Empty = usable by every nation. Variants such as `US Airborne` are grouped under their base nation |
| `Stats` | no | One `KEY:value` per line, see below |
| `Notes` | no | The card text. Weapon range/mode tables, soldier health/action tables and the objective Hostile table are written in the notes and parsed from them |
| `Module` | yes* | The expansion (box / product) the card belongs to. It is the unit of **My Expansions**: users tick the expansions they own, and the generator and pickers use only those. *If empty, it is inferred from other cards with the same number prefix. `Core Europe` is always listed first, then boxes by their `#NN` number |
| `Vassal Module` | no | Informational |

## Types the importer understands

| `Type` value | Becomes |
|---|---|
| `Player Soldier`, `Non Player Soldier`, `Squad Soldier`, `Team Soldier`, `Squad Vehicle` | Soldier (Player / NPS / Squad / Team / Vehicle) |
| `Weapon Ranged`, `Weapon Thrown`, `Weapon <anything>` | Weapon |
| `Equipment`, `Equipment (<kind>)` | Equipment |
| `Skill`, `Skill (Nation)`, `Skill (Specialist)`, `Skill (Fortification)` | Skill |
| `Service Record (<region>)` | Service Record |
| `Mission <theater>`, `Airborne Mission …` | Mission (the theater comes from the text after `Mission`) |
| `Objective <theater>` | Objective (its kind — Eliminate Hostiles, Keep Clear, Destroy Target … — is derived from the notes) |

Other types (Hostile, Location, Action, Event …) are skipped by the importer; the Hostile and Location cards are only
used by `scripts/build_metric_reference.py`.

## Stats keys

| Key | Meaning | Used by |
|---|---|---|
| `RC` | RP cost | all purchasable cards |
| `M`, `C`, `H`, `L`, `HtH` | Movement, Cover, Health, Loadout, hand-to-hand modifier (`+1`) | soldiers (`L` is also the Loadout weight of gear) |
| `A` | Actions | NPS / Squad soldiers |
| `R`, `T`, `OB`, `LM` | RP budget, turns, objective location (`#04`), Loadout modifier (`-1`) | missions |
| `EN`, `ACHtH`, `REIN` | Entrance cost, HtH action cost, reinforcement range | missions / objectives |

Printed gear and skills of a soldier are written as lines of the notes that name other cards
(`Sample Rifle.`, `2 Sample Grenades.`); the importer links them to the matching cards (`card_associations`) and removes
the lines from the notes. `XP`/`CX` values are written as `2 XP.` / `1 CX.` in the notes.

## Details and more

- [card_taxonomy.md](card_taxonomy.md) — how types and stats are normalised, with every column of the database.
- [`examples/cards.sample.csv`](../examples/cards.sample.csv) — a working example of every card type.
- Card images: [`static/card_images/README.md`](../static/card_images/README.md).
