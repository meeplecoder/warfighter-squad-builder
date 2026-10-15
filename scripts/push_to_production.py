#!/usr/bin/env python3
"""
Push the squads and campaigns of a local database to a running server through its HTTP API.

    python scripts/push_to_production.py --url https://warfighterww2.fly.dev --login admin [--db data/warfighter.db] [--dry-run]
        [--owner-map admin=MeepleCoder]      # create the admin's items under another account
    (the password is asked, or taken from the WF_PASSWORD environment variable)

Each local squad / campaign is looked up on the server by name and owner (the n-th local item of that name matches
the n-th one on the server). Missing ones are created. Ones that exist are compared field by field and UPDATED
only when something differs (a repeat run changes nothing). Nothing is ever deleted on the server.
  - an item with no match under that owner is also looked for under any owner by name (+ same mission and soldiers
    for squads) and updated in place; the API cannot change an existing item's owner, so that is only reported.

Each item is created under its original owner: logged in as the admin, the API accepts an `owner` username (a
missing account is created 'reserved', without a password). Any other login gets a 403. Created/updated times are
the push time; likes and comments are not copied. A squad that no longer passes validation is saved as a draft
instead of published (reported at the end).
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
    ap.add_argument('--dry-run', action='store_true', help='only report what would be created or updated')
    ap.add_argument('--fix-owner', action='store_true',
                    help='an item that exists under a different owner is DELETED and created again under the right '
                         'one (the API cannot change an owner); its likes and comments are lost')
    ap.add_argument('--owner-map', action='append', default=[], metavar='FROM=TO',
                    help='use owner TO for the items of local owner FROM (repeatable), e.g. admin=MeepleCoder')
    args = ap.parse_args()

    owner_map = {}
    for pair in args.owner_map:
        if '=' not in pair:
            sys.exit(f'--owner-map expects FROM=TO, got {pair!r}')
        src, dst = pair.split('=', 1)
        owner_map[src.strip().lower()] = dst.strip()

    def owner_of(name):
        return owner_map.get(name.lower(), name)

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
            if ids[number] is None:
                print(f'  ! card {number} not found on the server')
        return ids[number]

    def list_all(path):
        items, page = [], 1
        while True:
            code, body = api.call('GET', f'{path}?per_page=100&page={page}')
            if code != 200:
                sys.exit(f'Cannot list {path} ({code}).')
            items += body['items']
            if page >= body['pages']:
                return items
            page += 1

    def norm(v):
        return v if v not in (None, '') else ''

    # ======================================================================================================
    # squads
    # ======================================================================================================
    remote_squads = list_all('/api/squads')
    taken = set()
    details = {}

    def squad_detail(rid):
        if rid not in details:
            details[rid] = api.call('GET', f'/api/squads/{rid}')[1]['squad']
        return details[rid]

    def squad_state(d):
        """Comparable content of a server squad detail (cards as server ids, soldiers as card numbers)."""
        return {
            'mission': d['mission']['id'], 'situation': (d.get('situation') or {}).get('id'),
            'objectives': tuple(o['id'] for o in d['objectives']),
            'nation': d['nation'], 'notes': norm(d.get('notes')), 'status': d['status'],
            'soldiers': tuple(sorted((so['card']['number'], tuple(sorted((g['card']['number'], g['quantity'])
                                                                         for g in so['gear'])))
                                     for so in d['soldiers'])),
        }

    def local_squad_state(sq):
        return {
            'mission': card_id(sq['mission']), 'situation': card_id(sq['situation']),
            'objectives': tuple(card_id(n) for n in sq['objectives']),
            'nation': sq['nation'], 'notes': norm(sq['notes']), 'status': sq['status'],
            'soldiers': tuple(sorted((so['card'], tuple(sorted(so['gear']))) for so in sq['soldiers'])),
        }

    def find_squad(sq, owner):
        mine = [r for r in remote_squads if r['name'].strip().lower() == sq['name'].strip().lower()
                and r['owner']['username'].lower() == owner.lower() and r['id'] not in taken]
        if mine:
            return mine[0], False
        # not under that owner: same name + mission + soldiers under anybody
        mission_id = card_id(sq['mission'])
        want = local_squad_state(sq)['soldiers']
        for r in remote_squads:
            if r['id'] in taken or r['name'].strip().lower() != sq['name'].strip().lower():
                continue
            if r['mission']['id'] == mission_id and squad_state(squad_detail(r['id']))['soldiers'] == want:
                return r, True
        return None, False

    squad_map = {}   # local id -> server id
    counts = {'squads': [0, 0, 0], 'campaigns': [0, 0, 0]}      # created, updated, unchanged
    downgraded, failed, notes, wrong_owner = [], [], [], []
    for sq in local.squads():
        owner = owner_of(sq['owner'])
        label = f'squad "{sq["name"]}" ({owner})'
        found, other_owner = find_squad(sq, owner)
        if found and other_owner and args.fix_owner:
            if args.dry_run:
                print(f'  would delete and recreate {label} (now owned by {found["owner"]["username"]})')
            else:
                api.call('DELETE', f'/api/squads/{found["id"]}')
                remote_squads.remove(found)
                print(f'  deleted {label} (was owned by {found["owner"]["username"]})')
            found = None
        payload = {
            'owner': owner, 'name': sq['name'], 'nation': sq['nation'], 'notes': sq['notes'] or '',
            'status': sq['status'], 'mission_card_id': card_id(sq['mission']),
            'situation_card_id': card_id(sq['situation']),
            'objective_card_ids': [card_id(n) for n in sq['objectives'] if card_id(n)],
            'parent_squad_id': squad_map.get(sq['parent']),
            'soldiers': [{'card_id': card_id(so['card']), 'sort_order': so['sort_order'],
                          'gear': [{'card_id': card_id(g), 'quantity': q} for g, q in so['gear']]}
                         for so in sq['soldiers']],
        }
        if found:
            taken.add(found['id'])
            squad_map[sq['id']] = found['id']
            remote, wanted = squad_state(squad_detail(found['id'])), local_squad_state(sq)
            same_content = {k: v for k, v in remote.items() if k != 'status'} == \
                {k: v for k, v in wanted.items() if k != 'status'}
            if other_owner:
                notes.append(f'{label}: exists under {found["owner"]["username"]} (owner not changed)')
            if same_content and remote['status'] == sq['status']:
                counts['squads'][2] += 1
                continue
            if same_content and sq['status'] == 'published':      # only the status differs: publish if it is valid now
                code, v = api.call('POST', '/api/squads/validate', payload)
                if code != 200 or not v.get('valid'):
                    counts['squads'][2] += 1
                    continue
            if same_content and sq['status'] == 'draft' and remote['status'] == 'published':
                counts['squads'][2] += 1                               # never unpublish
                continue
            if args.dry_run:
                print(f'  would update {label}')
                counts['squads'][1] += 1
                continue
            code, body = api.call('PUT', f'/api/squads/{found["id"]}', payload)
            if code == 422 and payload['status'] == 'published':
                payload['status'] = 'draft'
                code, body = api.call('PUT', f'/api/squads/{found["id"]}', payload)
                if code == 200:
                    downgraded.append(label)
            if code != 200:
                failed.append(f'{label}: {code} {(body or {}).get("error")}')
                continue
            counts['squads'][1] += 1
            print(f'  updated {label}')
            continue
        if args.dry_run:
            print(f'  would create {label}')
            counts['squads'][0] += 1
            continue
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
        counts['squads'][0] += 1
        if body['squad']['owner']['username'].lower() != owner.lower():
            wrong_owner.append(f'{label}: created under {body["squad"]["owner"]["username"]}')
        print(f'  created {label}')
    c_, u_, n_ = counts['squads']
    print(f'Squads: {c_} created, {u_} updated, {n_} unchanged, '
          f'{len([f for f in failed if f.startswith("squad")])} failed.')

    # ======================================================================================================
    # campaigns
    # ======================================================================================================
    remote_campaigns = list_all('/api/campaigns')
    c_taken = set()
    CF = ('name', 'summary', 'intro', 'nation', 'theater', 'enemy', 'period', 'flow_type', 'language', 'status')
    MF = ('code', 'title', 'briefing', 'debrief', 'requirements', 'setup', 'victory', 'rewards')

    def remote_campaign_state(d):
        missions = []
        for m in d['missions']:
            missions.append({
                **{f: norm(m.get(f)) for f in MF}, 'is_entry': bool(m['is_entry']),
                'mission': (m.get('mission') or {}).get('number'), 'situation': (m.get('situation') or {}).get('number'),
                'objective': (m.get('objective') or {}).get('number'),
                'squad': (m.get('squad') or {}).get('id'),
                'overrides': (m['rp_override'], m['time_override'], m['loadout_override'])})
        index = {m['id']: i for i, m in enumerate(d['missions'])}
        links = sorted((index[int(l['from'])], index[int(l['to'])], l['condition'], norm(l['label']))
                       for l in d['links'])
        return {**{f: norm(d.get(f)) for f in CF}, 'settings': json.dumps(d['settings'], sort_keys=True),
                'missions': missions, 'links': links}

    for c, missions, links in local.campaigns():
        owner = owner_of(c['username'])
        label = f'campaign "{c["name"]}" ({owner})'
        key = {m['id']: str(i) for i, m in enumerate(missions)}
        payload = {
            'owner': owner,
            **{k: c[k] for k in CF},
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
        found = next((r for r in remote_campaigns if r['id'] not in c_taken
                      and r['name'].strip().lower() == c['name'].strip().lower()
                      and r['owner']['username'].lower() == owner.lower()), None)
        other_owner = False
        if not found:   # same name under another owner
            found = next((r for r in remote_campaigns if r['id'] not in c_taken
                          and r['name'].strip().lower() == c['name'].strip().lower()), None)
            other_owner = bool(found)
        if found and other_owner and args.fix_owner:
            if args.dry_run:
                print(f'  would delete and recreate {label} (now owned by {found["owner"]["username"]})')
            else:
                api.call('DELETE', f'/api/campaigns/{found["id"]}')
                remote_campaigns.remove(found)
                print(f'  deleted {label} (was owned by {found["owner"]["username"]})')
            found = None
        if found:
            c_taken.add(found['id'])
            if other_owner:
                notes.append(f'{label}: exists under {found["owner"]["username"]} (owner not changed)')
            remote = remote_campaign_state(api.call('GET', f'/api/campaigns/{found["id"]}')[1]['campaign'])
            want = {
                **{f: norm(c[f]) for f in CF},
                'settings': None,
                'missions': [{**{f: norm(m[f]) for f in MF}, 'is_entry': bool(m['is_entry']),
                              'mission': local.n(m['mission_card_id']), 'situation': local.n(m['situation_card_id']),
                              'objective': local.n(m['objective_card_id']),
                              'squad': squad_map.get(m['squad_id']),
                              'overrides': (m['rp_override'], m['time_override'], m['loadout_override'])}
                             for m in missions],
                'links': sorted((list(key).index(l['from_mission_id']), list(key).index(l['to_mission_id']),
                                 l['condition'], norm(l['label'])) for l in links)}
            remote_cmp = {**remote, 'settings': None}
            if remote_cmp == want:
                counts['campaigns'][2] += 1
                continue
            if args.dry_run:
                print(f'  would update {label}')
                counts['campaigns'][1] += 1
                continue
            code, body = api.call('PUT', f'/api/campaigns/{found["id"]}', payload)
            if code == 422 and payload['status'] == 'published':
                payload['status'] = 'draft'
                code, body = api.call('PUT', f'/api/campaigns/{found["id"]}', payload)
                if code == 200:
                    downgraded.append(label)
            if code != 200:
                failed.append(f'{label}: {code} {(body or {}).get("error")} {(body or {}).get("errors", "")}')
                continue
            counts['campaigns'][1] += 1
            print(f'  updated {label}')
            continue
        if args.dry_run:
            print(f'  would create {label}')
            counts['campaigns'][0] += 1
            continue
        code, body = api.call('POST', '/api/campaigns', payload)
        if code == 422 and payload['status'] == 'published':
            payload['status'] = 'draft'
            code, body = api.call('POST', '/api/campaigns', payload)
            if code == 201:
                downgraded.append(label)
        if code != 201:
            failed.append(f'{label}: {code} {(body or {}).get("error")} {(body or {}).get("errors", "")}')
            continue
        counts['campaigns'][0] += 1
        print(f'  created {label}')
        if body['campaign']['owner']['username'].lower() != owner.lower():
            wrong_owner.append(f'{label}: created under {body["campaign"]["owner"]["username"]}')
    c_, u_, n_ = counts['campaigns']
    print(f'Campaigns: {c_} created, {u_} updated, {n_} unchanged.')

    for line in notes:
        print(f'  note: {line}')
    if wrong_owner:
        print(f'\nWARNING: {len(wrong_owner)} items were created under the wrong owner. The server probably runs an '
              f'older version that ignores the "owner" field: deploy the new version first.')
        for line in wrong_owner[:5]:
            print(f'  {line}')
    if notes and not args.fix_owner:
        print(f'\n{len(notes)} items exist under another owner than wanted; re-run with --fix-owner to recreate them.')
    for line in downgraded:
        print(f'  saved as draft (does not pass validation): {line}')
    for line in failed:
        print(f'  FAILED {line}')
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
