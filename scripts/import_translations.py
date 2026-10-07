#!/usr/bin/env python3
"""
Import / export card translations (contract: spec/07_i18n.md §4.5).
Run from the warfighter-squad-builder/ directory:

    python scripts/import_translations.py import FILE.json|FILE.csv [--dry-run] [--overwrite-reviewed]
    python scripts/import_translations.py export --lang es [--status draft|reviewed] [-o FILE.json|FILE.csv]
    python scripts/import_translations.py rehash

Entries: {"number", "lang", "field": "name"|"notes", "value", "status": "reviewed"|"draft" (default reviewed)}
CSV uses the same columns as a header row.
"""
import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))
except ImportError:
    pass

from app import create_app
from app import translation_io

CSV_COLUMNS = ['number', 'lang', 'field', 'value', 'status']


def read_entries(path):
    if path.lower().endswith('.csv'):
        with open(path, encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, list):
        sys.exit('JSON file must contain an array of entries.')
    return data


def write_entries(entries, path):
    if path and path.lower().endswith('.csv'):
        with open(path, 'w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=CSV_COLUMNS + ['stale'])
            w.writeheader()
            w.writerows(entries)
        return
    text = json.dumps(entries, ensure_ascii=False, indent=2)
    if path:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text + '\n')
    else:
        print(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p_imp = sub.add_parser('import')
    p_imp.add_argument('file')
    p_imp.add_argument('--dry-run', action='store_true')
    p_imp.add_argument('--overwrite-reviewed', action='store_true')
    p_exp = sub.add_parser('export')
    p_exp.add_argument('--lang', required=True)
    p_exp.add_argument('--status', choices=translation_io.STATUSES)
    p_exp.add_argument('-o', '--output')
    sub.add_parser('rehash')
    args = ap.parse_args()

    app = create_app()
    with app.app_context():
        if args.cmd == 'import':
            report = translation_io.import_entries(
                read_entries(args.file), overwrite_reviewed=args.overwrite_reviewed, dry_run=args.dry_run)
            print(('DRY RUN — nothing written\n' if args.dry_run else '')
                  + f"Inserted: {report['inserted']} | Updated: {report['updated']} | "
                  f"Unchanged: {report['unchanged']} | Deleted: {report['deleted']}")
            if report['kept_reviewed']:
                print(f"Kept {len(report['kept_reviewed'])} reviewed rows (use --overwrite-reviewed): "
                      + ', '.join(report['kept_reviewed'][:20]) + (' …' if len(report['kept_reviewed']) > 20 else ''))
            if report['unknown_numbers']:
                print(f"Unknown card numbers ({len(report['unknown_numbers'])}): "
                      + ', '.join(report['unknown_numbers'][:20]))
            if report['invalid']:
                print(f"Invalid entries ({len(report['invalid'])}), first: {report['invalid'][0]}")
        elif args.cmd == 'export':
            write_entries(translation_io.export_entries(args.lang, args.status), args.output)
        else:
            r = translation_io.rehash()
            print(f"Up to date: {r['fresh']} | Stale: {r['stale']} | Adopted: {r['adopted']} | "
                  f"Orphaned: {len(r['orphaned'])}")


if __name__ == '__main__':
    main()
