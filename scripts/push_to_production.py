#!/usr/bin/env python3
"""
Push the squads and campaigns of a local database to a running server through its HTTP API.

    python scripts/push_to_production.py --url https://warfighterww2.fly.dev --login admin [--db data/warfighter.db] [--dry-run]
    (the password is asked, or taken from the WF_PASSWORD environment variable)

For each local squad / campaign the server is asked first; one that is already there is skipped, so the script can
be re-run safely (e.g. after a failure). Nothing is ever updated or deleted on the server.
  squad     = same name, same mission card and same soldiers + gear (cards compared by card number)
  campaign  = same name and the same mission titles

Limits of the public API, by design: everything is created under the account you log in with (normally the admin),
not under the original owner; created/updated times are the push time; likes and comments are not copied. A squad
that no longer passes validation is saved as a draft instead of published (reported at the end).
Standard library only; run it on the machine that has the local database.
"""
import argparse
import getpass
import http.cookiejar
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request


class Api:
    def __init__(self, base):
        self.base = base.rstrip('/')
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
        try:
            with self.opener.open(req, timeout=60) as r:
                return r.status, json.loads(r.read() or b'null')
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b'null')
            except ValueError:
                return e.code, None


class Local:
    def __init__(self, path):
        self.con = sqlite3.connect(path)
        self.con.row_factory = sqlite3.Row
        self.num = {r['id']: r['number'] for r in self.con.execute('SELECT id, number FROM cards')}

    def rows(self, sql, *args):
        return self.con.execute(sql, args).fetchall()

    def n(self, card_id):
        return self.num.get(card_id) if card_id else None

    def squads(self):
        for s in self.rows('SELECT s.*, u.username FROM squads s JOIN users u ON u.id=s.user_id ORDER BY s.id'):
            soldiers = []
            for so in self.rows('SELECT * FROM squad_soldiers WHERE squad_id=? ORDER BY sort_order, id', s['id']):
                gear = [(self.n(g['card_id']), g['quantity']) for g in
                        self.rows('SELECT * FROM squad_gear WHERE squad_soldier_id=? ORDER BY id', so['id'])]
                soldiers.append({'card': self.n(so['card_id']), 'sort_order': so['sort_order'], 'gear': gear})
            objectives = [self.n(o['card_id']) for o in
                          self.rows('SELECT * FROM squad_objectives WHERE squad_id=? ORDER BY sort_order, id', s['id'])]
            yield {'id': s['id'], 'owner': s['username'], 'name': s['name'], 'nation': s['nation'], 'notes': s['notes'],
                   'status': s['status'], 'parent': s['parent_squad_id'], 'mission': self.n(s['mission_card_id']),
                   'situation': self.n(s['situation_card_id']), 'objectives': objectives, 'soldiers': soldiers}

    def campaigns(self):
        for c in self.rows('SELECT c.*, u.username FROM campaigns c JOIN users u ON u.id=c.user_id ORDER BY c.id'):
            missions = [dict(m) for m in self.rows(
                'SELECT * FROM campaign_missions WHERE campaign_id=? ORDER BY sort_order, id', c['id'])]
            links = [dict(l) for l in self.rows('SELECT * FROM campaign_links WHERE campaign_id=? ORDER BY id', c['id'])]
            yield dict(c), missions, links


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--url', required=True, help='server address, e.g. https://warfighterww2.fly.dev')
    ap.add_argument('--login', default='admin', help='username or e-mail to sign in with (default: admin)')
    ap.add_argument('--db', default='data/warfighter.db')
    ap.add_argument('--dry-run', action='store_true', help='only report what would be created')
    args = ap.parse_args()

    local = Local(args.db)
    api = Api(args.url)
    password = os.environ.get('WF_PASSWORD') or getpass.getpass(f'Password for {args.login} on {args.url}: ')
    code, body = api.call('POST', '/api/auth/login', {'login': args.login, 'password': password})
    if code != 200:
        sys.exit(f'Login failed ({code}): {(body or {}).get("error")}')
    print(f'Signed in as {body["user"]["username"]}.')

    # --- card numbers -> ids on the server -------------------------------------------------------------
    ids = {}

    def card_id(number):
        if number is None:
            return None
        if number not in ids:
            code, body = api.call('GET', f'/api/cards/{number}')
            ids[number] = body['card']['id'] if code == 200 and body and 'card' in body else None
            if ids[number] is None and code == 200 and body and 'id' in body:
                ids[number] = body['id']
            if ids[number] is None:
                print(f'  ! card {number} not found on the server')
        return ids[number]

    # --- what the server already has ---------------------------------------------------------------------
    remote_squads = []
    page = 1
    while True:
        code, body = api.call('GET', f'/api/squads?per_page=100&page={page}')
        if code != 200:
            sys.exit(f'Cannot list squads ({code}).')
        remote_squads += body['items']
        if page >= body['pages']:
            break
        page += 1
    by_name = {}
    for s in remote_squads:
        by_name.setdefault(s['name'].strip(), []).append(s)
    detail_cache = {}

    def remote_soldiers(s):
        """Soldiers + gear of a server squad, as comparable card numbers."""
        if s['id'] not in detail_cache:
            code, body = api.call('GET', f'/api/squads/{s["id"]}')
            detail_cache[s['id']] = tuple(sorted(
                (so['card']['number'], tuple(sorted((g['card']['number'], g['quantity']) for g in so['gear'])))
                for so in body['squad']['soldiers']))
        return detail_cache[s['id']]

    taken = set()   # server squads already matched by an earlier local one (equal twins)

    def find_squad(sq):
        mission_id = card_id(sq['mission'])
        want = tuple(sorted((so['card'], tuple(sorted(so['gear']))) for so in sq['soldiers']))
        for r in by_name.get(sq['name'].strip(), []):
            if r['id'] not in taken and r['mission']['id'] == mission_id and remote_soldiers(r) == want:
                return r['id']
        return None

    # --- squads --------------------------------------------------------------------------------------------
    squad_map = {}   # local id -> server id
    created = skipped = 0
    downgraded, failed = [], []
    for sq in local.squads():
        label = f'squad "{sq["name"]}" ({sq["owner"]})'
        found = find_squad(sq)
        if found:
            taken.add(found)
            squad_map[sq['id']] = found
            skipped += 1
            continue
        if args.dry_run:
            print(f'  would create {label}')
            created += 1
            continue
        payload = {
            'name': sq['name'], 'nation': sq['nation'], 'notes': sq['notes'] or '', 'status': sq['status'],
            'mission_card_id': card_id(sq['mission']), 'situation_card_id': card_id(sq['situation']),
            'objective_card_ids': [card_id(n) for n in sq['objectives'] if card_id(n)],
            'parent_squad_id': squad_map.get(sq['parent']),
            'soldiers': [{'card_id': card_id(so['card']), 'sort_order': so['sort_order'],
                          'gear': [{'card_id': card_id(g), 'quantity': q} for g, q in so['gear']]}
                         for so in sq['soldiers']],
        }
        code, body = api.call('POST', '/api/squads', payload)
        if code == 422 and payload['status'] == 'published':      # no longer valid under today's rules
            payload['status'] = 'draft'
            code, body = api.call('POST', '/api/squads', payload)
            if code == 201:
                downgraded.append(label)
        if code != 201:
            failed.append(f'{label}: {code} {(body or {}).get("error")}')
            continue
        squad_map[sq['id']] = body['squad']['id']
        created += 1
        print(f'  created {label}')
    print(f'Squads: {created} {"to create" if args.dry_run else "created"}, {skipped} already there, {len(failed)} failed.')

    # --- campaigns -----------------------------------------------------------------------------------------
    code, body = api.call('GET', '/api/campaigns?per_page=100')
    remote_campaigns = body['items'] if code == 200 else []
    c_created = c_skipped = 0
    c_failed = []
    for c, missions, links in local.campaigns():
        label = f'campaign "{c["name"]}" ({c["username"]})'
        titles = [m['title'] or '' for m in missions]
        same = None
        for r in remote_campaigns:
            if r['name'].strip() != c['name'].strip():
                continue
            code, body = api.call('GET', f'/api/campaigns/{r["id"]}')
            if code == 200 and [m['title'] or '' for m in body['campaign']['missions']] == titles:
                same = r['id']
                break
        if same:
            c_skipped += 1
            continue
        if args.dry_run:
            print(f'  would create {label}')
            c_created += 1
            continue
        key = {m['id']: str(i) for i, m in enumerate(missions)}
        payload = {
            **{k: c[k] for k in ('name', 'summary', 'intro', 'nation', 'theater', 'enemy', 'period', 'flow_type',
                                 'language', 'status')},
            'settings': json.loads(c['settings'] or '{}'),
            'missions': [{
                'key': key[m['id']], 'code': m['code'], 'title': m['title'], 'briefing': m['briefing'],
                'debrief': m['debrief'], 'requirements': m['requirements'], 'setup': m['setup'],
                'victory': m['victory'], 'rewards': m['rewards'], 'is_entry': m['is_entry'],
                'mission_card_id': card_id(local.n(m['mission_card_id'])),
                'situation_card_id': card_id(local.n(m['situation_card_id'])),
                'objective_card_id': card_id(local.n(m['objective_card_id'])),
                'squad_id': squad_map.get(m['squad_id']),
                'rp_override': m['rp_override'], 'time_override': m['time_override'],
                'loadout_override': m['loadout_override']} for m in missions],
            'links': [{'from': key[l['from_mission_id']], 'to': key[l['to_mission_id']],
                       'condition': l['condition'], 'label': l['label']} for l in links],
        }
        code, body = api.call('POST', '/api/campaigns', payload)
        if code == 422 and payload['status'] == 'published':
            payload['status'] = 'draft'
            code, body = api.call('POST', '/api/campaigns', payload)
            if code == 201:
                downgraded.append(label)
        if code != 201:
            c_failed.append(f'{label}: {code} {(body or {}).get("error")} {(body or {}).get("errors", "")}')
            continue
        c_created += 1
        print(f'  created {label}')
    print(f'Campaigns: {c_created} {"to create" if args.dry_run else "created"}, {c_skipped} already there, '
          f'{len(c_failed)} failed.')

    for line in downgraded:
        print(f'  saved as draft (does not pass validation): {line}')
    for line in failed + c_failed:
        print(f'  FAILED {line}')
    if failed or c_failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
