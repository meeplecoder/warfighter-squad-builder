#!/usr/bin/env python3
"""
Load the card image CDN mapping (card number -> hash) into cards.cdn_hash. The manifest stays outside the
repository; pass its path (cards_printing/cards_cdn_manifest.json, JSON {"W-001": "<hash>", ...}).

Run from the warfighter-squad-builder/ directory (in production, on the server with the production DB):
    python scripts/load_cdn_hashes.py /path/to/cards_cdn_manifest.json
    python scripts/load_cdn_hashes.py /path/to/cards_cdn_manifest.json --dry-run

Then set CARD_CDN_BASE_URL (e.g. https://www2cards.armydice.com) in the environment.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
except ImportError:
    pass

from app import create_app, db
from app.models import Card

HASH_RE = re.compile(r'^[0-9a-f]{64}$')


def main():
    ap = argparse.ArgumentParser(description='Load the CDN hash manifest into cards.cdn_hash.')
    ap.add_argument('manifest', help='path to cards_cdn_manifest.json')
    ap.add_argument('--dry-run', action='store_true', help='report only, change nothing')
    args = ap.parse_args()

    with open(args.manifest, encoding='utf-8') as f:
        manifest = {k.upper(): v for k, v in json.load(f).items()}
    bad = [k for k, v in manifest.items() if not HASH_RE.match(str(v))]
    if bad:
        sys.exit(f'invalid hash for: {", ".join(bad[:10])}')

    app = create_app()
    with app.app_context():
        cards = {c.number.upper(): c for c in Card.query.filter(Card.owner_user_id.is_(None)).all()}
        updated = 0
        for number, h in manifest.items():
            card = cards.get(number)
            if not card:
                print(f'  not in database: {number}')
            elif card.cdn_hash != h:
                card.cdn_hash = h
                updated += 1
        without = sum(1 for n in cards if n not in manifest)
        if args.dry_run:
            db.session.rollback()
        else:
            db.session.commit()
        print(f'{"would update" if args.dry_run else "updated"} {updated} cards; '
              f'{without} catalog cards have no hash')


if __name__ == '__main__':
    main()
