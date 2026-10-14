#!/usr/bin/env python3
"""
Create the admin account, or set/reset its password. There is exactly one admin: the account named `admin`
(app/roles.py). The name is reserved at registration, so nobody can sign up as admin — this script is the only way.

Run from the warfighter-squad-builder/ directory:
    python scripts/create_admin.py --email you@example.com          # prompts for the password
    python scripts/create_admin.py                                   # existing admin: just reset the password
    ADMIN_PASSWORD=... python scripts/create_admin.py --email ...   # non-interactive (CI / provisioning)

The account is created verified, and its other sessions are signed out when the password changes. The admin can
edit, publish and delete any squad and campaign, sees every draft, and is the only one who can open the
translation editor.
"""
import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
except ImportError:
    pass

from app import create_app, db, security
from app.models import User, now_utc
from app.roles import ADMIN_USERNAME


def main():
    ap = argparse.ArgumentParser(description='Create the admin account or reset its password.')
    ap.add_argument('--email', help='email of the admin account (required when creating it)')
    args = ap.parse_args()

    app = create_app()
    with app.app_context():
        user = User.query.filter_by(username_lower=ADMIN_USERNAME).first()
        email = (args.email or (user.email if user else '') or '').strip().lower()
        if not email:
            email = input('Admin email: ').strip().lower()
        other = User.query.filter(User.email == email, User.username_lower != ADMIN_USERNAME).first()
        if other:
            sys.exit(f'The email {email} already belongs to the account {other.username!r}; use another address.')

        password = os.environ.get('ADMIN_PASSWORD')
        if not password:
            password = getpass.getpass('New admin password: ')
            if password != getpass.getpass('Repeat password: '):
                sys.exit('The passwords do not match.')
        problem = security.password_problem(password, ADMIN_USERNAME, email)
        if problem:
            sys.exit(problem)

        created = user is None
        if created:
            user = User(username=ADMIN_USERNAME, email=email)
            db.session.add(user)
        user.email = email
        user.email_verified_at = user.email_verified_at or now_utc()
        security.set_password(user, password)
        security.revoke_sessions(user)
        db.session.commit()
        print(f"{'Created' if created else 'Updated'} the admin account ({user.email}).")


if __name__ == '__main__':
    main()
