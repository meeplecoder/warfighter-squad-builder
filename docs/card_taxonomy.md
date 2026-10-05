# Warfighter Card Taxonomy

## Data Model

All card types (Mission, Objective, Soldier, Hostile, Weapon, Location, …) live in a single
`cards` table, distinguished by `card_type`.

```
cards
├── id                  INTEGER PK
├── number              TEXT UNIQUE          "W-018", "03-051"
├── name                TEXT
├── card_type           TEXT  ← discriminator "Mission", "Objective", "Soldier", …
├── card_subtype        TEXT  ← generic combined field (see per-type meaning below)
├── raw_type            TEXT                 original CSV Type field (theater derivation source)
├── nation              TEXT
├── module              TEXT
├── notes               TEXT
├── objective_family    TEXT                 Objective cards only; null = Standard
│
│   ── mission-specific stats ──
├── resources           INTEGER   RP budget
├── time                INTEGER   turn limit
├── objective_position  INTEGER   location number where objective card is placed
├── loadout_modifier    INTEGER   modifier applied to Player Soldier loadout
├── action_cost_hth     INTEGER
│
│   ── objective-specific stats ──
├── entrance_cost       INTEGER   RP cost to enter objective location
├── action_cost_hth     INTEGER   HtH action cost
├── reinforcements      TEXT      reinforcement schedule
├── hostile_count       TEXT      hostile quantity table
│
│   ── soldier-specific stats ──
├── health / loadout / movement / cover / hth / actions / resource_cost / cx / xp
└── …
```

`theater` is derived at runtime from `raw_type` via `theater_from_raw_type()` — not stored.

---

## Mission Cards  (`card_type = 'Mission'`)

### `card_subtype` = `mission_type`

The mission structure type. One field; the generic `card_subtype` equals `mission_type`.

| mission_type | Count | Detection |
|---|---|---|
| Standard | 152 | default |
| Raid | 37 | "Raid Mission." in notes |
| Airborne | 21 | raw_type starts with "Airborne Mission" |
| Holding Action | 15 | "Holding Action Mission." in notes |
| Hold the Line | 5 | "Hold the Line Mission." in notes |
| Shore Invasion | 4 | raw_type starts with "Mission-Shore Invasion" |
| Escape | 0 | reserved — "Escape Mission." in notes |

**Priority**: notes-based types win over raw_type types. A card with "Raid Mission." in notes
and "Airborne Mission" in raw_type is classified as **Raid**. Its Airborne origin is captured
in `theater`.

### API fields for Mission cards

| Field | Source |
|---|---|
| `card_type` | `'Mission'` |
| `card_subtype` | combined generic value = `mission_type` |
| `mission_type` | same as `card_subtype` (semantic alias) |
| `theater` | derived from `raw_type` at runtime |
| `resources` | RP budget |
| `time` | turn limit |
| `objective_position` | location number for objective placement |
| `loadout_modifier` | PS loadout modifier |

**Fortification overlay**: not a mission card property. When a Fortification-family objective
is paired with a mission, the UI shows a "Fortification" badge on the mission box. This is
a runtime display computed from `objective.objective_family`.

---

## Objective Cards  (`card_type = 'Objective'`)

### `card_subtype` = `"{objective_family} / {objective_mechanic}"` or just one of them

The generic `card_subtype` combines both dimensions. The two parts are also stored/exposed
separately for programmatic use.

### `objective_mechanic` — the victory condition

| mechanic | Count | What it means |
|---|---|---|
| Eliminate Hostiles | 82 | Kill all hostiles bearing Objective Hostile markers |
| Kill Specified Hostile | 44 | Kill or capture a specific named/presented unit |
| Keep Clear | 40 | Keep the location free of hostiles for N Soldier Turns |
| Destroy Target | 28 | Accumulate hits against the objective card's printed stats |
| Escape | 21 | Escape back to the mission card |
| *(empty)* | 22 | Structural objective — win condition defined by the mission rules |

Structural objectives (Fallback, Right Flank) are scenario setup cards for Holding Action and
Hold the Line missions. Their `objective_mechanic` is empty.

### `objective_family` — the scenario/compatibility context

| family | card_subtype form | Count | Compatible missions |
|---|---|---|---|
| *(null — Standard)* | `"Mechanic"` | 194 | Standard, Raid, Escape |
| Fallback | `"Fallback"` | 16 | Holding Action only |
| Right Flank | `"Right Flank"` | 6 | Hold the Line only |
| Fortification | `"Fortification / Mechanic"` | 12 | Fortification sub-mission (overlays any type) |
| Shore | `"Shore / Mechanic"` | 4 | Shore Invasion only |
| Airborne | `"Airborne / Mechanic"` | 4 | Airborne (Tombola theater) |
| Embedded | `"Embedded / Mechanic"` | 1 | Specific paired scenario |

### Complete `card_subtype` values in DB

```
Standard family (mechanic only):
  "Eliminate Hostiles"                       69
  "Kill Specified Hostile"                   38
  "Keep Clear"                               38
  "Destroy Target"                           28
  "Escape"                                   21

Structural (family only, no mechanic):
  "Fallback"                                 16
  "Right Flank"                               6

Special families (Family / Mechanic):
  "Fortification / Kill Specified Hostile"    6
  "Fortification / Eliminate Hostiles"        5
  "Shore / Eliminate Hostiles"                4
  "Airborne / Eliminate Hostiles"             3
  "Fortification / Keep Clear"                1
  "Airborne / Keep Clear"                     1
  "Embedded / Eliminate Hostiles"             1
```

### API fields for Objective cards

| Field | Source |
|---|---|
| `card_type` | `'Objective'` |
| `card_subtype` | combined `"Family / Mechanic"` string |
| `objective_mechanic` | mechanic part extracted from `card_subtype` |
| `objective_family` | family part (from `objective_family` column) |
| `theater` | derived from `raw_type` at runtime |
| `entrance_cost` | RP cost to enter objective location |
| `action_cost_hth` | HtH action cost at objective |

---

## Mission–Objective Compatibility Rules

> **NOT YET IMPLEMENTED.** Documented here for future implementation.

| Objective family | Compatible mission_type |
|---|---|
| Standard | Standard, Raid, Escape |
| Fallback | Holding Action |
| Right Flank | Hold the Line |
| Fortification | Any (Fortification sub-mission overlaid on top) |
| Shore | Shore Invasion |
| Airborne | Airborne |
| Embedded | Specific paired scenario only |

Additionally, **theater** must match between the mission and objective card (e.g., "Mission Europe"
uses "Objective Europe"). Compatibility is enforced per `raw_type` theater, not `card_subtype`.

---

## Classification Functions (`app/utils.py`)

| Function | Inputs | Returns |
|---|---|---|
| `classify_mission_type(notes, raw_type)` | notes, raw_type | `mission_type` string |
| `classify_objective_type(notes)` | notes | `objective_mechanic` string (or `""` for structural) |
| `classify_objective_family(notes, raw_type, module)` | notes, raw_type, module | `objective_family` string (or `""` for Standard) |
| `build_objective_subtype(mechanic, family)` | mechanic, family | combined `card_subtype` string |
| `theater_from_raw_type(raw_type)` | raw_type | theater/campaign label string |
