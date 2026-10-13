#!/usr/bin/env python3
"""
Give a user the admin flag (the card-translation editor is owner-only).
Run from the warfighter-squad-builder/ directory:
    python scripts/make_admin.py USERNAME            # grant
    python scripts/make_admin.py USERNAME --revoke   # remove
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
except ImportError:
    pass

from app import create_app, db
from app.models import User


def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith('-'):
        print(__doc__)
        sys.exit(1)
    name, revoke = sys.argv[1], '--revoke' in sys.argv
    app = create_app()
    with app.app_context():
        user = User.query.filter_by(username_lower=name.lower()).first()
        if not user:
            print(f'No user named {name!r}. Register in the web app first.')
            sys.exit(1)
        user.is_admin = 0 if revoke else 1
        db.session.commit()
        print(f'{user.username}: admin = {bool(user.is_admin)}')


if __name__ == '__main__':
    main()
