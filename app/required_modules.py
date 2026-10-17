"""Modules needed to build a squad.

The same card is often printed in several modules (Bayonet appears in 35), and a
squad stores whichever printing the builder picked. So the modules of the stored
cards are NOT what the player needs: a squad holding the Castle Itter "98k Rifle"
is buildable with German #1. Here every stored card is widened to its group of
equivalent printings, and we look for the smallest set of modules that contains
at least one printing of each group.

Printings are equivalent when name, type, nation and all printed stats match
(None == 0). Notes wording/errata and subtype tags are ignored: they differ
between reprints without changing the card. Soldiers are never merged in
practice — same-name soldiers always differ in stats.

Quantities (×2) are ignored: a module counts if it has the card at all — the
builder doesn't limit quantities by physical copies either. See spec/08_squad_tools.md §5.
"""
import re
from collections import defaultdict
from functools import lru_cache

from app import db
from app.models import HIDDEN_SUBTYPE, Card, Squad, SquadGear, SquadObjective, SquadSoldier

_STAT_COLS = ('resource_cost', 'movement', 'cover', 'health', 'loadout', 'hth', 'actions',
              'entrance_cost', 'resources', 'time', 'objective_position', 'loadout_modifier',
              'xp_value', 'noise', 'action_cost_hth', 'support_cost', 'covert_cost', 'gain', 'loss',
              'combat_xp', 'soldier_xp', 'weapon_range_table', 'weapon_mode_table')

_MAX_SOLUTIONS = 2000  # tie-break candidates collected at the minimal size


def module_rank(module):
    """Core Europe first, then box number (#13 …), then the rest (KS, Multi-Era) by name."""
    if module == 'Core Europe':
        return (0, 0, '')
    m = re.match(r'#(\d+)', module or '')
    return (1, int(m.group(1)), '') if m else (2, 0, module or '')


@lru_cache(maxsize=1)
def _index():
    """card_id -> group key, and group key -> set of modules printing it."""
    t = Card.__table__
    cols = [t.c.id, t.c.name, t.c.card_type, t.c.nation, t.c.module] + [t.c[c] for c in _STAT_COLS]
    group_of, supply = {}, defaultdict(set)
    hidden = db.or_(t.c.card_subtype.is_(None), t.c.card_subtype != HIDDEN_SUBTYPE)     # helper cards need no module
    for row in db.session.execute(db.select(*cols).where(hidden)):
        cid, name, ctype, nation, module, *stats = row
        key = (name.strip().lower(), ctype, nation or '', tuple(0 if v is None else v for v in stats))
        group_of[cid] = key
        supply[key].add(module)
    return group_of, dict(supply)


def clear_cache():
    _index.cache_clear()


def _groups(card_ids):
    group_of, _ = _index()
    return {group_of[cid] for cid in card_ids if cid in group_of}


def _min_cover(needs):
    """Smallest module set covering `needs`; ties → best module_rank tuple."""
    _, supply = _index()
    if not needs:
        return []

    def unmet(chosen):
        return [g for g in needs if not supply[g] & chosen]

    def search(chosen, depth, out):
        left = unmet(chosen)
        if not left:
            out.append(frozenset(chosen))
            return
        if depth == 0 or len(out) >= _MAX_SOLUTIONS:
            return
        # Branch on the most constrained group: any cover must use one of its modules
        g = min(left, key=lambda g: len([m for m in supply[g] if m not in chosen]))
        for m in sorted((m for m in supply[g] if m not in chosen), key=module_rank):
            search(chosen | {m}, depth - 1, out)

    all_modules = {m for g in needs for m in supply[g]}
    for size in range(1, len(all_modules) + 1):
        found = []
        search(frozenset(), size, found)
        if found:
            best = min(found, key=lambda s: (len(s), sorted(module_rank(m) for m in s)))
            return sorted(best, key=module_rank)
    return sorted(all_modules, key=module_rank)


def required_modules(squad):
    """Modules to build the squad's soldiers + gear (missions/objectives excluded by design)."""
    items = []
    for ss in squad.soldiers:
        items.append(ss.card_id)
        items.extend(g.card_id for g in ss.gear)
    return _min_cover(_groups(items))


def _squad_cards(squad_ids):
    """squad_id -> [card_id] for everything needed to play: soldiers, gear,
    mission, objectives, situation."""
    out = defaultdict(list)
    if not squad_ids:
        return out
    for sid, cid in db.session.query(SquadSoldier.squad_id, SquadSoldier.card_id).filter(
            SquadSoldier.squad_id.in_(squad_ids)):
        out[sid].append(cid)
    for sid, cid in (db.session.query(SquadSoldier.squad_id, SquadGear.card_id)
                          .join(SquadGear, SquadGear.squad_soldier_id == SquadSoldier.id)
                          .filter(SquadSoldier.squad_id.in_(squad_ids))):
        out[sid].append(cid)
    for sid, cid in db.session.query(SquadObjective.squad_id, SquadObjective.card_id).filter(
            SquadObjective.squad_id.in_(squad_ids)):
        out[sid].append(cid)
    for sid, mid, sit in db.session.query(Squad.id, Squad.mission_card_id, Squad.situation_card_id).filter(
            Squad.id.in_(squad_ids)):
        out[sid].append(mid)
        if sit:
            out[sid].append(sit)
    return out


def buildable_ids(squad_ids, excluded_modules):
    """Subset of squad_ids playable without `excluded_modules` (any equivalent printing counts)."""
    _, supply = _index()
    excluded = set(excluded_modules)
    ok = []
    for sid, items in _squad_cards(list(squad_ids)).items():
        if all(supply[g] - excluded for g in _groups(items)):
            ok.append(sid)
    return ok
