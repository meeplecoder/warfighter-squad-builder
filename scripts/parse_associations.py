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
    """Return {lowercase_name: card_obj} for all gear-category cards."""
    cards = Card.query.filter(Card.card_category.in_(GEAR_CATEGORIES)).all()
    return {c.name.lower(): c for c in cards}


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


def extract_refs(notes: str, soldier_nation: str, lookup: dict) -> list:
    """
    Return list of (child_card, quantity) for each card reference found in notes.

    Parameters
    ----------
    notes          : raw notes text from the soldier card
    soldier_nation : nation string from the card (e.g. "US", "UK", "Germany")
    lookup         : {lowercase_name: Card} for all gear-category cards

    Returns
    -------
    list of (Card, int) — unique, ordered as encountered
    """
    if not notes:
        return []

    refs = []
    seen_ids = set()
    soldier_nation_low = (soldier_nation or '').lower()

    lines = [l.strip() for l in re.split(r'\n', notes) if l.strip()]

    for line in lines:
        line = line.rstrip('.')

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

        candidate_low = candidate.lower()

        # Pass 1: exact match
        if candidate_low in lookup:
            card = lookup[candidate_low]
            if card.id not in seen_ids:
                refs.append((card, quantity))
                seen_ids.add(card.id)
            continue

        # Pass 2: suffix match — handles nation-prefixed names like "UK-Keep Calm"
        suffix = f'-{candidate_low}'
        matches = [(name, card) for name, card in lookup.items() if name.endswith(suffix)]

        if not matches:
            continue

        if len(matches) == 1:
            card = matches[0][1]
            if card.id not in seen_ids:
                refs.append((card, quantity))
                seen_ids.add(card.id)
        else:
            # Multiple nation variants — prefer the one matching the soldier's nation
            preferred = [
                (name, card) for name, card in matches
                if name.startswith(soldier_nation_low + '-')
            ]
            if len(preferred) == 1:
                card = preferred[0][1]
                if card.id not in seen_ids:
                    refs.append((card, quantity))
                    seen_ids.add(card.id)
            # else: ambiguous (multiple nation matches or no nation match) — skip

    return refs


def main():
    app = create_app()
    with app.app_context():
        print('Building gear lookup...')
        lookup = build_gear_lookup()
        print(f'  {len(lookup)} gear/skill cards indexed.')

        soldiers = Card.query.filter_by(card_category='Soldier').all()
        print(f'  {len(soldiers)} soldier cards to process.')

        inserted = 0
        updated = 0
        soldier_with_assoc = 0

        for soldier in soldiers:
            refs = extract_refs(soldier.notes, soldier.nation, lookup)
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

        db.session.commit()

        total = CardAssociation.query.count()
        print(f'\nDone.')
        print(f'  Soldiers with associations : {soldier_with_assoc}/{len(soldiers)}')
        print(f'  New rows inserted          : {inserted}')
        print(f'  Existing rows updated      : {updated}')
        print(f'  Total rows in DB           : {total}')


if __name__ == '__main__':
    main()
