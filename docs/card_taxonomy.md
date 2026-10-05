# Warfighter Card Taxonomy

## Mission Cards

### Mission Structure Type (`card_subtype`)

The primary classification of a mission card. Stored in `cards.card_subtype`.

| Type | Detection | Count |
|------|-----------|-------|
| Standard | Default (no keyword match) | 152 |
| Raid | Notes contain "Raid Mission." | 37 |
| Airborne | `raw_type` starts with "Airborne Mission" | 21 |
| Holding Action | Notes contain "Holding Action Mission." | 15 |
| Hold the Line | Notes contain "Hold the Line Mission." | 5 |
| Shore Invasion | `raw_type` starts with "Mission-Shore Invasion" | 4 |
| Escape | Notes contain "Escape Mission." | 0 (reserved) |

**Priority**: Notes-based types (Raid, Holding Action, Hold the Line, Escape) take precedence
over raw_type-based types (Airborne, Shore Invasion). A mission with "Raid Mission." in its
notes and "Airborne Mission" in its raw_type is classified as **Raid** — the Airborne origin
is captured separately in the `theater` field.

### Mission Theater

Derived at runtime from `raw_type` via `theater_from_raw_type()`. Not stored in the DB.

Examples: "Europe", "Russia", "Tombola", "Castle Frankestein"

### Mission Modifier (Fortification Overlay)

A **Fortification sub-mission** is not a mission card property. It is a runtime state that
occurs when a mission card is paired with a Fortification-family objective. The modifier is
displayed in the squad detail view as an additional badge on the Mission box.

Rule: `mission_modifier = "Fortification"` when `objective.objective_family == "Fortification"`.

Overlaying a Fortification objective on a Standard (or Raid) mission creates the equivalent
of a "Standard + Fortification" setup. The base mission rules still apply, with the
Fortification sub-mission rules layered on top.

---

## Objective Cards

### Objective Mechanic / Victory Condition (`card_subtype`)

The primary victory condition of the objective. Stored in `cards.card_subtype`.

| Mechanic | Description | Detection | Count |
|----------|-------------|-----------|-------|
| Eliminate Hostiles | Kill all hostiles that receive Objective Hostile markers when the objective activates | "eliminate" in notes (line scan) | 82 |
| Keep Clear | Maintain the objective location free of hostiles for N Soldier Turns; count resets on hostile entry | "Keep Clear N." or "At any time, have no hostiles" | 40 |
| Destroy Target | The objective card is attackable; accumulate required hits against its printed stats | "destroy", "defuse", "clear the X:" in notes | 28 |
| Kill Specified Hostile | A particular hostile is placed/presented by the objective; must be eliminated | "Eliminate Present:", "capture the X: inflict", "Find: [name]", etc. | 44 |
| Escape | Win by escaping back to the mission card after completing a sub-condition | "Escape Mission." in notes | 21 |
| *(empty)* | Structural scenario component — no standard mechanic (see Objective Family) | "Fallback Position" or "Right Flank" in notes | 22 |

**Structural objectives** (Fallback Position, Right Flank) are scenario setup components for
Holding Action and Hold the Line missions. Their win/loss condition is defined by the mission
rules, not the objective card.

### Objective Family (`objective_family`)

Answers: *"What kind of scenario/system does this objective belong to, and which missions can use it?"*

Stored in `cards.objective_family`. Null/empty means Standard (no special restriction).

| Family | Compatible Missions | Detection | Count |
|--------|---------------------|-----------|-------|
| *(null — Standard)* | Standard, Raid, Escape (subject to card text) | Default | 194 |
| Fallback | Holding Action only | "Fallback Position" in notes | 16 |
| Right Flank | Hold the Line only | "Right Flank" in notes | 6 |
| Fortification | Fortification sub-mission (overlays any base type) | Module name contains "Fortif" | 12 |
| Shore | Shore Invasion only | `raw_type` contains "Shore Invasion" | 4 |
| Airborne | Airborne missions | Theater exclusively used by Airborne missions (Tombola) | 4 |
| Embedded | Specific scenario only | `raw_type` contains "Embedded" | 1 |

---

## Mission–Objective Compatibility Rules

> **NOT YET IMPLEMENTED.** These rules are documented here for future implementation.

The objective family determines which mission types can legally use a given objective.

| Objective Family | Compatible Mission Types |
|-----------------|--------------------------|
| Standard | Standard, Raid, Escape |
| Fallback | Holding Action |
| Right Flank | Hold the Line |
| Fortification | Any (overlaid on top of base type) |
| Shore | Shore Invasion |
| Airborne | Airborne |
| Embedded | Specific paired scenario only |

Additionally, **theater** must match between the mission card and the objective card (e.g.,
a "Mission Europe" card must use an "Objective Europe" card from the same theater).
Airborne missions may use objectives from the same theater pool as regular missions in
shared theaters (e.g., Europe), or from Airborne-exclusive pools (e.g., Tombola, Mediterranean).

---

## Data Model

```
cards
├── card_category       TEXT    — "Mission", "Objective", "Soldier", ...
├── card_subtype        TEXT    — mission type OR objective mechanic (see above)
├── objective_family    TEXT    — objective family (Objective cards only, null = Standard)
├── raw_type            TEXT    — original CSV Type field (source for theater derivation)
```

`theater` is derived at runtime via `theater_from_raw_type(raw_type)` and is not stored
in the DB.

---

## Classification Functions (`app/utils.py`)

| Function | Input | Returns |
|----------|-------|---------|
| `classify_mission_type(notes, raw_type)` | notes text, raw_type string | Mission structure type string |
| `classify_objective_type(notes)` | notes text | Objective mechanic string (or `""` for structural) |
| `classify_objective_family(notes, raw_type, module)` | notes, raw_type, module | Family string (or `""` for Standard) |
| `theater_from_raw_type(raw_type)` | raw_type string | Theater/campaign label string |
