#!/usr/bin/env python3
"""
Machine-translate card names/notes with Claude. Writes rows with status='draft'.
Run from the warfighter-squad-builder/ directory:

    pip install anthropic          # not an app dependency — only this script needs it
    export ANTHROPIC_API_KEY=...
    python scripts/translate.py --lang es [--fields name,notes] [--type Skill] [--limit 200] [--dry-run]

Only touches entries that are missing or draft+stale. Reviewed rows are never overwritten,
and up-to-date drafts are left alone. Identical English texts are translated once and
fanned out to every card that uses them. The glossary (static/i18n/glossary.<lang>.csv)
is sent with every request. See spec/07_i18n.md §4.2.

Prefer importing official Spanish-edition text first (scripts/import_translations.py);
this script is the fallback for whatever is still missing.
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

from app import create_app, db, i18n
from app.models import Card, CardTranslation
from app import translation_io

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANG_NAMES = {'es': 'Spanish (Spain)'}
DEFAULT_MODEL = 'claude-opus-5-5'


def load_glossary(lang):
    path = os.path.join(BASE, 'static', 'i18n', f'glossary.{lang}.csv')
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8-sig', newline='') as f:
        return [r for r in csv.DictReader(f) if r.get('term_en')]


def system_prompt(lang, glossary):
    terms = '\n'.join(f"- {g['term_en']} → {g['term_' + lang]}" + (f"  ({g['note']})" if g.get('note') else '')
                      for g in glossary)
    return f"""You translate card text for the board game Warfighter WWII (Dan Verssen Games) from English into {LANG_NAMES.get(lang, lang)}.
The translation is shown to Spanish-speaking players next to their printed Spanish-edition cards, so use the established game terminology below exactly and keep the tone of printed rules text: short, imperative, consistent.

Rules:
- Keep every number, dice notation, symbol, abbreviation in the glossary, and line break exactly as in the source. Each source line becomes one translated line.
- Proper names of soldiers, places and weapon models stay as in the source unless the glossary gives a translation.
- Card names: translate descriptive names (skills, equipment, missions, objectives); keep personal names.
- Do not add explanations or notes. Return one translation per input id.

Glossary (English → {lang}):
{terms or '(empty)'}"""


def collect_work(lang, fields, card_type, limit):
    """Return {(field, english_text): [card, ...]} for entries that need machine translation."""
    rows = {(r.card_number, r.field): r for r in CardTranslation.query.filter_by(lang=lang)}
    query = Card.query
    if card_type:
        query = query.filter(Card.card_type == card_type)
    work = {}
    for card in query.order_by(Card.number):
        for field in fields:
            english = getattr(card, field)
            if not english or not english.strip():
                continue
            row = rows.get((card.number, field))
            if row and (row.status == 'reviewed' or not row.stale):
                continue
            work.setdefault((field, english), []).append(card)
            if limit and len(work) >= limit:
                return work
    return work


def translate_batch(client, model, system, batch):
    """batch: [(id, field, card_type, text)] → {id: translation}"""
    from pydantic import BaseModel

    class Item(BaseModel):
        id: int
        text: str

    class Result(BaseModel):
        items: list[Item]

    payload = [{'id': i, 'kind': f'{card_type} {field}', 'text': text} for i, field, card_type, text in batch]
    response = client.messages.parse(
        model=model,
        max_tokens=16000,
        output_config={'effort': 'medium'},
        system=[{'type': 'text', 'text': system, 'cache_control': {'type': 'ephemeral'}}],
        messages=[{'role': 'user', 'content':
                   'Translate the "text" of each entry. Return every id.\n\n'
                   + json.dumps(payload, ensure_ascii=False, indent=1)}],
        output_format=Result,
    )
    if response.stop_reason != 'end_turn' or response.parsed_output is None:
        print(f'  ! batch not translated (stop_reason={response.stop_reason})')
        return {}
    return {it.id: it.text for it in response.parsed_output.items}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--lang', required=True)
    ap.add_argument('--fields', default='name,notes')
    ap.add_argument('--type', dest='card_type', help='Only this card_type (e.g. Skill)')
    ap.add_argument('--limit', type=int, default=0, help='Max unique texts to translate')
    ap.add_argument('--batch-size', type=int, default=20)
    ap.add_argument('--model', default=DEFAULT_MODEL)
    ap.add_argument('--dry-run', action='store_true', help='Show what would be translated; no API calls')
    args = ap.parse_args()

    lang = i18n.normalize_lang(args.lang)
    if not lang or lang == i18n.DEFAULT_LANG:
        sys.exit(f'Unsupported target language: {args.lang}')
    fields = [f for f in args.fields.split(',') if f in i18n.CARD_FIELDS]

    app = create_app()
    with app.app_context():
        work = collect_work(lang, fields, args.card_type, args.limit)
        n_cards = sum(len(v) for v in work.values())
        chars = sum(len(text) for (_, text) in work)
        print(f'{len(work)} unique texts ({chars:,} chars) for {n_cards} card fields need translation.')
        if args.dry_run or not work:
            for (field, text), cards in list(work.items())[:10]:
                print(f'  [{field}] {text[:70]!r} × {len(cards)}')
            return

        try:
            import anthropic
        except ImportError:
            sys.exit('pip install anthropic  (only needed for this script)')
        client = anthropic.Anthropic()
        system = system_prompt(lang, load_glossary(lang))

        items = list(work.items())
        done = 0
        for start in range(0, len(items), args.batch_size):
            chunk = items[start:start + args.batch_size]
            batch = [(i, field, cards[0].card_type, text) for i, ((field, text), cards) in enumerate(chunk)]
            try:
                out = translate_batch(client, args.model, system, batch)
            except anthropic.APIStatusError as e:
                print(f'  ! API error {e.status_code}: {e.message} — stopping; rerun to continue')
                break
            except anthropic.APIConnectionError:
                print('  ! network error — stopping; rerun to continue')
                break
            for i, ((field, _), cards) in enumerate(chunk):
                if out.get(i):
                    for card in cards:
                        translation_io.upsert(card, lang, field, out[i], 'draft', overwrite_reviewed=False)
                    done += 1
            db.session.commit()
            print(f'  {min(start + args.batch_size, len(items))}/{len(items)} texts processed')
        i18n.invalidate_cache()
        print(f'Done: {done} texts written as draft. Review them in the app (Translations).')


if __name__ == '__main__':
    main()
