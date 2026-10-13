#!/usr/bin/env python3
"""
Parse soldier card notes to discover pre-printed gear/skill associations.

Reads all Soldier cards from the database, extracts card name references from
their notes field, and writes the results to the card_associations table.

Run after import_cards.py:
    python3 scripts/parse_associations.py

Algorithm (two-pass):
  Pass 1 — Exact name match (case-insensitive):
      "Marksman." -> look up "marksman" in gear lookup
  Pass 2 — Suffix match for nation-prefixed names:
      "Keep Calm." -> find any card whose name ends with "-Keep Calm"
      If multiple matches, prefer the one matching the soldier's nation.

Many gear names have several printings (e.g. "M1 Carbine" in Core Europe, Core Pacific, US #2,
South Korea #2 …). best_printing() takes the first match in: the soldier's own module → Core Europe →
expansions with the soldier's nation → any other expansion (module order, then card number).

Repair rows linked to the wrong printing (no notes needed — they were stripped on first run):
    python3 scripts/parse_associations.py --remap
"""

import os
import re
import sys

# Allow running from project root or scripts/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app import create_app, db
from app.models import Card, CardAssociation

# Card categories that can appear as pre-printed associations on soldier cards
GEAR_CATEGORIES = {
    'Skill', 'Weapon', 'Equipment', 'Service Record', 'Action',
}

# Stat field labels that appear in notes as "N Label" — never card names
STAT_LABELS = {
    'health', 'loadout', 'movement', 'cover', 'hth', 'actions',
    'cx', 'noise', 'xp', 'range', 'entrance', 'resources', 'time',
}


def build_gear_lookup():
    """Return {lowercase_name: [Card, …]} for all gear-category cards (every printing of a name)."""
    lookup = {}
    for c in Card.query.filter(Card.card_type.in_(GEAR_CATEGORIES)).order_by(Card.number).all():
        lookup.setdefault(c.name.lower(), []).append(c)
    return lookup


CORE_MODULE = 'Core Europe'
_MODULE_NO = re.compile(r'^#\s*(\d+)')


def _module_order(module):
    """Expansions in catalogue order: '#06 - US #2' → 6; unnumbered sets (KS, Multi-Era …) last."""
    m = _MODULE_NO.match(module or '')
    return (int(m.group(1)) if m else 10_000, module or '')


def best_printing(soldier, candidates):
    """The printing of an included gear card for `soldier`, first match in this order:
    1. the soldier's own module, 2. Core Europe, 3. expansions with the soldier's nation,
    4. any other expansion. Within a step: module order, then card number."""
    def rank(c):
        if c.module == soldier.module:
            step = 0
        elif c.module == CORE_MODULE:
            step = 1
        elif soldier.nation and c.nation == soldier.nation:
            step = 2
        else:
            step = 3
        return (step, _module_order(c.module), c.number)
    return min(candidates, key=rank)


def is_stat_line(candidate: str) -> bool:
    """Return True if the candidate text looks like a stat value, not a card name."""
    low = candidate.lower()
    # Leading digit + stat label, e.g. "7 Health", "4 CX"
    parts = low.split(None, 1)
    if len(parts) == 2:
        word = parts[1].rstrip('.')
        if word in STAT_LABELS:
            return True
    # Just a stat label alone
    if low.rstrip('.') in STAT_LABELS:
        return True
    return False


def extract_refs(soldier, lookup: dict) -> tuple:
    """
    Return (refs, matched_lines) for card references found in the soldier's notes.

    Parameters
    ----------
    soldier : Soldier Card (its notes, nation and module are used)
    lookup  : {lowercase_name: [Card, …]} from build_gear_lookup()

    Returns
    -------
    refs          : list of (Card, int) — unique, ordered as encountered
    matched_lines : set of original stripped line strings that resolved to a card
    """
    notes = soldier.notes
    if not notes:
        return [], set()

    refs = []
    seen_ids = set()
    matched_lines = set()
    soldier_nation_low = (soldier.nation or '').lower()

    lines = [l.strip() for l in re.split(r'\n', notes) if l.strip()]

    for original_line in lines:
        line = original_line.rstrip('.')

        # Extract leading quantity
        quantity = 1
        m = re.match(r'^(\d+)\s+(.+)$', line)
        if m:
            quantity = int(m.group(1))
            candidate = m.group(2)
        else:
            candidate = line

        if not candidate or is_stat_line(line):
            continue

        # Skip purely numeric candidates — these come from stat table rows like "3               2"
        # and would incorrectly match cards whose names end with "-2", "-4", etc.
        if re.match(r'^\d+$', candidate):
            continue

        candidate_low = candidate.lower()

        def _resolve(cand_low: str) -> 'Card | None':
            """Try exact then suffix match for a candidate string. Returns card or None."""
            # Pass 1: exact match
            if cand_low in lookup:
                return best_printing(soldier, lookup[cand_low])
            # Pass 2: suffix match — handles nation-prefixed names like "UK-Keep Calm"
            suffix = f'-{cand_low}'
            matches = [(name, cs) for name, cs in lookup.items() if name.endswith(suffix)]
            if not matches:
                return None
            names = {name for name, _ in matches}
            if len(names) > 1:
                # Multiple nation variants — prefer the one matching the soldier's nation
                names = {name for name in names if name.startswith(soldier_nation_low + '-')}
                if len(names) != 1:
                    return None
            return best_printing(soldier, lookup[names.pop()])

        card = _resolve(candidate_low)

        # Plural fallback: "Mk2 Grenades" → try "Mk2 Grenade"
        if card is None and candidate_low.endswith('s'):
            card = _resolve(candidate_low[:-1])

        if card is None:
            continue

        matched_lines.add(original_line)
        if card.id not in seen_ids:
            refs.append((card, quantity))
            seen_ids.add(card.id)

    return refs, matched_lines


def remap_existing():
    """Point every existing association at the printing best_printing() picks for its soldier."""
    lookup = build_gear_lookup()
    changed = merged = orphans = 0
    for a in CardAssociation.query.all():
        if not a.parent_card or not a.child_card:  # card deleted since; left as is
            orphans += 1
            continue
        candidates = lookup.get(a.child_card.name.lower())
        if not candidates:
            continue
        best = best_printing(a.parent_card, candidates)
        if best.id == a.child_card_id:
            continue
        twin = CardAssociation.query.filter_by(parent_card_id=a.parent_card_id, child_card_id=best.id).first()
        if twin:  # the soldier already lists the right printing
            twin.quantity = max(twin.quantity or 1, a.quantity or 1)
            db.session.delete(a)
            merged += 1
        else:
            a.child_card_id = best.id
            changed += 1
    db.session.commit()
    print(f'Remapped {changed} associations to the right printing; removed {merged} duplicates; '
          f'skipped {orphans} pointing at deleted cards.')


def main():
    app = create_app()
    with app.app_context():
        if '--remap' in sys.argv:
            remap_existing()
            return
        print('Building gear lookup...')
        lookup = build_gear_lookup()
        print(f'  {len(lookup)} gear/skill card names indexed.')

        soldiers = Card.query.filter_by(card_type='Soldier').all()
        print(f'  {len(soldiers)} soldier cards to process.')

        inserted = 0
        updated = 0
        notes_cleaned = 0
        soldier_with_assoc = 0

        for soldier in soldiers:
            refs, matched_lines = extract_refs(soldier, lookup)
            if not refs:
                continue
            soldier_with_assoc += 1
            for child_card, quantity in refs:
                existing = CardAssociation.query.filter_by(
                    parent_card_id=soldier.id,
                    child_card_id=child_card.id,
                ).first()
                if existing:
                    if existing.quantity != quantity:
                        existing.quantity = quantity
                        updated += 1
                else:
                    db.session.add(CardAssociation(
                        parent_card_id=soldier.id,
                        child_card_id=child_card.id,
                        quantity=quantity,
                    ))
                    inserted += 1

            # Strip matched association lines from notes
            if matched_lines and soldier.notes:
                cleaned_lines = [
                    l for l in soldier.notes.split('\n')
                    if l.strip() not in matched_lines
                ]
                cleaned = '\n'.join(cleaned_lines).strip() or None
                if cleaned != soldier.notes:
                    soldier.notes = cleaned
                    notes_cleaned += 1

        db.session.commit()

        total = CardAssociation.query.count()
        print(f'\nDone.')
        print(f'  Soldiers with associations : {soldier_with_assoc}/{len(soldiers)}')
        print(f'  New rows inserted          : {inserted}')
        print(f'  Existing rows updated      : {updated}')
        print(f'  Notes cleaned              : {notes_cleaned}')
        print(f'  Total rows in DB           : {total}')


if __name__ == '__main__':
    main()
