"""Load campaign YAML files (docs/campaign_yaml.md) into the database.

The owner is --owner, else the file's `author:`; a missing owner is created without a password (like the
community squad importers). A campaign with the same name and owner is replaced. Published by default;
files that are not complete enough to publish are refused unless --draft.

Usage: python scripts/import_campaign_yaml.py campaigns/normandia_pablosolano.yaml [--owner NAME] [--draft]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask_login import login_user

from app import create_app, db
from app.models import Campaign, User
from app.campaigns import _parse, _publish_errors, _save
from app.campaign_yaml import load, CampaignYamlError


def owner_user(username):
    user = User.query.filter(User.username_lower == username.lower()).first()
    if not user:
        user = User(username=username, email=f'{username.lower()}@community.local', password_hash=None,
                    full_name=username)
        db.session.add(user)
        db.session.flush()
        print(f'Owner user created: {username}')
    return user


def import_file(path, owner_name, draft):
    with open(path, encoding='utf-8') as f:
        payload, warnings = load(f.read())
    for w in warnings:
        print(f'  warning: {w}')
    owner_name = owner_name or payload['author']
    if not owner_name:
        raise CampaignYamlError('No owner: pass --owner or set author: in the file.')
    owner = owner_user(owner_name)
    login_user(owner)

    fields, settings, missions, links, errors = _parse(payload)
    status = 'draft' if draft else 'published'
    if status == 'published':
        errors += _publish_errors(fields, settings, missions)
    if errors:
        raise CampaignYamlError('cannot import:\n    ' + '\n    '.join(errors))

    c = Campaign.query.filter_by(user_id=owner.id, name=fields['name']).first()
    action = 'replaced' if c else 'created'
    if not c:
        c = Campaign(user_id=owner.id, name=fields['name'], flow_type=fields['flow_type'], status=status)
        db.session.add(c)
        db.session.flush()
    c.status = status
    _save(c, fields, settings, missions, links)
    db.session.commit()
    print(f'Campaign {c.id} {action} ({status}): {c.name} — {len(missions)} missions, owner {owner.username}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('files', nargs='+')
    ap.add_argument('--owner', help='username that owns the campaign (default: author: in the file)')
    ap.add_argument('--draft', action='store_true', help='save as draft instead of publishing')
    args = ap.parse_args()

    app = create_app()
    failed = 0
    for path in args.files:
        print(path)
        with app.test_request_context():
            try:
                import_file(path, args.owner, args.draft)
            except (OSError, CampaignYamlError) as e:
                db.session.rollback()
                print(f'  error: {e}')
                failed += 1
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
