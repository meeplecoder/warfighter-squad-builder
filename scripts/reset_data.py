#!/usr/bin/env python3
"""
Reset the database to its initial state: ALL squads, campaigns (with likes, comments, custom missions) and ALL
accounts except `admin` are DELETED, then the cards are (re)loaded from the CSV. Card translations, the admin
account and the cards themselves stay. This cannot be undone.

Run from the warfighter-squad-builder/ directory (DATABASE_URL selects the database):
    python scripts/reset_data.py --yes [--csv cards/warfighter_cards.csv]
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app import create_app, db
from app.roles import ADMIN_USERNAME

# children before parents (SQLite may not enforce ON DELETE CASCADE)
WIPE = ['campaign_links', 'campaign_missions', 'campaigns', 'squad_likes', 'squad_comments', 'squad_gear',
        'squad_soldiers', 'squad_objectives', 'squads']


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--yes', action='store_true', help='confirm that all squads, campaigns and non-admin users go')
    ap.add_argument('--csv', help='cards CSV to load (default: CARDS_CSV / cards/warfighter_cards.csv)')
    args = ap.parse_args()
    if not args.yes:
        sys.exit('Refusing to run without --yes: this deletes all squads, campaigns and non-admin users.')

    app = create_app()
    with app.app_context():
        admin = db.session.execute(text('SELECT id FROM users WHERE username_lower=:a'), {'a': ADMIN_USERNAME}).first()
        if not admin:
            sys.exit('There is no admin account: run create-admin first (nothing was deleted).')
        print(f'Database: {db.engine.url}')
        for t in WIPE:
            n = db.session.execute(text(f'DELETE FROM {t}')).rowcount
            print(f'  {t}: {n} deleted')
        n = db.session.execute(text('DELETE FROM cards WHERE owner_user_id IS NOT NULL')).rowcount
        print(f'  custom cards: {n} deleted')
        for t in ('auth_tokens', 'user_modules'):
            db.session.execute(text(f'DELETE FROM {t} WHERE user_id != :a'), {'a': admin[0]})
        n = db.session.execute(text('DELETE FROM users WHERE id != :a'), {'a': admin[0]}).rowcount
        print(f'  users: {n} deleted (admin kept)')
        db.session.commit()

    cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'import_cards.py')]
    if args.csv:
        cmd += ['--csv', args.csv]
    print('Loading cards...')
    sys.exit(subprocess.call(cmd))


if __name__ == '__main__':
    main()
