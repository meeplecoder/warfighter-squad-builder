"""
Build app/metric_reference.json — the reference data behind the squad metrics (app/metrics.py, spec 12).

  hostiles   Cover / Penetration distributions and Hostiles per card, from the Hostile cards of cards2.csv
             (not imported into the DB): key 'all' and '<nation>|<Frontline|Elite>'.
  locations  entrance-cost distribution of the Location cards: 'all' and per deck.
  community  raw metric values of the published squads in the DB, per budget band — the scale the
             0..1 scores are percentiles of (replaced by random legal squads later).

Run after changing the metrics or the squad data (needs the DB for the community part):
  DEBUG=true python scripts/build_metric_reference.py [--skip-community]
"""
import csv
import collections
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CSV_PATH = os.path.join(os.path.dirname(ROOT), 'cards2.csv')
OUT = os.path.join(ROOT, 'app', 'metric_reference.json')


def norm(counter):
    tot = sum(counter.values()) or 1
    return {str(k): round(v / tot, 4) for k, v in sorted(counter.items())}


def stat(row, key):
    m = re.search(rf'(?:^|\n){re.escape(key)}:\s*([^\n]+)', row.get('Stats') or '')
    return m.group(1).strip() if m else None


def build_csv_part():
    rows = list(csv.DictReader(open(CSV_PATH, encoding='utf-8')))
    groups = collections.defaultdict(lambda: {'cover': collections.Counter(), 'pen': collections.Counter(), 'h': []})
    for r in rows:
        t = r['Type']
        if 'Hostile' not in t:
            continue
        c = stat(r, 'C')
        if c is None or not c.isdigit():
            continue
        m = re.search(r'Pen(?:etration)?\s+(\d+)', r.get('Notes') or '')
        pen = int(m.group(1)) if m else 0
        h = stat(r, 'H#')
        level = 'Elite' if 'Elite' in t else 'Frontline' if 'Frontline' in t else None
        keys = ['all']
        if level and r.get('Nation'):
            keys.append(f"{r['Nation']}|{level}")
        for k in keys:
            g = groups[k]
            g['cover'][int(c)] += 1
            g['pen'][pen] += 1
            if h and h.isdigit():
                g['h'].append(int(h))
    hostiles = {k: {'cover': norm(g['cover']), 'pen': norm(g['pen']),
                    'per_card': round(sum(g['h']) / len(g['h']), 2) if g['h'] else 2.6, 'n': sum(g['cover'].values())}
                for k, g in groups.items() if sum(g['cover'].values()) >= 10}

    decks = collections.defaultdict(collections.Counter)
    for r in rows:
        t = r['Type']
        if not t.startswith('Location'):
            continue
        en = stat(r, 'EN')
        if en is None or not en.isdigit():
            continue
        decks['all'][int(en)] += 1
        decks[t[len('Location'):].strip() or 'Generic'][int(en)] += 1
    locations = {k: norm(v) for k, v in decks.items()}
    return hostiles, locations


def build_community():
    from app import create_app
    from app.models import Squad
    from app import metrics
    app = create_app()
    out = {}
    with app.app_context():
        metrics.clear_cache()
        per_band = collections.defaultdict(lambda: collections.defaultdict(list))
        count = collections.Counter()
        for sq in Squad.query.filter_by(status='published').all():
            try:
                data, mission, objectives = metrics.squad_input(sq)
                raw = metrics.analyse(data, mission, objectives)
            except Exception as e:                       # one bad squad must not stop the build
                print(f'  skip squad {sq.id} {sq.name!r}: {type(e).__name__}: {e}')
                continue
            for band in (metrics.budget_band(mission.get('budget')), 'all'):
                count[band] += 1
                for k in metrics.METRIC_KEYS:
                    per_band[band][k].append(round(raw[k]['raw'], 4))
        for band, vals in per_band.items():
            out[band] = {'n': count[band], 'values': {k: sorted(v) for k, v in vals.items()}}
    return out


def main():
    hostiles, locations = build_csv_part()
    ref = {'hostiles': hostiles, 'locations': locations, 'community': {}}
    if '--skip-community' not in sys.argv:
        # write the CSV part first so the community pass runs against the real reference
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        json.dump(ref, open(OUT, 'w', encoding='utf-8'))
        ref['community'] = build_community()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(ref, f, ensure_ascii=False, separators=(',', ':'))
    print(f'hostile groups: {len(hostiles)} · location decks: {len(locations)} · '
          f'community bands: { {b: v["n"] for b, v in ref["community"].items()} }')


if __name__ == '__main__':
    main()
