#!/usr/bin/env python3
"""
Check UI translation keys. Run from the warfighter-squad-builder/ directory:
    python scripts/i18n_check.py [--strict]

Reports keys used in static/*.js / index.html but missing from static/i18n/en.json,
en.json keys never used, and per-language coverage (keys missing vs en.json).
--strict exits non-zero when en.json is missing keys.
"""
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(BASE, 'static')
I18N_DIR = os.path.join(STATIC, 'i18n')

# t('x.y'), tn('x.y', n), data-i18n="x.y", and i18n keys stored as plain strings ('col.name')
KEY_PATTERNS = [
    re.compile(r"""\btn?\(\s*['"]([a-z_]+\.[a-z0-9_.]+)['"]"""),
    re.compile(r"""data-i18n(?:-title)?="([a-z_]+\.[a-z0-9_.]+)\""""),
    re.compile(r"""header:\s*'([a-z_]+\.[a-z0-9_.]+)'"""),
]
PLURAL_RE = re.compile(r"""\btn\(\s*['"]([a-z_]+\.[a-z0-9_.]+)['"]""")
# Keys built at runtime — prefixes whose children are never flagged as unused
DYNAMIC_PREFIXES = ('enum.', 'tr.status.', 'tr.marker.')


def used_keys():
    keys, plurals = set(), set()
    for name in os.listdir(STATIC):
        if not name.endswith(('.js', '.html')):
            continue
        text = open(os.path.join(STATIC, name), encoding='utf-8').read()
        for pat in KEY_PATTERNS:
            keys.update(pat.findall(text))
        plurals.update(PLURAL_RE.findall(text))
    keys = {k for k in keys if not k.endswith('.')}  # t('prefix.' + x) — dynamic, see DYNAMIC_PREFIXES
    for k in plurals:
        keys.discard(k)
        keys.update({f'{k}_one', f'{k}_other'})
    return keys


def main():
    en = json.load(open(os.path.join(I18N_DIR, 'en.json'), encoding='utf-8'))
    used = used_keys()
    missing = sorted(k for k in used if k not in en)
    unused = sorted(k for k in en if k not in used and not k.startswith(DYNAMIC_PREFIXES))
    print(f'en.json: {len(en)} keys, {len(used)} used in code')
    if missing:
        print(f'\nMISSING in en.json ({len(missing)}):\n  ' + '\n  '.join(missing))
    if unused:
        print(f'\nUnused in code ({len(unused)}):\n  ' + '\n  '.join(unused))

    ui_keys = [k for k in en if not k.startswith('enum.')]
    for name in sorted(os.listdir(I18N_DIR)):
        if not name.endswith('.json') or name == 'en.json':
            continue
        lang = json.load(open(os.path.join(I18N_DIR, name), encoding='utf-8'))
        lacking = [k for k in ui_keys if k not in lang]
        extra = [k for k in lang if k not in en and not k.startswith('enum.')]
        pct = 100 * (len(ui_keys) - len(lacking)) / max(1, len(ui_keys))
        print(f'\n{name}: {pct:.0f}% of UI keys translated'
              + (f' — missing: {", ".join(lacking)}' if lacking else '')
              + (f'\n  keys not in en.json: {", ".join(extra)}' if extra else ''))

    # Server messages: every _('…') string and rules.MESSAGES template needs an entry per catalogue
    sys.path.insert(0, BASE)
    from app.rules import MESSAGES
    server = set(MESSAGES.values())
    app_dir = os.path.join(BASE, 'app')
    for name in os.listdir(app_dir):
        if name.endswith('.py'):
            server.update(re.findall(r"\b_\('([^']+)'", open(os.path.join(app_dir, name), encoding='utf-8').read()))
    cat_dir = os.path.join(app_dir, 'translations')
    for name in sorted(os.listdir(cat_dir)):
        if name.endswith('.json'):
            cat = json.load(open(os.path.join(cat_dir, name), encoding='utf-8'))
            lacking = sorted(m for m in server if m not in cat)
            print(f'\nserver {name}: {len(server) - len(lacking)}/{len(server)} messages'
                  + (''.join(f'\n  missing: {m}' for m in lacking)))

    if missing and '--strict' in sys.argv:
        sys.exit(1)


if __name__ == '__main__':
    main()
