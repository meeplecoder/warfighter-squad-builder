#!/usr/bin/env python3
"""
Import cards from CSV into the SQLite database.
Run from the warfighter-squad-builder/ directory:
    python scripts/import_cards.py [--csv path/to/cards2.csv]
"""
import os
import sys
import re
import csv
import argparse

# Allow importing app from parent directory context
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))
except ImportError:
    pass

from app import create_app, db
from app.models import Card


# ---------------------------------------------------------------------------
# Type normalization
# ---------------------------------------------------------------------------

def normalize_type(raw):
    raw = raw.strip()
    if raw == 'Player Soldier' or raw.startswith('Player Soldier '):
        return 'Soldier', 'Player'
    if raw == 'Non Player Soldier' or raw.startswith('Non Player Soldier '):
        return 'Soldier', 'NPS'
    if raw == 'Squad Soldier' or raw.startswith('Squad Soldier '):
        return 'Soldier', 'Squad'
    if raw == 'Team Soldier' or raw.startswith('Team Soldier '):
        return 'Soldier', 'Team'
    if raw == 'Squad Vehicle' or raw.startswith('Squad Vehicle '):
        return 'Soldier', 'Vehicle'
    if raw.startswith('Alternate Weapon'):
        return 'Weapon', 'Alternate'
    if raw.startswith('Weapon '):
        return 'Weapon', raw[7:].strip()
    if raw == 'Weapon':
        return 'Weapon', 'General'
    m = re.match(r'Equipment \((.+)\)', raw)
    if m:
        return 'Equipment', m.group(1)
    if raw == 'Equipment':
        return 'Equipment', 'General'
    if raw == 'Skill (Nation)':
        return 'Skill', 'Nation'
    if raw == 'Skill (Specialist)':
        return 'Skill', 'Specialist'
    if raw == 'Skill (Fortification)':
        return 'Skill', 'Fortification'
    if raw == 'Skill':
        return 'Skill', 'General'
    if raw.startswith('Airborne Mission'):
        return 'Mission', 'Airborne'
    if raw.startswith('Mission-Shore Invasion') or raw.startswith('Mission Shore Invasion'):
        return 'Mission', 'Shore Invasion'
    if raw.startswith('Mission '):
        return 'Mission', raw[8:].strip()
    if raw == 'Mission':
        return 'Mission', 'General'
    if raw.startswith('Objective - Assault') or raw.startswith('Objective-Assault'):
        return 'Objective', 'Assault'
    if raw.startswith('Objective Embedded'):
        return 'Objective', 'Embedded'
    if raw.startswith('Objective-Shore Invasion') or raw.startswith('Objective Shore Invasion'):
        return 'Objective', 'Shore Invasion'
    if raw.startswith('Objective '):
        return 'Objective', raw[10:].strip()
    if raw == 'Objective':
        return 'Objective', 'General'
    if raw.startswith('Surf-Shore Invasion') or raw.startswith('Surf Shore Invasion'):
        return 'Location', 'Surf Shore'
    if raw.startswith('Beach-Shore Invasion') or raw.startswith('Beach Shore Invasion'):
        return 'Location', 'Beach Shore'
    if raw.startswith('Location '):
        return 'Location', raw[9:].strip()
    if raw == 'Location':
        return 'Location', 'General'
    m = re.match(r'Action \((.+)\)', raw)
    if m:
        return 'Action', m.group(1)
    if raw == 'Action':
        return 'Action', 'General'
    if raw.startswith('Hostile Elite'):
        return 'Hostile', 'Elite'
    if raw.startswith('Hostile Frontline'):
        return 'Hostile', 'Frontline'
    if raw.startswith('Hostile Embedded'):
        return 'Hostile', 'Embedded'
    if raw.startswith('Anti-Vehicle Elite'):
        return 'Hostile', 'Anti-Vehicle'
    m = re.match(r'Service Record \((.+)\)', raw)
    if m:
        return 'Service Record', m.group(1)
    if raw.startswith('Service Record'):
        return 'Service Record', 'General'
    m = re.match(r'Event \((.+)\)', raw)
    if m:
        return 'Event', m.group(1)
    if raw == 'Event':
        return 'Event', 'General'
    if raw == 'Landing Zone':
        return 'Landing Zone', 'General'
    if raw == 'Enemy Lines':
        return 'Enemy Lines', 'General'
    if raw == 'Medals':
        return 'Medal', 'General'
    if raw == 'Shore Defense':
        return 'Shore Defense', 'General'
    if raw == 'Situation':
        return 'Situation', 'General'
    if raw.startswith('Fortification'):
        suffix = raw[13:].strip()
        return 'Fortification', suffix or 'General'
    if raw == 'Frame':
        return 'Reference', 'Frame'
    if raw == 'Reference':
        return 'Reference', 'General'
    if raw.startswith('Theology') or raw.startswith('Clergy Power'):
        return 'Clergy', raw
    return 'Other', raw


# ---------------------------------------------------------------------------
# Stats parsing
# ---------------------------------------------------------------------------

KEY_MAP = {
    'RC': 'resource_cost',
    'M': 'movement',
    'C': 'cover',
    'H': 'health',
    'L': 'loadout',
    'HtH': 'hth',
    'A': 'actions',
    'EN': 'entrance_cost',
    'ACHtH': 'action_cost_hth',
    'R': 'resources',
    'T': 'time',
    'OB': 'objective_location',
    'LM': 'loadout_modifier',
    'REIN': 'reinforcements',
    'XP': 'xp_value',
    'EV': 'xp_value',
    'H#': 'hostile_count',
    'N': 'noise',
    'SUP': 'support_cost',
    'CV': 'covert_cost',
    'Gain': 'gain',
    'Loss': 'loss',
    'Cost': 'resource_cost',
}

TEXT_COLS = {'reinforcements', 'hostile_count'}


def parse_int_val(val):
    """Parse a possibly-signed, possibly-prefixed integer string."""
    val = val.strip()
    # Strip leading # (e.g. '#03')
    val = val.lstrip('#')
    if not val:
        return None
    try:
        return int(val)
    except ValueError:
        return None


def parse_stats(stats_str):
    result = {}
    if not stats_str:
        return result
    for line in stats_str.split('\n'):
        line = line.strip()
        if ':' not in line:
            continue
        key, _, raw_val = line.partition(':')
        key = key.strip()
        raw_val = raw_val.strip()
        col = KEY_MAP.get(key)
        if col is None:
            continue
        if col in TEXT_COLS:
            result[col] = raw_val
        else:
            v = parse_int_val(raw_val)
            if v is not None:
                result[col] = v
    return result


# ---------------------------------------------------------------------------
# Image detection
# ---------------------------------------------------------------------------

IMAGE_EXTS = ['.jpg', '.jpeg', '.png', '.webp']


def check_has_image(images_dir, number):
    if not os.path.isdir(images_dir):
        return 0
    for ext in IMAGE_EXTS:
        if os.path.isfile(os.path.join(images_dir, number + ext)):
            return 1
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Import Warfighter cards from CSV.')
    parser.add_argument('--csv', help='Path to cards CSV file')
    args = parser.parse_args()

    app = create_app()

    with app.app_context():
        csv_path = args.csv or app.config.get('CARDS_CSV', '../cards2.csv')
        if not os.path.isabs(csv_path):
            csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), csv_path)
            # If that doesn't exist, try relative to cwd
            if not os.path.exists(csv_path):
                csv_path = os.path.join(os.getcwd(), args.csv or '../cards2.csv')

        # Also try the squad_builder directory
        if not os.path.exists(csv_path):
            alt = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'cards2.csv')
            alt = os.path.normpath(alt)
            if os.path.exists(alt):
                csv_path = alt

        if not os.path.exists(csv_path):
            print(f'ERROR: CSV file not found at {csv_path}')
            print('Pass --csv /path/to/cards2.csv to specify the location.')
            sys.exit(1)

        print(f'Importing from: {csv_path}')

        images_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'static', 'card_images'
        )

        inserted = 0
        updated = 0
        skipped = 0
        total = 0

        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            batch = []
            for row in reader:
                total += 1
                number = (row.get('Number') or '').strip()
                name = (row.get('Name') or '').strip()
                raw_type = (row.get('Type') or '').strip()
                nation = (row.get('Nation') or '').strip() or None
                stats_str = row.get('Stats') or ''
                notes = (row.get('Notes') or '').strip() or None
                module = (row.get('Module') or '').strip()
                vassal_module = (row.get('Vassal Module') or '').strip() or None

                if not number or not name:
                    skipped += 1
                    continue

                category, subtype = normalize_type(raw_type)
                stats = parse_stats(stats_str)
                has_image = check_has_image(images_dir, number)

                # Parse pre-printed CX (combat experience) and XP from notes
                combat_xp = 0
                soldier_xp = 0
                if notes and category == 'Soldier':
                    for line in notes.split('\n'):
                        stripped = line.strip()
                        if not combat_xp:
                            m = re.match(r'^(\d+)\s+CX\.?$', stripped, re.IGNORECASE)
                            if m:
                                combat_xp = int(m.group(1))
                        if not soldier_xp:
                            m = re.match(r'^(\d+)\s+XP\.?$', stripped, re.IGNORECASE)
                            if m:
                                soldier_xp = int(m.group(1))

                existing = Card.query.filter_by(number=number).first()
                if existing:
                    existing.name = name
                    existing.raw_type = raw_type
                    existing.card_category = category
                    existing.card_subtype = subtype
                    existing.nation = nation
                    existing.module = module
                    existing.notes = notes
                    existing.vassal_module = vassal_module
                    existing.has_image = has_image
                    existing.cx = combat_xp
                    existing.xp = soldier_xp
                    for col, val in stats.items():
                        setattr(existing, col, val)
                    updated += 1
                else:
                    card = Card(
                        number=number,
                        name=name,
                        raw_type=raw_type,
                        card_category=category,
                        card_subtype=subtype,
                        nation=nation,
                        module=module,
                        notes=notes,
                        vassal_module=vassal_module,
                        has_image=has_image,
                        cx=combat_xp,
                        xp=soldier_xp,
                        **{k: v for k, v in stats.items()},
                    )
                    db.session.add(card)
                    inserted += 1

                if (inserted + updated) % 500 == 0:
                    db.session.commit()
                    print(f'  ... {inserted + updated} processed', end='\r')

        db.session.commit()
        print(f'\nDone. Total: {total} | Inserted: {inserted} | Updated: {updated} | Skipped: {skipped}')


if __name__ == '__main__':
    main()
